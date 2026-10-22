from .financial_test_helpers import install_area
from .financial_areas import area_scope
import struct
import tempfile
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.db import connection, close_old_connections, DatabaseError
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import access, document_services as docs, services
from .document_storage import inspect_content, path_for as legacy_path
from .document_spool import path_for
from .models import Household, Membership, Category, Document, DocumentJob, Entry, BillOccurrence


def png(width=1, height=1):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + chunk(b'IEND', b'')


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
class WorkflowAssetTests(SimpleTestCase):
    def test_production_serves_workflow_scripts_without_debug_static_handler(self):
        for name in ('camera-scan.js', 'document-draft.js', 'shopping.js'):
            with self.subTest(name=name):
                response = self.client.get('/static/budget/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/javascript')
                self.assertEqual(b''.join(response.streaming_content),
                    (Path(__file__).parent / 'static' / 'budget' / name).read_bytes())
        self.assertEqual(self.client.get('/static/budget/document_services.py').status_code, 404)


class DocumentTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(PRIVATE_DOCUMENT_ROOT=self.temp.name + "/legacy", PRIVATE_SCAN_ROOT=self.temp.name + "/scans")
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user(username='doc-test', email='doc@example.test')
        self.house = Household.objects.create(name='Synthetic')
        self.member = Membership.objects.create(user=self.user, household=self.house, role='admin')
        install_area(self, self.member)
        self.category = Category.objects.create(household=self.house, created_by=self.user, name='Testmat')
        self.today = timezone.localdate()
        self.client.force_login(self.user)

    def upload(self, key=None):
        return docs.upload(self.user, SimpleUploadedFile('test.png', png()), key or uuid.uuid4())

    def draft(self):
        row = self.upload()
        return docs.save_draft(self.user, row.pk, row.version, uuid.uuid4(), supplier='Testbutikk', amount_ore=125000,
            document_date=self.today, due_date=self.today, category_id=self.category.pk)

    def test_upload_draft_and_original_are_private_without_money(self):
        row = self.draft()
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(BillOccurrence.objects.count(), 0)
        self.assertEqual(path_for(row.storage_key).read_bytes(), png())
        result = self.client.get(reverse('document_original', args=[row.pk]))
        self.assertEqual(result.status_code, 404)
        self.assertEqual(row.filename, '')
        self.assertTrue(row.transient)
        self.assertContains(self.client.get(reverse('document_detail', args=[row.pk])), 'Lagre utkast uten bokføring')

    def test_confirm_bill_retry_and_receipt_link_creates_no_extra_expense(self):
        row = self.draft()
        key, version = uuid.uuid4(), row.version
        row = docs.confirm(self.user, row.pk, version, key, 'bill')
        docs.confirm(self.user, row.pk, version, key, 'bill')
        self.assertEqual(BillOccurrence.objects.count(), 1)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertFalse(row.bill.template.monthly)
        payment = services.pay_bill(self.user, row.bill_id, self.today, uuid.uuid4(), row.bill.version)
        receipt = self.draft()
        docs.confirm(self.user, receipt.pk, receipt.version, uuid.uuid4(), 'link_entry', payment.pk)
        self.assertEqual(Entry.objects.count(), 1)

    def test_duplicates_require_explicit_override(self):
        first = self.draft()
        docs.confirm(self.user, first.pk, first.version, uuid.uuid4(), 'expense')
        second = self.draft()
        self.assertTrue(docs.duplicates(self.member, second))
        with self.assertRaises(ValidationError): docs.confirm(self.user, second.pk, second.version, uuid.uuid4(), 'expense')
        second.sha256 = '0' * 64
        second.save()
        self.assertTrue(docs.duplicates(self.member, second))
        self.assertEqual(Entry.objects.count(), 1)

    def test_replay_rechecks_revoked_access(self):
        row = self.draft()
        key, version = uuid.uuid4(), row.version
        docs.confirm(self.user, row.pk, version, key, 'expense')
        self.member.role, self.member.module_access = 'member', {'budget': False}
        self.member.save()
        with self.assertRaises(PermissionDenied): docs.confirm(self.user, row.pk, version, key, 'expense')
        self.assertEqual(self.client.get(reverse('document_detail', args=[row.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('document_original', args=[row.pk])).status_code, 404)
        self.assertFalse(access.safe_rows(self.member, Document.objects.all()).exists())

    def test_document_permission_not_finance_shortcut_and_other_family(self):
        row = self.upload()
        self.member.role, self.member.module_access = 'member', {'documents': False}
        self.member.save()
        self.assertTrue(access.complete_finance(self.member))
        self.assertFalse(access.safe_rows(self.member, Document.objects.all()).exists())
        foreign = Household.objects.create(name='Other synthetic')
        other = get_user_model().objects.create_user(username='document-foreign-member')
        Membership.objects.create(user=other, household=foreign)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('document_original', args=[row.pk])).status_code, 403)

    def test_upload_and_draft_idempotency_and_conflicts(self):
        key = uuid.uuid4()
        a, b = self.upload(key), self.upload(key)
        self.assertEqual(a.pk, b.pk)
        draft_key = uuid.uuid4()
        docs.save_draft(self.user, a.pk, 1, draft_key, supplier='First')
        docs.save_draft(self.user, a.pk, 1, draft_key, supplier='First')
        with self.assertRaises(services.Conflict): docs.save_draft(self.user, a.pk, 1, uuid.uuid4(), supplier='Old')
        with self.assertRaises(services.Conflict): docs.save_draft(self.user, a.pk, 1, draft_key, supplier='Changed')

    def test_invalid_and_oversized_files(self):
        for data in (b'fake', b'%PDF-fake', png(6000, 6000), png()[:-5], b'x' * (10 * 1024 * 1024 + 1)):
            with self.assertRaises(ValidationError): inspect_content(data)
        with self.assertRaises(ValidationError): legacy_path('../../secret')

    def test_worker_failure_discards_photo_but_preserves_reviewed_draft(self):
        from .document_ocr import process_one
        row = self.draft()
        with patch('budget.document_ocr.recognize', side_effect=FileNotFoundError): self.assertTrue(process_one())
        row.refresh_from_db()
        self.assertEqual(row.job.status, 'failed')
        self.assertEqual(row.supplier, 'Testbutikk')
        self.assertFalse(path_for(row.storage_key).exists())
        self.assertIsNotNone(row.photo_deleted_at)
        self.assertEqual(row.ocr_text, '')
        self.assertFalse(Entry.objects.exists())

    def test_reads_do_not_materialize_bills(self):
        from .models import BillTemplate
        BillTemplate.objects.create(household=self.house, created_by=self.user, name='Not materialized', amount_ore=100, first_due=self.today)
        self.client.get(reverse('documents'))
        self.assertFalse(BillOccurrence.objects.exists())

    def test_restricted_home_lists_new_modules(self):
        self.member.role = 'member'
        self.member.module_access = {module: False for module in access.MODULES}
        self.member.module_access['documents'] = True
        self.member.save()
        result = self.client.get(reverse('page', args=['oversikt']))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Skann kvittering')
        self.member.module_access['documents'] = False
        self.member.module_access['shopping'] = True
        self.member.save()
        self.assertContains(self.client.get(reverse('page', args=['oversikt'])), 'Handlelister')

    def test_ocr_copy_is_explicit_escaped_and_does_not_write(self):
        row = self.draft()
        row.suggestions = {'supplier': '</script><script>alert(1)</script>', 'amount': '1250,00', 'document_date': '22.10.2026'}
        row.save(update_fields=['suggestions'])
        DocumentJob.objects.filter(document=row).update(status='ready')
        response = self.client.get(reverse('document_detail', args=[row.pk]))
        self.assertContains(response, 'Bruk forslag i utkast')
        self.assertContains(response, 'id="use-document-suggestions" type="button"')
        self.assertContains(response, 'id="document-suggestions" type="application/json"')
        self.assertNotContains(response, '</script><script>alert(1)</script>')
        self.assertContains(response, '\\u003C/script\\u003E')
        row.refresh_from_db()
        self.assertEqual(row.supplier, 'Testbutikk')
        self.assertFalse(Entry.objects.exists())
        self.assertFalse(BillOccurrence.objects.exists())

    def test_streaming_cap_prevents_oversized_temporary_file(self):
        written = []
        original = TemporaryFileUploadHandler.receive_data_chunk
        def observe(handler, chunk, start):
            written.append(len(chunk))
            return original(handler, chunk, start)
        with patch.object(TemporaryFileUploadHandler, 'receive_data_chunk', observe):
            response = self.client.post(reverse('documents'), {'key': uuid.uuid4(),
                'file': SimpleUploadedFile('oversized.png', b'x' * (10 * 1024 * 1024 + 256 * 1024))})
        self.assertContains(response, 'Opplastingen er stoppet: maks. 10 MiB')
        self.assertLessEqual(sum(written), 10 * 1024 * 1024)
        self.assertFalse(Document.objects.exists())

    def test_http_validation_and_disk_write_do_not_take_household_lock(self):
        baseline = len(connection.atomic_blocks)
        original_inspect, original_store = docs.document_storage.inspect_content, docs.document_spool.store
        with patch('budget.document_services.access.lock_member', wraps=access.lock_member) as lock:
            def inspect(data, **kwargs):
                self.assertEqual(lock.call_count, 1)  # Short replay preflight has already ended.
                self.assertEqual(len(connection.atomic_blocks), baseline)
                return original_inspect(data, **kwargs)
            def store(data):
                self.assertEqual(lock.call_count, 1)
                self.assertEqual(len(connection.atomic_blocks), baseline)
                return original_store(data)
            with patch('budget.document_services.document_storage.inspect_content', side_effect=inspect), patch('budget.document_services.document_spool.store', side_effect=store):
                result = self.client.post(reverse('documents'), {'key':uuid.uuid4(), 'file':SimpleUploadedFile('test.png',png())})
            self.assertEqual(lock.call_count, 2)
        self.assertEqual(result.status_code, 302)

    def test_access_revoked_during_validation_is_rechecked(self):
        self.member.role = 'member'
        self.member.save()
        def inspect(data, **kwargs):
            Membership.objects.filter(pk=self.member.pk).update(module_access={'documents':False})
            return 'image/png'
        with patch('budget.document_services.document_storage.inspect_content', side_effect=inspect):
            with self.assertRaises(PermissionDenied): self.upload()
        self.assertFalse(Document.objects.exists())

    def test_paginated_documents_and_confirmed_review_summary(self):
        first = self.draft()
        docs.confirm(self.user, first.pk, first.version, uuid.uuid4(), 'expense')
        for i in range(101):
            Document.objects.create(household=self.house, created_by=self.user, storage_key=f'{self.house.pk}/{uuid.uuid4().hex}',
                filename=f'Synthetic-{i}.png', content_type='image/png', sha256='a'*64, size=1)
        response = self.client.get(reverse('documents')+'?document_page=4')
        self.assertContains(response, reverse('document_detail', args=[first.pk]))
        self.assertContains(response, 'Side 4 av 4')
        summary = self.client.get(reverse('document_detail', args=[first.pk]))
        for value in ('Testbutikk', 'Testmat'):
            self.assertContains(summary, value)
        self.assertNotContains(summary, 'id="document-draft-form"')

    def test_structurally_empty_images_and_complete_grouped_amounts(self):
        # Valid header/CRC is insufficient when the image stream is absent/truncated.
        valid = png()
        header_only = valid[:33] + valid[-12:]
        jpeg_no_scan = b'\xff\xd8\xff\xc0\x00\x08\x08\x00\x01\x00\x01\x01\xff\xd9'
        for data in (header_only, jpeg_no_scan):
            with self.assertRaises(ValidationError): inspect_content(data)
        from .document_ocr import suggestions
        for text in ('1.250,00', '1 250,00', '1\u00a0250,00', '1250,00'):
            self.assertEqual(suggestions('Totalt NOK '+text)['amount'], '1250,00')
        for text in ('1.25.0,00', '12,50,99', '1,250.00', '1.250,001', '1250,00x'):
            self.assertNotIn('amount', suggestions('Totalt NOK '+text))

    def test_document_http_stale_draft_recovery_preserves_input_without_posting(self):
        row = self.draft()
        url = reverse('document_detail', args=[row.pk])
        submitted = dict(form='draft',key=uuid.uuid4(),version=1,supplier='Mitt beholdte utkast',amount='100,00',
            document_date=self.today.isoformat(),due_date=self.today.isoformat(),invoice_number='EGEN',kid='',category=self.category.pk)
        stale = self.client.post(url, submitted)
        self.assertContains(stale, 'Mitt beholdte utkast')
        recovered = self.client.post(url, {**submitted,'refresh_version':'1'})
        self.assertContains(recovered, 'Utkastet er beholdt')
        self.assertEqual(recovered.context['draft']['supplier'].value(), 'Mitt beholdte utkast')
        self.assertEqual(int(recovered.context['draft']['version'].value()), row.version)
        self.assertFalse(Entry.objects.exists())
        row.refresh_from_db()
        self.assertEqual(row.supplier,'Testbutikk')

    def test_upload_exact_retry_skips_decode_and_store_and_checks_current_row_access(self):
        row = self.draft()
        docs.confirm(self.user, row.pk, row.version, uuid.uuid4(), 'expense')
        before = set(Path(self.temp.name).rglob('*'))
        with patch('budget.document_services.document_storage.inspect_content') as decode, patch('budget.document_services.document_spool.store') as store:
            self.assertEqual(self.upload(row.upload_key).pk, row.pk)
            decode.assert_not_called(); store.assert_not_called()
            self.member.role, self.member.module_access = 'member', {'budget': False}
            self.member.save()
            with self.assertRaises(PermissionDenied): self.upload(row.upload_key)
            decode.assert_not_called(); store.assert_not_called()
        self.assertEqual(set(Path(self.temp.name).rglob('*')), before)
        self.assertEqual(path_for(row.storage_key).read_bytes(), png())

    def test_rejected_upload_discards_only_its_current_staging_file(self):
        existing = self.upload()
        original = docs.document_spool.store
        staged = []
        def revoked_store(data):
            key = original(data)
            staged.append(key)
            Membership.objects.filter(pk=self.member.pk).update(role='member', module_access={'documents':False})
            return key
        with patch('budget.document_services.document_spool.store', side_effect=revoked_store):
            with self.assertRaises(PermissionDenied): self.upload()
        self.assertFalse(path_for(staged[0]).exists())
        self.assertEqual(path_for(existing.storage_key).read_bytes(), png())
        self.assertEqual(Document.objects.count(), 1)

    def test_changed_queue_discards_new_unregistered_file(self):
        with patch('budget.document_services.DocumentJob.objects.filter') as queue:
            queue.return_value.count.side_effect = [0, 100]
            with self.assertRaises(ValidationError): self.upload()
        self.assertEqual([path for path in Path(self.temp.name).rglob('*') if path.is_file()], [])
        self.assertFalse(Document.objects.exists())

    def test_legacy_cleanup_retains_referenced_file_and_database_uncertainty(self):
        new_key = docs.document_storage.store(self.house.pk, png())
        with patch('budget.models.Document.objects.filter', side_effect=DatabaseError('synthetic unavailable')):
            self.assertFalse(docs.document_storage.discard_unregistered_staging(new_key))
        self.assertEqual(legacy_path(new_key).read_bytes(), png())

    def test_registration_error_never_discards_potentially_referenced_original(self):
        with patch('budget.document_services.Document.objects.create', side_effect=DatabaseError('synthetic uncertain insert')):
            with patch('budget.document_services.document_spool.discard') as cleanup:
                with self.assertRaises(DatabaseError): self.upload()
                cleanup.assert_not_called()
        self.assertEqual(len([path for path in Path(self.temp.name).rglob('*') if path.is_file()]), 1)


