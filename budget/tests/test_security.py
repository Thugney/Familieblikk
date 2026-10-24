"""Synthetic security regressions, including real PostgreSQL transactions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
import tempfile
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from budget import forms, identity, services
from budget.financial_projection import month_basis
from budget.middleware import PrivateResponseMiddleware
from budget.models import Asset, BillOccurrence, BillTemplate, Document, DocumentJob, LoginCode, LoginRequest, MonthPlan, PasswordAttempt
from budget.spending_services import commitments, fund_available_before
from budget.tests.financial_support import enter_fixture_area
from budget.tests.test_domain import setup_family
from budget.tests.test_preregistered_auth import PASSWORD, binding
from budget.work_limits import FinancialWorkLimit, MAX_MONTH_STEPS


class PasswordSecurityTests(TestCase):
    def test_exhausted_email_or_ip_skips_account_lookup_and_hashing(self):
        email, ip = 'blocked@example.test', '192.0.2.4'
        for dimension, count in [('email', 5), ('ip', 30)]:
            with self.subTest(dimension=dimension):
                PasswordAttempt.objects.all().delete()
                PasswordAttempt.objects.bulk_create([
                    PasswordAttempt(email_digest=identity.digest('password-email:' + (email if dimension == 'email' else f'{n}@example.test')),
                                    ip_digest=identity.digest('password-ip:' + (ip if dimension == 'ip' else str(n))),
                                    attempted_at=timezone.now()) for n in range(count)])
                with patch('django.contrib.auth.hashers.make_password') as dummy, patch.object(get_user_model(), 'check_password') as check:
                    with CaptureQueriesContext(connection) as queries, self.assertRaisesMessage(ValidationError, identity.LOGIN_ERROR):
                        identity.password_login(RequestFactory().post('/passord/'), email, PASSWORD, ip)
                    dummy.assert_not_called()
                    check.assert_not_called()
                sql = '\n'.join(q['sql'] for q in queries.captured_queries)
                self.assertNotIn('budget_membership', sql)
                self.assertNotIn('auth_user', sql)
                self.assertEqual(PasswordAttempt.objects.count(), count)

    def test_oversized_password_rejected_in_form_and_service_before_work(self):
        data = {'email': 'synthetic@example.test', 'password': 'x' * 1025}
        form = forms.PasswordLoginForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn(identity.LOGIN_ERROR, form.errors['password'])
        self.assertTrue(forms.PasswordLoginForm({**data, 'password': 'x' * 1024}).is_valid())
        with patch('django.contrib.auth.hashers.make_password') as dummy, self.assertNumQueries(0):
            with self.assertRaises(ValidationError):
                identity.password_login(RequestFactory().post('/passord/'), data['email'], data['password'], '192.0.2.1')
            dummy.assert_not_called()
        self.assertFalse(forms.CodeForm({'email': data['email'], 'code': '1' * 10000}).is_valid())
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            identity.verify_code(RequestFactory().post('/kode/'), data['email'], '1' * 10000)

    def test_valid_login_rotates_session_and_proxy_headers_do_not_override_ip(self):
        member, _ = identity.provision_owner(binding(), PASSWORD, 'Synthetic household')
        session = self.client.session
        session['before'] = True
        session.save()
        old_key = session.session_key
        response = self.client.post('/passord/', {'email': member.user.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.client.session.session_key, old_key)
        with patch('budget.identity.password_login', side_effect=ValidationError(identity.LOGIN_ERROR)) as login:
            self.client.post('/passord/', {'email': member.user.email, 'password': PASSWORD},
                             REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='203.0.113.1', HTTP_CF_CONNECTING_IP='203.0.113.2')
            self.assertEqual(login.call_args.args[-1], '192.0.2.1')
        self.assertEqual(Client(enforce_csrf_checks=True).post('/passord/', {'email': member.user.email, 'password': PASSWORD}).status_code, 403)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CodeConcurrencySecurityTests(TransactionTestCase):
    def concurrent_send(self, pairs):
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(len(pairs))
        def send(pair):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                identity.send_code(*pair)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
            list(pool.map(send, pairs))

    def test_first_code_and_sixty_second_cooldown_are_serialized(self):
        self.concurrent_send([('same@example.test', f'192.0.2.{n}') for n in range(4)])
        self.assertEqual(LoginRequest.objects.count(), 1)
        self.assertEqual(LoginCode.objects.count(), 1)

    def test_shared_ip_cannot_exceed_hourly_quota_with_different_emails(self):
        ip = '192.0.2.1'
        LoginRequest.objects.bulk_create([LoginRequest(email_digest=identity.digest(f'old{n}@example.test'), ip_digest=identity.digest(ip), sent_at=timezone.now()) for n in range(19)])
        self.concurrent_send([(f'new{n}@example.test', ip) for n in range(4)])
        self.assertEqual(LoginRequest.objects.count(), 20)
        self.assertEqual(LoginCode.objects.count(), 1)

    def test_email_hourly_quota_is_shared_across_different_ips(self):
        email = 'same@example.test'
        LoginRequest.objects.bulk_create([LoginRequest(email_digest=identity.digest(email), ip_digest=identity.digest(f'192.0.2.{n}'), sent_at=timezone.now() - timedelta(minutes=2)) for n in range(4)])
        self.concurrent_send([(email, f'192.0.2.{n}') for n in range(4)])
        self.assertEqual(LoginRequest.objects.count(), 5)
        LoginCode.objects.update(sent_at=timezone.now() - timedelta(minutes=2))
        self.concurrent_send([(email, f'198.51.100.{n}') for n in range(4)])
        self.assertEqual(LoginRequest.objects.count(), 5)


class FinancialWorkSecurityTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family()
        enter_fixture_area(self, self.user)
        self.month = timezone.localdate().replace(day=1)
        self.client.force_login(self.user)

    def bill(self, first=None):
        return BillTemplate.objects.create(household=self.house, created_by=self.user, category=self.category,
            name='Synthetic bill', amount_ore=1200, first_due=first or self.month, monthly=True)

    def test_extreme_url_and_direct_service_do_no_materialization(self):
        self.bill()
        for period in ('9999-12', '0001-01'):
            with self.subTest(period=period), patch('budget.services.prepare_month') as prepare:
                self.assertEqual(self.client.get('/app/oversikt/', {'month': period}).status_code, 404)
                self.assertEqual(self.client.get('/app/budsjett/', {'month': period}).status_code, 404)
                self.assertEqual(self.client.get('/app/plan/data/', {'target_month': period}).status_code, 400)
                prepare.assert_not_called()
        with self.assertRaises(FinancialWorkLimit): services.prepare_month(self.house, date(9999, 12, 1))
        self.assertFalse(BillOccurrence.objects.exists())
        self.assertFalse(MonthPlan.objects.exists())

    def test_ancient_bill_anchor_fails_before_other_writes_and_returns_400(self):
        self.bill()
        malicious = self.bill(date(1, 1, 1))
        Asset.objects.create(household=self.house, created_by=self.user, kind='fund', name='Implicit plan', opening_date=self.month, target_ore=12000)
        with patch('budget.services.materialize_template') as materialize:
            with self.assertRaises(FinancialWorkLimit): services.prepare_month(self.house, self.month)
            materialize.assert_not_called()
        self.assertFalse(MonthPlan.objects.exists())
        self.assertFalse(BillOccurrence.objects.exists())
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 400)
        for action in (lambda: services.materialize_template(malicious, self.month), lambda: month_basis(self.house, self.month), lambda: commitments(self.house, self.month)):
            with self.assertRaises(FinancialWorkLimit): action()

    def test_ancient_plan_and_fund_and_debt_anchors_are_bounded(self):
        fund = Asset.objects.create(household=self.house, created_by=self.user, kind='fund', name='Fund', opening_date=date(1, 1, 1), target_ore=12000)
        for action in (lambda: services.prepare_month(self.house, self.month), lambda: month_basis(self.house, self.month), lambda: fund_available_before(self.house, fund, self.month)):
            with self.assertRaises(FinancialWorkLimit): action()
        self.assertFalse(MonthPlan.objects.exists())
        fund.opening_date = self.month
        fund.save()
        MonthPlan.objects.create(household=self.house, created_by=self.user, asset=fund, month=date(1, 1, 1), amount_ore=100, derived=True)
        with self.assertRaises(FinancialWorkLimit): month_basis(self.house, self.month)
        debt = Asset.objects.create(household=self.house, created_by=self.user, kind='debt', name='Debt', opening_date=date(1, 1, 1), annual_rate=5)
        with self.assertRaises(FinancialWorkLimit): services.estimated_debt_balance(debt, self.month)

    def test_total_work_is_rejected_before_any_occurrence_write(self):
        first = self.month.replace(year=self.month.year - 10)
        count = MAX_MONTH_STEPS // 121 + 1
        BillTemplate.objects.bulk_create([BillTemplate(household=self.house, financial_area=self.area, created_by=self.user,
            category=self.category, name=f'Series {n}', amount_ore=1200, first_due=first, monthly=True) for n in range(count)])
        with self.assertRaises(FinancialWorkLimit): services.prepare_month(self.house, self.month)
        with self.assertRaises(FinancialWorkLimit): month_basis(self.house, self.month)
        self.assertFalse(BillOccurrence.objects.exists())

    def test_normal_current_and_next_month_match_projection_and_isolate_families(self):
        self.bill()
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category, month=self.month, amount_ore=5000)
        for month in (self.month, services.next_month(self.month)):
            before = month_basis(self.house, month)
            services.prepare_month(self.house, month)
            after = month_basis(self.house, month)
            self.assertEqual(before['category_limits'], after['category_limits'])
            self.assertEqual(sum(x['amount_ore'] for x in before['pending']), sum(x['amount_ore'] for x in after['pending']))
        self.assertEqual(BillOccurrence.objects.count(), 2)
        _, foreign, _ = setup_family('foreign@example.test')
        with self.assertRaises(PermissionDenied): services.prepare_month(foreign, self.month)
        with self.assertRaises(PermissionDenied): month_basis(foreign, self.month)

    def test_cumulative_request_limit_rolls_back_and_resets_for_next_request(self):
        self.bill()
        # Overview invokes materialization, calculation and its explanatory
        # projection: each alone fits, but the whole request must fit as well.
        with patch('budget.work_limits.MAX_MONTH_STEPS', 2):
            self.assertEqual(self.client.get('/app/oversikt/').status_code, 400)
        self.assertFalse(BillOccurrence.objects.exists())
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 200)
        self.assertEqual(BillOccurrence.objects.count(), 1)

    def test_old_one_off_bill_uses_one_step_and_retains_its_amount(self):
        row = self.bill(date(1, 1, 1))
        row.monthly = False
        row.save()
        with patch('budget.work_limits.MAX_MONTH_STEPS', 1):
            services.prepare_month(self.house, self.month)
        self.assertEqual(BillOccurrence.objects.get(template=row).amount_ore, 1200)
        with patch('budget.work_limits.MAX_MONTH_STEPS', 1):
            self.assertEqual(sum(row['amount_ore'] for row in month_basis(self.house, self.month)['pending']), 1200)

    def test_debt_dates_only_guard_actual_interest_replay(self):
        missing_rate = Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
            name='Unknown rate', opening_date=date(1, 1, 1), opening_ore=10000)
        archived = Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
            name='Old archived debt', opening_date=date(1, 1, 1), opening_ore=10000, annual_rate=5, archived=True)
        future = Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
            name='Future opening', opening_date=date(9999, 1, 1), opening_ore=10000, annual_rate=5)
        with self.assertNumQueries(0):
            self.assertIsNone(services.estimated_debt_balance(missing_rate, date(9999, 1, 1)))
            self.assertIsNone(services.estimated_debt_balance(future, self.month))
        # These paths need plans/bills, not debt interest. An old archived asset
        # must not block unrelated budget views simply because it exists.
        services.prepare_month(self.house, self.month)
        self.assertEqual(month_basis(self.house, self.month)['pending'], [])
        with self.assertRaises(FinancialWorkLimit): services.estimated_debt_balance(archived, self.month)

    def test_actual_debt_as_of_and_allocation_share_cumulative_budget(self):
        from budget.work_limits import financial_work_scope
        first = (self.month - timedelta(days=32)).replace(day=1)
        debts = [Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
            name=f'Debt {number}', opening_date=first, opening_ore=10000, minimum_ore=100, annual_rate=5)
            for number in range(2)]
        with patch('budget.work_limits.MAX_MONTH_STEPS', 3), financial_work_scope():
            month_basis(self.house, first)  # Selected month has no interest work.
            self.assertGreater(services.estimated_debt_balance(debts[0], self.month), 10000)
            with self.assertRaises(FinancialWorkLimit): services.estimated_debt_balance(debts[1], self.month)
        # A standalone allocation must inherit one operation budget too, even
        # without HTTP middleware or the broad budget-page preflight.
        with patch('budget.work_limits.MAX_MONTH_STEPS', 3), self.assertRaises(FinancialWorkLimit):
            services.allocate_debt_plan(self.user, self.month, 'avalanche', 0)
        self.assertFalse(MonthPlan.objects.exists())

    def test_all_future_derived_rows_are_budgeted_before_refresh_and_roll_back_save(self):
        anchor = MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
            month=self.month, amount_ore=5000)
        cursor = self.month
        copies = []
        for _ in range(3):
            cursor = services.next_month(cursor)
            copies.append(MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
                month=cursor, amount_ore=111, derived=True))
        with patch('budget.work_limits.MAX_MONTH_STEPS', 2), self.assertRaises(FinancialWorkLimit):
            services.refresh_future_plans(self.house)
        self.assertEqual(list(MonthPlan.objects.filter(derived=True).values_list('amount_ore', flat=True)), [111] * 3)
        anchor.amount_ore = 6000
        with patch('budget.work_limits.MAX_MONTH_STEPS', 2), self.assertRaises(FinancialWorkLimit):
            services.save_row(self.user, anchor, expected_version=anchor.version)
        anchor.refresh_from_db()
        self.assertEqual((anchor.amount_ore, anchor.version), (5000, 1))
        self.assertEqual(list(MonthPlan.objects.filter(derived=True).values_list('amount_ore', flat=True)), [111] * 3)

    def test_old_asset_can_be_renamed_archived_but_not_given_a_new_extreme_anchor(self):
        row = Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
            name='Old retained asset', opening_date=date(1, 1, 1), opening_ore=10000)
        row.name = 'Renamed retained asset'
        services.save_row(self.user, row, expected_version=row.version)
        row.archived = True
        services.save_row(self.user, row, expected_version=row.version)
        row.refresh_from_db()
        self.assertEqual(row.name, 'Renamed retained asset')
        self.assertTrue(row.archived)
        self.assertEqual(row.opening_date, date(1, 1, 1))
        row.opening_date = date(2, 1, 1)
        with self.assertRaises(FinancialWorkLimit): services.save_row(self.user, row, expected_version=row.version)
        row.refresh_from_db()
        self.assertEqual(row.opening_date, date(1, 1, 1))
        new = Asset(kind='debt', name='New invalid anchor', opening_date=date(1, 1, 1), opening_ore=10000)
        with self.assertRaises(FinancialWorkLimit): services.save_row(self.user, new)
        self.assertEqual(Asset.objects.count(), 1)


class ResponseSecurityTests(TestCase):
    def test_csp_and_permissions_on_html_api_static_worker_and_errors(self):
        for path in ('/passord/', '/app/forbruk/data/', '/static/budget/app.js', '/sw.js', '/does-not-exist/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                csp = response['Content-Security-Policy']
                self.assertIn("script-src 'self';", csp)
                self.assertIn("frame-ancestors 'none'", csp)
                self.assertIn("object-src 'none'", csp)
                self.assertIn("base-uri 'none'", csp)
                self.assertIn("worker-src 'self'", csp)
                self.assertIn("img-src 'self' data: blob:", csp)
                self.assertNotIn('unsafe-eval', csp)
                self.assertIn('camera=(self)', response['Permissions-Policy'])
                if not path.startswith('/static/') and path != '/sw.js':
                    self.assertIn('no-store', response['Cache-Control'])
        csrf = Client(enforce_csrf_checks=True).post('/passord/', {})
        self.assertEqual(csrf.status_code, 403)
        self.assertIn('Content-Security-Policy', csrf)

    def test_vary_is_preserved(self):
        def downstream(request):
            response = HttpResponse('Synthetic')
            response['Vary'] = 'Accept-Encoding, Origin'
            return response
        response = PrivateResponseMiddleware(downstream)(RequestFactory().get('/app/'))
        self.assertEqual(set(response['Vary'].split(', ')), {'Accept-Encoding', 'Origin', 'Cookie'})


class DecoderSecurityTests(TestCase):
    def test_native_decoder_invocation_does_not_inherit_secrets(self):
        from budget import document_ocr
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'DJANGO_SECRET_KEY': 'sentinel-secret', 'POSTGRES_PASSWORD': 'sentinel-password',
                                         'UNRELATED_TOKEN': 'sentinel-token', 'PATH': 'synthetic-path', 'SYSTEMROOT': 'synthetic-system'}):
                with patch('budget.document_ocr.document_spool.scratch', return_value=nullcontext(Path(directory))), patch('budget.document_ocr.subprocess.run') as execute:
                    self.assertEqual(document_ocr.run(['synthetic-decoder']), '')
                    environment = execute.call_args.kwargs['env']
                    self.assertNotIn('DJANGO_SECRET_KEY', environment)
                    self.assertNotIn('POSTGRES_PASSWORD', environment)
                    self.assertNotIn('UNRELATED_TOKEN', environment)
                    self.assertEqual(environment['PATH'], 'synthetic-path')
                    self.assertEqual(environment['SYSTEMROOT'], 'synthetic-system')
                    self.assertEqual(environment['TMPDIR'], directory)
                    self.assertEqual(environment['TMP'], directory)
                    self.assertEqual(environment['TEMP'], directory)
                    self.assertEqual(environment['OMP_THREAD_LIMIT'], '1')

    def test_queued_legacy_pdf_requires_manual_review_without_decoding_or_deletion(self):
        from budget import document_ocr, document_storage
        user, house, _ = setup_family()
        enter_fixture_area(self, user)
        original = b'%PDF-1.7\nsynthetic preserved original\n%%EOF'
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_DOCUMENT_ROOT=directory, PRIVATE_SCAN_ROOT=directory + '/scans'):
            key = document_storage.store(house.pk, original)
            document = Document.objects.create(household=house, created_by=user, content_type='application/pdf',
                storage_key=key, size=len(original), supplier='Retained manual supplier', amount_ore=1200,
                ocr_text='Retained old text', suggestions={'supplier': 'Retained suggestion'})
            job = DocumentJob.objects.create(document=document)
            with patch('budget.document_ocr.run') as decoder:
                self.assertTrue(document_ocr.process_one())
                decoder.assert_not_called()
            document.refresh_from_db()
            job.refresh_from_db()
            self.assertEqual(job.status, 'failed')
            self.assertIn('fyll inn feltene manuelt', job.error)
            self.assertIsNone(job.lease_until)
            self.assertEqual(document.supplier, 'Retained manual supplier')
            self.assertEqual(document.amount_ore, 1200)
            self.assertEqual(document.ocr_text, 'Retained old text')
            self.assertEqual(document.suggestions, {'supplier': 'Retained suggestion'})
            self.assertFalse(document.cleanup_pending)
            self.assertIsNone(document.photo_deleted_at)
            self.assertEqual(document_storage.path_for(key).read_bytes(), original)
