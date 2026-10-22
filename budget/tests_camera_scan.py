"""Camera contract regression tests. Native OCR/runtime tests run separately."""
from datetime import timedelta
import os
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import document_ocr as ocr, document_services as service, document_spool as spool
from .models import Document, DocumentJob, Entry, BillOccurrence
from . import tests_documents as document_tests
from .tests_documents import png


class ScanParserTests(SimpleTestCase):
    def test_native_quality_filter_withholds_doubtful_whole_line(self):
        header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n'
        words = ['5\t1\t1\t1\t1\t1\t95\tMerchant',
                 '5\t1\t1\t1\t2\t1\t95\tTotal:',
                 '5\t1\t1\t1\t2\t2\t70.9\t110,09']
        filtered = ocr.readable_lines(header + '\n'.join(words))
        self.assertEqual(filtered, 'Merchant\nÅ betale: ?')
        self.assertNotIn('amount', ocr.suggestions(filtered))
        self.assertNotIn('110,09', filtered)
        self.assertNotIn('supplier', ocr.suggestions('…\nCustomer Name'))

    def test_uncertain_line_cannot_expose_weaker_total_or_date(self):
        header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n'
        rows = ['5\t1\t1\t1\t1\t1\t95\tMerchant',
                '5\t1\t1\t1\t2\t1\t95\tA betale:',
                '5\t1\t1\t1\t2\t2\t70\t110,09',
                '5\t1\t1\t1\t3\t1\t95\tTotal: 100,00',
                '5\t1\t1\t1\t4\t1\t70\tDato: 22.10.2026',
                '5\t1\t1\t1\t5\t1\t95\tDato: 21.10.2026',
                '5\t1\t1\t1\t6\t1\t70\tButikk: Uncertain']
        candidates = ocr.suggestions(ocr.readable_lines(header + '\n'.join(rows)))
        for field in ('amount', 'document_date', 'supplier'):
            self.assertNotIn(field, candidates)
            self.assertIn(field, candidates['ambiguous'])
        self.assertEqual(ocr.readable_lines('not TSV'), '')
        self.assertEqual(ocr.readable_lines(header + rows[1].replace('95', 'nan')), '')

    def test_unknown_doubtful_line_blocks_numeric_fallback_without_label_guessing(self):
        header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n'
        for uncertain in ('A betaie: 1250,00', 'D?to 22.10.2026', 'unclassifiable words'):
            rows = ['5\t1\t1\t1\t1\t1\t95\tMerchant',
                    '5\t1\t1\t1\t2\t1\t50\t' + uncertain,
                    '5\t1\t1\t1\t3\t1\t95\tTotal: 1000,00',
                    '5\t1\t1\t1\t4\t1\t95\tDato: 21.10.2026']
            candidates = ocr.suggestions(ocr.readable_lines(header + '\n'.join(rows)))
            self.assertEqual(candidates['supplier'], 'Merchant')
            for field in ('amount', 'document_date', 'due_date'):
                self.assertNotIn(field, candidates)
                self.assertIn(field, candidates['ambiguous'])

    def test_invalid_tsv_structure_is_not_parsed_as_candidate_text(self):
        self.assertEqual(ocr.readable_lines('level\tconf\ttext\n5\t95\tTotal: 1000,00'), '')
        header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n'
        good = '5\t1\t1\t1\t1\t1\t95\tTotal: 1000,00'
        for bad in (good.replace('5\t1', '5\t0', 1), good.replace('5\t1', '5\tx', 1),
                    good + '\tunexpected', good + '\n' + good, good.rsplit('\t', 1)[0]):
            self.assertEqual(ocr.readable_lines(header + bad), '')

    def test_native_output_overflow_fails_instead_of_parsing_partial_text(self):
        def emit(arguments, **kwargs):
            kwargs['stdout'].write(b'x' * 200_001)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_SCAN_ROOT=directory):
            with patch.object(ocr.subprocess, 'run', side_effect=emit):
                with self.assertRaises(ValueError): ocr.run(['synthetic'])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_ascii_payable_label_keeps_priority_without_guessing_digits(self):
        self.assertEqual(ocr.suggestions('Subtotal 1000,00\nMVA 250,00\nA betale: 1250,00')['amount'], '1250,00')
        self.assertNotIn('amount', ocr.suggestions('Total 1000,00\nA betale: 1?50,00'))

    def test_total_preference_and_conflicts(self):
        data = ocr.suggestions('Nordby Testbutikk\nSubtotal 100,00\nMVA 25,00\nTotal 125,00\nÅ betale 120,00\nKontant 200,00\nTilbake 80,00')
        self.assertEqual(data['amount'], '120,00')
        self.assertEqual(data['supplier'], 'Nordby Testbutikk')
        self.assertTrue(data['merchant_heading'])
        data = ocr.suggestions('Total 125,00\nTotal 129,00')
        self.assertNotIn('amount', data)
        self.assertIn('amount', data['ambiguous'])

    def test_document_title_may_precede_uncertain_merchant_heading(self):
        for title in ('FAKTURA', 'KVITTERING', 'FIKTIV TESTFAKTURA', 'INVOICE'):
            data = ocr.suggestions(title + '\nNordby Testbutikk AS\nFakturanr: 123\nTotal 125,00')
            self.assertEqual(data['supplier'], 'Nordby Testbutikk AS')
            self.assertTrue(data['merchant_heading'])
            self.assertNotIn('supplier', ocr.suggestions(title))
        self.assertNotIn('supplier', ocr.suggestions('FAKTURA\nFakturanr: 123\nCustomer Name'))

    def test_malformed_payable_does_not_fall_back_to_weaker_total(self):
        self.assertNotIn('amount', ocr.suggestions('Total 125,00\nÅ betale 12,50,99'))
        for value in ('0,00', '-12,50', '1.250,001'):
            self.assertNotIn('amount', ocr.suggestions('SUM ' + value))

    def test_dates_are_valid_and_due_date_never_becomes_purchase_date(self):
        self.assertEqual(ocr.suggestions('Dato: 22.10.2026\nForfall: 30.10.2026')['document_date'], '22.10.2026')
        self.assertNotIn('document_date', ocr.suggestions('Forfall: 30.10.2026'))
        self.assertNotIn('document_date', ocr.suggestions('Dato: 31.02.2026'))
        self.assertNotIn('document_date', ocr.suggestions('Dato: 22.10.2026\nDato: 23.10.2026'))
        self.assertEqual(ocr.suggestions('22.10.2026 12:30')['document_date'], '22.10.2026')

    def test_payee_conflicts_and_unneeded_data_not_retained(self):
        data = ocr.suggestions('Butikk: One\nButikk: Two\nKID: 123456789\nFakturanummer: secret')
        self.assertNotIn('supplier', data)
        self.assertNotIn('kid', data)
        self.assertNotIn('invoice_number', data)
        self.assertIn('supplier', data['ambiguous'])

    def test_spool_orphan_cleanup_never_visits_legacy_or_new_files(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_SCAN_ROOT=Path(directory)/'scans'):
            legacy = Path(directory)/'legacy'
            legacy.mkdir()
            (legacy/'preserve').write_bytes(b'legacy')
            old, current, referenced = [spool.store(b'synthetic') for _ in range(3)]
            for key in (old, referenced): os.utime(spool.path_for(key), (0, 0))
            with spool.scratch() as scratch:
                (scratch/'decoder').write_bytes(b'synthetic')
                # Normal exit also disposes scratch.
            self.assertFalse(scratch.exists())
            spool.sweep_orphans({referenced})
            self.assertFalse(spool.path_for(old).exists())
            self.assertTrue(spool.path_for(current).exists())
            self.assertTrue(spool.path_for(referenced).exists())
            self.assertEqual((legacy/'preserve').read_bytes(), b'legacy')
            with self.assertRaises(ValidationError): spool.path_for('../legacy/preserve')

    def test_financial_history_labels_scans_and_preserves_legacy_names(self):
        from types import SimpleNamespace
        from django.template.loader import render_to_string
        rows = [SimpleNamespace(pk=uuid.uuid4(), transient=True, supplier='Testbutikk', filename=''),
                SimpleNamespace(pk=uuid.uuid4(), transient=True, supplier='', filename=''),
                SimpleNamespace(pk=uuid.uuid4(), transient=False, supplier='Ignored', filename='legacy.png')]
        rendered = render_to_string('budget/workflow_links.html', {'documents': rows})
        self.assertIn('Skanning: Testbutikk', rendered)
        self.assertIn('Skanning: Gjennomgåtte detaljer', rendered)
        self.assertIn('Dokument: legacy.png', rendered)
        for row in rows:
            self.assertIn(reverse('document_detail', args=[row.pk]), rendered)

    def test_camera_templates_compile(self):
        from django.template.loader import get_template
        for name in ('documents', 'document_detail'):
            get_template('budget/' + name + '.html')


