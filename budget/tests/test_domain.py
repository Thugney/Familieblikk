from budget.area_requests import financial_url
from budget.tests.financial_support import enter_fixture_area
import uuid
from unittest.mock import patch
from datetime import date, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from budget import identity, importing, services
from budget.financial_areas import create_area, area_scope
from budget.financial_models import FinancialAreaGrant
from budget.models import Asset, BillOccurrence, BillTemplate, Category, Entry, Household, ImportBatch, ImportRecord, LoginCode, Membership, MonthPlan


def setup_family(email='owner@example.test'):
    user = get_user_model().objects.create_user(username=email, email=email)
    house = Household.objects.create(name='Testfamilie')
    membership = Membership.objects.create(user=user, household=house, role='admin', verified_at=timezone.now())
    user.test_area = create_area(membership, 'Testbudsjett', kind='shared')
    with area_scope(membership, user.test_area.pk):
        category = Category.objects.create(household=house, created_by=user, name='Mat')
    return user, house, category


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DomainTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family()
        self.other, self.foreign, self.foreign_category = setup_family('foreign@example.test')
        enter_fixture_area(self, self.user)
        self.today = timezone.localdate()
        self.month = services.month_start(self.today)
        self.member = get_user_model().objects.create_user(username='member@example.test', email='member@example.test')
        member = Membership.objects.create(user=self.member, household=self.house, role='member', verified_at=timezone.now())
        FinancialAreaGrant.objects.create(area=self.area, member=member, role='reader')

    def entry(self, kind, amount, **kwargs):
        return services.save_entry(self.user, Entry(kind=kind, amount_ore=amount, description='Kontrollpost', effective_date=self.today, category=self.category, **kwargs))

    def asset(self, kind='savings', **kwargs):
        return Asset.objects.create(household=self.house, created_by=self.user, kind=kind, name='Kontrollmål', opening_date=self.month, **kwargs)

    def test_new_household_has_no_fixture_or_other_family_data(self):
        self.assertFalse(Entry.objects.filter(household=self.foreign).exists())
        row = self.entry('income', 10000)
        self.client.force_login(self.other)
        response = self.client.get(f'/endre/entry/{row.pk}/')
        self.assertEqual(response.status_code, 404)
        response = self.client.get('/app/oversikt/')
        self.assertNotContains(response, 'Kontrollpost')
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')

    def test_roles_conflict_and_cross_household_relations(self):
        row = self.entry('expense', 100)
        with self.assertRaises(PermissionDenied): services.save_entry(self.member, row, row.version)
        row.description = 'Endret'
        services.save_entry(self.user, row, 1)
        with self.assertRaises(services.Conflict): services.save_entry(self.user, row, 1)
        with area_scope(Membership.objects.get(user=self.other), self.other.test_area.pk):
            foreign_asset = Asset.objects.create(household=self.foreign, created_by=self.other, kind='savings', name='Fremmed mål', opening_date=self.month)
        with self.assertRaises(ValidationError): self.entry('expense', 10, asset=foreign_asset)
        with self.assertRaises((IntegrityError, ValidationError)), transaction.atomic():
            Entry.objects.create(household=self.house, created_by=self.user, kind='expense', amount_ore=10, effective_date=self.today, description='Ulovlig', category=self.foreign_category)

    def test_received_income_and_net_savings_per_goal(self):
        self.entry('income', 6200000)
        self.entry('income', 500000, received=False)
        self.entry('expense', 2845000)
        goal = self.asset(opening_ore=100000)
        goal2 = self.asset()
        for asset, plan in [(goal, 400000), (goal2, 200000)]:
            MonthPlan.objects.create(household=self.house, created_by=self.user, month=self.month, asset=asset, amount_ore=plan)
        self.entry('deposit', 450000, asset=goal)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Regning', amount_ore=865000, first_due=self.today, monthly=False, category=self.category)
        services.prepare_month(self.house, self.month)
        values = services.calculate(self.house, self.month)
        self.assertEqual(values['available'], 1840000)
        self.assertEqual(values['expected'], 500000)
        self.entry('withdrawal', 10000, asset=goal)
        self.entry('deposit', 10000, asset=goal)
        self.assertEqual(services.calculate(self.house, self.month)['available'], 1840000)

    def test_bill_payment_retry_and_historical_reserve(self):
        old = self.month - timedelta(days=1)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Gammel regning', amount_ore=10000, first_due=old, monthly=False, category=self.category)
        services.prepare_month(self.house, self.month)
        bill = BillOccurrence.objects.get(template=template)
        key = uuid.uuid4()
        FinancialAreaGrant.objects.filter(area=self.area, member__user=self.member).update(role='editor')
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            payment = services.pay_bill(self.member, bill.pk, self.today, key, bill.version)
        FinancialAreaGrant.objects.filter(area=self.area, member__user=self.member).update(role='editor')
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            self.assertEqual(services.pay_bill(self.member, bill.pk, self.today, key, bill.version).pk, payment.pk)
        self.assertEqual(Entry.objects.filter(occurrence=bill).count(), 1)
        self.assertEqual(services.calculate(self.house, old)['bills'], 10000)
        self.assertEqual(services.calculate(self.house, self.month)['bills'], 0)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 10000)
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            services.delete_entry(self.member, payment.pk, payment.version)
        self.assertEqual(services.calculate(self.house, self.month)['bills'], 10000)

    def test_month_reset_goal_carry_and_historical_limits(self):
        goal = self.asset(opening_ore=10000)
        MonthPlan.objects.create(household=self.house, created_by=self.user, month=self.month, asset=goal, amount_ore=2000)
        MonthPlan.objects.create(household=self.house, created_by=self.user, month=self.month, category=self.category, amount_ore=3000)
        self.entry('income', 90000)
        future = services.next_month(self.month)
        services.prepare_month(self.house, future)
        services.prepare_month(self.house, future)
        self.assertEqual(services.calculate(self.house, future)['available'], -2000)
        self.assertEqual(MonthPlan.objects.filter(month=future).count(), 2)
        self.assertEqual(services.savings_balance(goal), 10000)
        self.assertEqual(MonthPlan.objects.get(month=self.month, category=self.category).amount_ore, 3000)

    def test_refund_and_future_and_savings_validation(self):
        payment = self.entry('expense', 10000)
        self.entry('refund', 3000, original=payment)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 7000)
        with self.assertRaises(ValidationError): self.entry('refund', 8000, original=payment)
        goal = self.asset(opening_ore=1000)
        with self.assertRaises(ValidationError): self.entry('withdrawal', 1001, asset=goal)
        candidate = Entry(kind='expense', amount_ore=100, description='Fremtid', effective_date=self.today + timedelta(days=1), category=self.category)
        with self.assertRaises(ValidationError): services.save_entry(self.user, candidate)

    def test_fund_topup_single_effect_and_payment_dispatch(self):
        asset = self.asset('fund', opening_ore=720000)
        MonthPlan.objects.create(household=self.house, created_by=self.user, month=self.month, asset=asset, amount_ore=80000)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Årsregning', amount_ore=960000, first_due=self.today, monthly=False, asset=asset, accounting_class='fund')
        services.prepare_month(self.house, self.month)
        self.assertEqual(services.calculate(self.house, self.month)['funds'], 240000)
        bill = BillOccurrence.objects.get(template=template)
        services.pay_bill(self.user, bill.pk, self.today, uuid.uuid4())
        services.prepare_month(self.house, self.month)
        self.assertEqual(services.calculate(self.house, self.month)['funds'], 240000)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 0)
        self.assertEqual(services.fund_balance(asset, services.month_end(self.month)), 0)

    def test_foreign_currency_snapshot(self):
        recipient = self.asset('recipient')
        row = self.entry('remittance', 1, asset=recipient, original_amount=Decimal('10'), currency='EUR', exchange_rate=Decimal('11.25'), fee_ore=100)
        self.assertEqual(row.amount_ore, 11350)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 11350)
        with self.assertRaises(ValidationError): self.entry('remittance', 100, asset=recipient)

    def test_login_wrong_expired_reused_and_logout(self):
        identity.send_code('new@example.test', '127.0.0.1')
        code = mail.outbox[-1].body.split('Din kode er ')[1][:6]
        response = self.client.post('/kode/', {'email': 'new@example.test', 'code': '000000' if code != '000000' else '111111'})
        self.assertContains(response, 'Koden er feil')
        row = LoginCode.objects.get(email='new@example.test')
        self.assertEqual(row.attempts, 1)
        self.assertEqual(self.client.post('/kode/', {'email': 'new@example.test', 'code': code}).status_code, 302)
        old_cookie = self.client.cookies['sessionid'].value
        self.client.post('/utlogging/')
        self.client.cookies['sessionid'] = old_cookie
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 302)
        self.assertContains(self.client.post('/kode/', {'email': 'new@example.test', 'code': code}), 'Koden er feil')
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.consumed = False
        row.save()
        self.assertContains(self.client.post('/kode/', {'email': 'new@example.test', 'code': code}), 'Koden er feil')

    def test_invitation_verified_email_and_single_household(self):
        identity.invite(self.user, 'invitee@example.test', 'https://example.test', financial_sharing='private')
        token = mail.outbox[-1].body.split('/invitasjon/')[1].split('/')[0]
        user = get_user_model().objects.create_user(username='invitee@example.test', email='invitee@example.test')
        with self.assertRaises(ValidationError): identity.accept_invite(user, token, 'wrong@example.test')
        identity.accept_invite(user, token, user.email)
        self.assertEqual(Membership.objects.get(user=user).household, self.house)
        with self.assertRaises(ValidationError): identity.accept_invite(user, token, user.email)

    def test_import_owner_drafts_idempotency_and_changed_source(self):
        source = {'import_series': 'test-series', 'source': {'sha256': 'a' * 64}, 'categories': [{'source_id': 'c1', 'raw': {'name': 'Kildekategori'}, 'monthly_budget_ore': 100, 'issue_codes': []}], 'transactions': [{'source_id': 't1', 'raw': {'description': 'Kildepost'}, 'category_id': 'c1', 'source_accounting_class': 'expense', 'amount_nok_ore': 100, 'effective_date': self.today.isoformat(), 'issue_codes': []}, {'source_id': 't2', 'raw': {'description': 'Udatert'}, 'issue_codes': ['missing_date']}]}
        binding = {'owner_email': self.user.email}
        with self.assertRaises(PermissionDenied): importing.apply_import(self.other, self.other.email, source, binding)
        batch = importing.apply_import(self.user, self.user.email, source, binding)
        self.assertEqual(ImportRecord.objects.filter(batch=batch).count(), 3)
        self.assertEqual(Entry.objects.filter(household=self.house).count(), 1)
        self.assertEqual(importing.apply_import(self.user, self.user.email, source, binding).pk, batch.pk)
        source['source']['sha256'] = 'b' * 64
        with self.assertRaises(ValidationError): importing.apply_import(self.user, self.user.email, source, binding)
        self.assertEqual(Entry.objects.filter(household=self.house).count(), 1)

    def test_all_pages_and_real_crud(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['verified_email'] = self.user.email
        session.save()
        for page in ['oversikt', 'poster', 'budsjett', 'regninger', 'sparing', 'gjeld', 'arsutgifter', 'utland', 'arsoversikt', 'tilpass', 'familie', 'mer', 'varsler']:
            response = self.client.get(f'/app/{page}/')
            self.assertEqual(response.status_code, 200, page)
        response = self.client.post('/ny/entry/', {'kind': 'expense', 'description': 'HTTP-utgift', 'effective_date': self.today.isoformat(), 'amount': '12,50', 'category': str(self.category.pk), 'idempotency_key': str(uuid.uuid4()), 'fee_ore': 0})
        self.assertEqual(response.status_code, 302, response.content.decode())
        self.assertEqual(Entry.objects.get(description='HTTP-utgift').amount_ore, 1250)

    def test_savings_edit_validates_both_timelines_and_opening(self):
        goal = self.asset()
        second = self.asset()
        deposit = self.entry('deposit', 10000, asset=goal)
        self.entry('withdrawal', 10000, asset=goal)
        deposit.asset = second
        with self.assertRaises(ValidationError): services.save_entry(self.user, deposit, deposit.version)
        deposit.asset = None
        deposit.kind = 'expense'
        with self.assertRaises(ValidationError): services.save_entry(self.user, deposit, deposit.version)
        goal.kind = 'recipient'
        with self.assertRaises(ValidationError): services.save_row(self.user, goal, goal.version, True)
        goal.kind = 'savings'
        goal.opening_date = self.today + timedelta(days=1)
        with self.assertRaises(ValidationError): services.save_row(self.user, goal, goal.version, True)

    def test_same_day_savings_preserves_insert_order_not_uuid(self):
        goal = self.asset()
        deposit = Entry(id=uuid.UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'), kind='deposit', asset=goal, amount_ore=10000, effective_date=self.today, description='Først')
        services.save_entry(self.user, deposit)
        withdrawal = Entry(id=uuid.UUID('00000000-0000-0000-0000-000000000001'), kind='withdrawal', asset=goal, amount_ore=10000, effective_date=self.today, description='Deretter')
        services.save_entry(self.user, withdrawal)
        self.assertEqual(services.savings_balance(goal), 0)

    def test_historical_opening_date(self):
        goal = self.asset(opening_ore=10000)
        fund = self.asset('fund', opening_ore=20000)
        prior = self.month - timedelta(days=1)
        self.assertEqual(services.savings_balance(goal, prior), 0)
        self.assertEqual(services.fund_balance(fund, prior), 0)
        self.assertEqual(services.savings_balance(goal, self.month), 10000)
        self.assertEqual(services.fund_balance(fund, self.month), 20000)

    def test_template_edit_updates_future_preserves_history_and_no_duplicate(self):
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Serie', amount_ore=1000, first_due=self.today, monthly=True, category=self.category)
        future = services.next_month(services.next_month(self.month))
        services.prepare_month(self.house, future)
        historical = BillOccurrence.objects.get(template=template, due_date=self.today)
        from budget import correction_services as corrections
        start = self.today + timedelta(days=1)
        manifest = [[str(row.pk), row.version] for row in corrections.affected(template, start)]
        corrections.revise_series(self.user, template.pk, 'revise', template.version, uuid.uuid4(), start, {'amount_ore':2000}, manifest)
        self.assertEqual(BillOccurrence.objects.get(pk=historical.pk).amount_ore, 1000)
        self.assertTrue(all(row.amount_ore == 2000 for row in BillOccurrence.objects.filter(template=template, due_date__gt=self.today)))
        template.refresh_from_db()
        corrections.revise_series(self.user, template.pk, 'archive', template.version, uuid.uuid4(), start, confirmed=[])
        services.prepare_month(self.house, future)
        self.assertTrue(BillOccurrence.objects.filter(template=template, due_date__gt=self.today).exists())
        self.assertEqual(BillOccurrence.objects.filter(template=template, recurrence_slot=self.month).count(), 1)

    def test_http_roles_csrf_conflict_and_module_hiding(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/ny/category/').status_code, 403)
        self.assertEqual(self.client.post('/preferanser/', {'version': 1, 'confirm': 'on'}).status_code, 403)
        self.assertEqual(Client(enforce_csrf_checks=True).post('/innlogging/', {'email': 'csrf@example.test'}).status_code, 403)
        FinancialAreaGrant.objects.filter(area=self.area, member__user=self.member).update(role='editor')
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            row = services.save_entry(self.member, Entry(kind='income', amount_ore=10000, effective_date=self.today, description='Medlem'))
        FinancialAreaGrant.objects.filter(area=self.area, member__user=self.member).update(role='editor')
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            services.save_entry(self.member, row, 1)
        response = self.client.post(f'/endre/entry/{row.pk}/', {'version': 1, 'command_key': str(uuid.uuid4()), 'kind': 'income', 'amount': '100', 'description': 'Konfliktfelt bevart', 'effective_date': self.today.isoformat(), 'received': 'on', 'idempotency_key': str(row.idempotency_key), 'fee_ore': 0})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Konfliktfelt bevart', status_code=409)
        goal = self.asset()
        MonthPlan.objects.create(household=self.house, created_by=self.user, month=self.month, asset=goal, amount_ore=1234)
        before = services.calculate(self.house, self.month)['available']
        self.client.force_login(self.user)
        self.client.post('/preferanser/', {'version': self.house.version, 'confirm': 'on'})
        self.house.refresh_from_db()
        self.assertEqual(services.calculate(self.house, self.month)['available'], before)

    def test_debt_dispatch_and_frozen_strategy_allocation(self):
        debt = self.asset('debt', opening_ore=100000, annual_rate=Decimal('12'), minimum_ore=10000)
        services.allocate_debt_plan(self.user, self.month, 'avalanche', 5000)
        self.assertEqual(MonthPlan.objects.get(asset=debt, month=self.month).amount_ore, 15000)
        bill = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Gjeldsforfall', amount_ore=10000, first_due=self.today, monthly=False, asset=debt, accounting_class='debt')
        services.prepare_month(self.house, self.month)
        occurrence = BillOccurrence.objects.get(template=bill)
        before = services.calculate(self.house, self.month)
        FinancialAreaGrant.objects.filter(area=self.area, member__user=self.member).update(role='editor')
        with area_scope(Membership.objects.get(user=self.member), self.area.pk):
            services.pay_bill(self.member, occurrence.pk, self.today, uuid.uuid4())
        after = services.calculate(self.house, self.month)
        self.assertEqual(after['debt'], before['debt'])
        self.assertEqual(after['ordinary'], 0)
        self.assertEqual(after['cash'], -10000)
        future = services.next_month(self.month)
        services.allocate_debt_plan(self.user, future, 'snowball', 0)
        self.assertEqual(MonthPlan.objects.get(asset=debt, month=self.month).amount_ore, 15000)

    def test_zero_budget_and_explicit_import_plan_month(self):
        from budget.forms import AssetForm, PlanForm
        form = PlanForm({'month': self.month.isoformat(), 'category': self.category.pk, 'amount': '0'}, household=self.house)
        self.assertTrue(form.is_valid(), form.errors)
        form = AssetForm({'kind': 'savings', 'name': 'Åpning', 'opening': '0', 'opening_date': self.month.isoformat(), 'plan': '100'}, instance=Asset(household=self.house, created_by=self.user))
        self.assertFalse(form.is_valid())

    def test_annual_ore_distribution_and_future_projection(self):
        fund = self.asset('fund', target_ore=120005)
        december = date(self.month.year, 12, 1)
        services.prepare_month(self.house, december)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=december).amount_ore, 10005)
        debt = self.asset('debt', opening_ore=100000, annual_rate=Decimal('12'), minimum_ore=10000)
        self.assertEqual(services.estimated_debt_balance(debt, self.month), 100000)
        next_day = services.next_month(self.month)
        self.assertEqual(services.estimated_debt_balance(debt, next_day), 101000)

    def test_source_interest_fraction_converts_to_percentage(self):
        source = {'import_series': 'rate-test', 'source': {'sha256': 'c' * 64}, 'debts': [{'source_id': 'd1', 'raw': {'name': 'Syntetisk lån'}, 'reference_balance_ore': 100000, 'reference_date': self.month.isoformat(), 'annual_rate_decimal': '0.12', 'monthly_minimum_ore': 10000, 'issue_codes': []}]}
        importing.apply_import(self.user, self.user.email, source, {'owner_email': self.user.email})
        debt = Asset.objects.get(household=self.house, name='Syntetisk lån')
        self.assertEqual(debt.annual_rate, Decimal('12'))
        self.assertEqual(services.estimated_debt_balance(debt, services.next_month(self.month)), 101000)

    def test_annual_import_resolution_preserves_known_amounts(self):
        batch = ImportBatch.objects.create(household=self.house, created_by=self.user, series='annual-source', sha256='d' * 64)
        raw = {'source_id': 'a1', 'raw': {'name': 'Syntetisk årsutgift', 'due_month': 12}, 'annual_amount_ore': 120000, 'opening_allocation_ore': 15000, 'opening_allocation_effective_date': None}
        record = ImportRecord.objects.create(household=self.house, created_by=self.user, batch=batch, source_id='a1', source_kind='annual_funds', raw=raw)
        self.client.force_login(self.user)
        session = self.client.session
        session['verified_email'] = self.user.email
        session.save()
        with patch('budget.importing.load_private_source', return_value=({}, {'owner_email': self.user.email})):
            response = self.client.get(f'/import/avklar/{record.pk}/')
            self.assertEqual(response.context['form'].initial['opening'], Decimal('150'))
            self.assertEqual(response.context['form'].initial['target'], Decimal('1200'))
            response = self.client.post(f'/import/avklar/{record.pk}/', {'kind': 'fund', 'name': 'Syntetisk årsutgift', 'opening': '150', 'target': '1200', 'opening_date': self.month.isoformat(), 'version': 0})
            self.assertEqual(response.status_code, 302, response.content.decode())
        record.refresh_from_db()
        fund = Asset.objects.get(pk=record.target_id)
        self.assertEqual((fund.opening_ore, fund.target_ore), (15000, 120000))
        services.prepare_month(self.house, self.month)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=self.month).amount_ore, 10000)

    def test_source_reconciliation_all_classes_and_negative_directions(self):
        goal = self.asset(opening_ore=10000)
        debt = self.asset('debt')
        fund = self.asset('fund', opening_ore=10000)
        recipient = self.asset('recipient')
        income = self.entry('income', 100000)
        expense = self.entry('expense', 10000)
        deposit = self.entry('deposit', 5000, asset=goal)
        withdrawal = self.entry('withdrawal', 1000, asset=goal)
        debt_payment = self.entry('debt', 4000, asset=debt)
        fund_payment = self.entry('fund', 3000, asset=fund)
        remittance = self.entry('remittance', 2500, asset=recipient, original_amount=Decimal('25'), currency='NOK')
        refunds = [self.entry('refund', amount, original=original) for amount, original in [(2000, expense), (200, debt_payment), (500, fund_payment), (100, remittance)]]
        batch = ImportBatch.objects.create(household=self.house, created_by=self.user, series='all-classes', sha256='e' * 64, reconciliation={'source_transaction_totals_ore': {self.month.strftime('%Y-%m'): {'income': 100000, 'expense': 8000, 'savings_deposit': 4000, 'debt_payment': 3800, 'annual_fund_payment': 2500, 'remittance': 2400}}})
        for index, entry in enumerate([income, expense, deposit, withdrawal, debt_payment, fund_payment, remittance] + refunds):
            ImportRecord.objects.create(household=self.house, created_by=self.user, batch=batch, source_id=f't{index}', source_kind='transactions', raw={}, status='confirmed', target_id=entry.pk, approved_decision=importing.decision_snapshot(entry))
        result = importing.reconcile_batch(batch)
        self.assertEqual(result['transaction_differences_ore'], {})
        self.assertTrue(result['financial_totals_verified'])
        refunds[0].amount_ore += 1
        services.save_entry(self.user, refunds[0], refunds[0].version)
        self.assertFalse(importing.reconcile_batch(batch)['financial_totals_verified'])

    def test_entry_sequence_immutable_and_not_reused_after_deletion(self):
        first = self.entry('income', 100)
        services.delete_entry(self.user, first.pk, first.version)
        second = self.entry('income', 100)
        self.assertGreater(second.sequence, first.sequence)
        second.sequence = 0
        with self.assertRaises(ValidationError): second.save()

    def test_unfunded_direct_fund_payment_requires_traceable_obligation(self):
        fund = self.asset('fund', opening_ore=1000)
        with self.assertRaisesMessage(ValidationError, 'Finansieringsgap'):
            self.entry('fund', 5000, asset=fund)
        self.assertFalse(Entry.objects.filter(asset=fund).exists())
        bill = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Finansieringsgap', amount_ore=5000, first_due=self.today, monthly=False, asset=fund, accounting_class='fund')
        services.prepare_month(self.house, self.month)
        occurrence = BillOccurrence.objects.get(template=bill)
        services.pay_bill(self.user, occurrence.pk, self.today, uuid.uuid4())
        self.assertEqual(services.calculate(self.house, self.month)['funds'], 4000)
        self.assertEqual(services.fund_balance(fund, services.month_end(self.month)), 0)


class ConcurrentPaymentTests(TransactionTestCase):
    def test_two_clients_create_one_payment(self):
        self.assertEqual(connection.vendor, 'postgresql')
        user, house, category = setup_family()
        enter_fixture_area(self, user)
        today = timezone.localdate()
        template = BillTemplate.objects.create(household=house, created_by=user, name='Samtidig', amount_ore=10000, first_due=today, monthly=False, category=category)
        services.prepare_month(house, today)
        bill = BillOccurrence.objects.get(template=template)
        def pay(_):
            close_old_connections()
            actor = get_user_model().objects.get(pk=user.pk)
            try:
                with area_scope(Membership.objects.get(user=actor), user.test_area.pk):
                    result = services.pay_bill(actor, bill.pk, today, shared_key, 1)
            except services.Conflict:
                return None
            close_old_connections()
            return result.pk
        shared_key = uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool: ids = list(pool.map(pay, [1, 2]))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Entry.objects.filter(occurrence=bill).count(), 1)