class ConcurrentDocumentUploadTests(TransactionTestCase):
    def test_raced_same_key_preserves_one_original_and_removes_only_losing_staging(self):
        user = get_user_model().objects.create_user(username='synthetic-upload-race')
        house = Household.objects.create(name='Synthetic upload race')
        member = Membership.objects.create(user=user, household=house, role='admin')
        install_area(self, member)
        barrier = Barrier(2)
        key = uuid.uuid4()
        original_inspect = docs.document_storage.inspect_content
        def inspect(data, **kwargs):
            result = original_inspect(data, **kwargs)
            self.assertFalse(connection.in_atomic_block)
            barrier.wait(timeout=10)
            return result
        def perform(_):
            close_old_connections()
            try:
                with area_scope(member, self.area.pk):
                    return docs.upload(user, SimpleUploadedFile('race.png', png()), key).pk
            finally:
                close_old_connections()
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_DOCUMENT_ROOT=directory + "/legacy", PRIVATE_SCAN_ROOT=directory + "/scans"):
            with patch('budget.document_services.document_storage.inspect_content', side_effect=inspect):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(perform, range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(Document.objects.count(), 1)
            self.assertEqual(DocumentJob.objects.count(), 1)
            files = [path for path in Path(directory).rglob('*') if path.is_file()]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), png())