class ScanLifecycleTests(TestCase):
    setUp = document_tests.DocumentTests.setUp
    upload = document_tests.DocumentTests.upload
    draft = document_tests.DocumentTests.draft

    def test_success_persists_candidates_before_disposal_without_money(self):
        row = self.upload()
        path = spool.path_for(row.storage_key)
        real_discard = spool.discard
        def inspect_discard(key):
            saved = Document.objects.get(pk=row.pk)
            self.assertTrue(saved.cleanup_pending)
            self.assertEqual(saved.suggestions['amount'], '125,00')
            self.assertEqual(saved.ocr_text, '')
            real_discard(key)
        with patch.object(ocr, 'recognize', return_value='Testbutikk\nTotal 125,00\nDato: 22.10.2026'), patch.object(spool, 'discard', side_effect=inspect_discard):
            self.assertTrue(ocr.process_one())
        row.refresh_from_db()
        self.assertFalse(path.exists())
        self.assertIsNotNone(row.photo_deleted_at)
        self.assertFalse(row.cleanup_pending)
        self.assertEqual(row.filename, '')
        self.assertEqual(row.job.status, 'ready')
        self.assertFalse(Entry.objects.exists())
        self.assertFalse(BillOccurrence.objects.exists())

    def test_cleanup_retry_keeps_candidates_and_never_reruns_ocr(self):
        row = self.upload()
        with patch.object(ocr, 'recognize', return_value='Total 125,00'), patch.object(spool, 'discard', side_effect=OSError):
            ocr.process_one()
        row.refresh_from_db()
        self.assertTrue(row.cleanup_pending)
        self.assertEqual(row.suggestions['amount'], '125,00')
        with patch.object(ocr, 'recognize') as recognize:
            self.assertFalse(ocr.process_one())
            recognize.assert_not_called()
        row.refresh_from_db()
        self.assertFalse(row.cleanup_pending)
        self.assertFalse(spool.path_for(row.storage_key).exists())

    def test_expiry_discards_queued_photo_and_keeps_manual_draft(self):
        row = self.draft()
        Document.objects.filter(pk=row.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with patch.object(ocr, 'recognize') as recognize:
            self.assertFalse(ocr.process_one())
            recognize.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.job.status, 'failed')
        self.assertEqual(row.supplier, 'Testbutikk')
        self.assertFalse(spool.path_for(row.storage_key).exists())
        self.assertFalse(Entry.objects.exists())

    def test_cancel_during_processing_invalidates_worker_generation(self):
        row = self.draft()
        def recognize(_):
            service.cancel(self.user, row.pk, row.version, uuid.uuid4())
            return 'Total 999,00\nButikk: Stale result'
        with self.captureOnCommitCallbacks(execute=True), patch.object(ocr, 'recognize', side_effect=recognize):
            ocr.process_one()
        row.refresh_from_db()
        self.assertTrue(row.cancelled)
        self.assertEqual(row.suggestions, {})
        self.assertEqual(row.supplier, '')
        self.assertEqual(row.job.status, 'cancelled')
        self.assertFalse(spool.path_for(row.storage_key).exists())
        with self.assertRaises(ValidationError): service.confirm(self.user, row.pk, row.version, uuid.uuid4(), 'expense')
        self.assertFalse(Entry.objects.exists())

    def test_cancel_after_confirmation_cannot_delete_post(self):
        row = self.draft()
        row = service.confirm(self.user, row.pk, row.version, uuid.uuid4(), 'expense')
        with self.assertRaises(ValidationError): service.cancel(self.user, row.pk, row.version, uuid.uuid4())
        self.assertEqual(Entry.objects.count(), 1)

    def test_expired_lease_can_recover_before_photo_ttl(self):
        row = self.upload()
        DocumentJob.objects.filter(document=row).update(status='running', attempts=1, lease_until=timezone.now()-timedelta(seconds=1))
        with patch.object(ocr, 'recognize', return_value='Total 125,00'):
            self.assertTrue(ocr.process_one())
        row.refresh_from_db()
        self.assertEqual(row.job.status, 'ready')
        self.assertFalse(spool.path_for(row.storage_key).exists())

    def test_terminal_interruption_discards_photo(self):
        row = self.upload()
        DocumentJob.objects.filter(document=row).update(status='running', attempts=3, lease_until=timezone.now()-timedelta(seconds=1))
        ocr.sweep()
        row.refresh_from_db()
        self.assertEqual(row.job.status, 'failed')
        self.assertFalse(spool.path_for(row.storage_key).exists())

    def test_legacy_original_is_untouched_by_sweep_and_still_accessible(self):
        from .document_storage import store, path_for
        key = store(self.house.pk, png())
        row = Document.objects.create(household=self.house, created_by=self.user, storage_key=key,
            filename='legacy.png', sha256='a'*64, size=len(png()), content_type='image/png')
        DocumentJob.objects.create(document=row, status='ready')
        os.utime(path_for(key), (0, 0))
        ocr.sweep()
        self.assertEqual(path_for(key).read_bytes(), png())
        response = self.client.get(reverse('document_original', args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), png())

    def test_blank_scan_cannot_link_or_become_immutable(self):
        target = Entry.objects.create(household=self.house, created_by=self.user, kind='expense',
            amount_ore=125000, effective_date=self.today, description='Existing', category=self.category)
        row = self.upload()
        with self.assertRaises(ValidationError):
            service.confirm(self.user, row.pk, row.version, uuid.uuid4(), 'link_entry', target.pk)
        row.refresh_from_db()
        self.assertFalse(row.confirmed)
        self.assertIsNone(row.entry_id)
        self.assertEqual(Entry.objects.count(), 1)

    def test_manual_entry_and_pdf_rejection(self):
        row = service.manual(self.user, uuid.uuid4())
        self.assertIsNotNone(row.photo_deleted_at)
        service.save_draft(self.user, row.pk, row.version, uuid.uuid4(), supplier='Manual')
        with self.assertRaises(ValidationError):
            from .document_storage import inspect_content
            inspect_content(b'%PDF-1.7\n%%EOF', image_only=True)
        response = self.client.get(reverse('documents'))
        self.assertContains(response, 'camera-preview')
        self.assertContains(response, 'Fyll inn manuelt')
        self.assertNotContains(response, 'Last opp privat dokument')


class ConcurrentScanCancellationTests(document_tests.TransactionTestCase):
    setUp = document_tests.DocumentTests.setUp
    upload = document_tests.DocumentTests.upload
    draft = document_tests.DocumentTests.draft

    def test_cancel_and_confirm_serialize_without_partial_financial_state(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connection, close_old_connections
        row = self.draft()
        barrier = Barrier(2)
        def attempt(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                try:
                    if operation == 'cancel': service.cancel(self.user, row.pk, row.version, uuid.uuid4())
                    else: service.confirm(self.user, row.pk, row.version, uuid.uuid4(), 'expense')
                    return pid, operation
                except ValidationError:
                    return pid, 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ['cancel', 'confirm']))
        self.assertEqual(len({pid for pid, _ in results}), 2)
        self.assertEqual([value for _, value in results].count('conflict'), 1)
        row.refresh_from_db()
        self.assertNotEqual(row.cancelled, row.confirmed)
        self.assertEqual(Entry.objects.count(), int(row.confirmed))
        self.assertEqual(row.entry_id is not None, row.confirmed)