class ConcurrentDocumentConfirmationTests(TransactionTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        setting = override_settings(PRIVATE_DOCUMENT_ROOT=self.temp.name + "/legacy", PRIVATE_SCAN_ROOT=self.temp.name + "/scans")
        setting.enable()
        self.addCleanup(setting.disable)
        self.house = Household.objects.create(name='Synthetic two-member confirmation')
        self.users = [get_user_model().objects.create_user(username=f'confirm-member-{i}') for i in range(2)]
        members = [Membership.objects.create(user=user, household=self.house, role='member') for user in self.users]
        install_area(self, members[0], members[1:])
        category = Category.objects.create(household=self.house, created_by=self.users[0], name='Test')
        row = docs.upload(self.users[0], SimpleUploadedFile('test.png', png()), uuid.uuid4())
        self.row = docs.save_draft(self.users[0], row.pk, row.version, uuid.uuid4(), supplier='Synthetic store',
            amount_ore=125000, document_date=timezone.localdate(), due_date=timezone.localdate(), category_id=category.pk)

    def race(self, action, same_key):
        from .models import BillTemplate, WorkflowCommand
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(2)
        keys = [uuid.uuid4(), uuid.uuid4()]
        if same_key: keys[1] = keys[0]
        def attempt(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                try:
                    with area_scope(Membership.objects.get(user=self.users[index]), self.area.pk):
                        result = docs.confirm(self.users[index], self.row.pk, self.row.version, keys[index], action).pk
                except services.Conflict:
                    result = 'conflict'
                return pid, result
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(len({pid for pid, _ in outcomes}), 2)
        results = [result for _, result in outcomes]
        # Workflow keys are bound to the actor as well as the area.
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(set(results) - {'conflict'}, {self.row.pk})
        old_version = self.row.version
        self.row.refresh_from_db()
        self.assertTrue(self.row.confirmed)
        self.assertEqual(self.row.version, old_version + 1)
        self.assertEqual(WorkflowCommand.objects.filter(operation='document_confirm').count(), 1)
        self.assertEqual(Entry.objects.count(), int(action == 'expense'))
        self.assertEqual(BillTemplate.objects.count(), int(action == 'bill'))
        self.assertEqual(BillOccurrence.objects.count(), int(action == 'bill'))
        target = self.row.entry if action == 'expense' else self.row.bill
        self.assertEqual(target.amount_ore, 125000)
        self.assertIn(target.created_by_id, [user.pk for user in self.users])

    def test_two_members_replay_one_bill(self): self.race('bill', True)
    def test_two_members_distinct_commands_create_one_bill(self): self.race('bill', False)
    def test_two_members_replay_one_expense(self): self.race('expense', True)
    def test_two_members_distinct_commands_create_one_expense(self): self.race('expense', False)


class LinkedDocumentModuleRevocationTests(TestCase):
    setUp = DocumentTests.setUp
    upload = DocumentTests.upload
    draft = DocumentTests.draft

    def test_linked_bill_module_revocation_hides_ocr_original_and_denies_replay(self):
        from .models import BillTemplate
        for module, accounting_class in [('bills', 'ordinary'), ('debt', 'debt'), ('fund', 'fund')]:
            with self.subTest(module=module):
                self.member.role, self.member.module_access = 'member', {}
                self.member.save()
                template = BillTemplate.objects.create(household=self.house, created_by=self.user,
                    name='Synthetic linked bill', amount_ore=125000, first_due=self.today, monthly=False,
                    accounting_class=accounting_class)
                bill = BillOccurrence.objects.create(household=self.house, created_by=self.user, template=template,
                    name=template.name, amount_ore=125000, due_date=self.today, accounting_class=accounting_class)
                row = self.draft()
                row.ocr_text = 'Synthetic secret OCR ' + module
                row.save()
                DocumentJob.objects.filter(document=row).update(status='ready')
                version, key = row.version, uuid.uuid4()
                docs.confirm(self.user, row.pk, version, key, 'link_bill', bill.pk)
                detail = reverse('document_detail', args=[row.pk])
                self.assertContains(self.client.get(detail), 'Testbutikk')
                self.assertNotContains(self.client.get(detail), row.ocr_text)
                self.member.module_access = {module: False}
                self.member.save()
                response = self.client.get(detail)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, row.ocr_text, status_code=404)
                self.assertEqual(self.client.get(reverse('document_original', args=[row.pk])).status_code, 404)
                self.assertEqual(self.client.post(detail, {'form': 'confirm', 'version': version, 'key': key,
                    'action': 'link_bill', 'bill': bill.pk, 'confirmation': 'on'}).status_code, 404)
                with self.assertRaises(PermissionDenied):
                    docs.confirm(self.user, row.pk, version, key, 'link_bill', bill.pk)
                row.refresh_from_db()
                self.assertEqual(row.bill_id, bill.pk)
                self.assertEqual(row.version, version + 1)
        self.assertEqual(BillOccurrence.objects.count(), 3)
        self.assertFalse(Entry.objects.exists())
