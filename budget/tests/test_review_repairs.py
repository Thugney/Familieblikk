import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from budget import identity, importing, services
from budget.models import Asset, BillOccurrence, BillTemplate, Entry, FundTopUp, ImportBatch, ImportRecord, MonthPlan
from budget.tests.test_domain import setup_family
from budget.views import add_calendar_months


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReviewRepairTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family()
        self.today = timezone.localdate()
        self.month = services.month_start(self.today)
        self.prior = (self.month - timedelta(days=1)).replace(day=1)

    def asset(self, kind, **kwargs):
        return Asset.objects.create(household=self.house, created_by=self.user, kind=kind, name='Kontroll', opening_date=self.prior, **kwargs)

    def entry(self, kind, amount, day=None, **kwargs):
        return services.save_entry(self.user, Entry(kind=kind, amount_ore=amount, effective_date=day or self.today, description='Kontroll', category=self.category, **kwargs))

    def test_materialized_skipped_funds_and_effective_target_history(self):
        fund = self.asset('fund', target_ore=120000)
        far = services.next_month(services.next_month(self.month))
        services.prepare_month(self.house, far)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=self.prior).amount_ore, 10000)
        fund.target_ore = 240000
        services.save_row(self.user, fund, fund.version, True)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=self.prior).amount_ore, 10000)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=far).amount_ore, 20000)
        self.assertEqual(services.fund_balance(fund, services.month_end(far)), 70000)

    def test_browsed_future_copy_refreshes_but_explicit_future_plan_stays(self):
        plan = MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category, month=self.month, amount_ore=1000)
        future = services.next_month(self.month)
        services.prepare_month(self.house, future)
        plan.amount_ore = 2000
        services.save_row(self.user, plan, plan.version, True)
        self.assertEqual(MonthPlan.objects.get(category=self.category, month=future).amount_ore, 2000)
        explicit = MonthPlan.objects.get(category=self.category, month=future)
        explicit.amount_ore = 3000
        services.save_row(self.user, explicit, explicit.version, True)
        plan.amount_ore = 4000
        services.save_row(self.user, plan, plan.version, True)
        self.assertEqual(MonthPlan.objects.get(pk=explicit.pk).amount_ore, 3000)

    def test_zero_annual_target_replaces_current_anchor_and_future_allocations(self):
        fund = self.asset('fund', target_ore=120000)
        future = services.next_month(self.month)
        services.prepare_month(self.house, future)
        fund.target_ore = 0
        services.save_row(self.user, fund, fund.version, True)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=self.prior).amount_ore, 10000)
        current = MonthPlan.objects.get(asset=fund, month=self.month)
        self.assertEqual((current.annual_total_ore, current.amount_ore), (0, 0))
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=future).amount_ore, 0)
        services.prepare_month(self.house, services.next_month(future))
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=services.next_month(future)).amount_ore, 0)

    def test_archive_materializes_unvisited_past_bills(self):
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Historisk', amount_ore=1000, first_due=self.prior, category=self.category)
        template.archived = True
        services.save_row(self.user, template, template.version)
        services.prepare_month(self.house, self.prior)
        self.assertTrue(BillOccurrence.objects.filter(template=template, due_date=self.prior).exists())

    def test_topup_original_month_and_amount_reconciliation_after_future_navigation(self):
        fund = self.asset('fund', opening_ore=1000)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Fond', amount_ore=5000, first_due=self.prior, monthly=False, asset=fund, accounting_class='fund')
        services.prepare_month(self.house, services.next_month(self.month))
        bill = BillOccurrence.objects.get(template=template)
        topup = FundTopUp.objects.get(occurrence=bill)
        self.assertEqual((topup.effective_month, topup.amount_ore), (self.prior, 4000))
        bill.amount_ore = 6000
        services.save_row(self.user, bill, bill.version)
        topup.refresh_from_db()
        self.assertEqual((topup.effective_month, topup.amount_ore), (self.prior, 5000))
        services.pay_bill(self.user, bill.pk, self.today, uuid.uuid4())
        self.assertEqual(FundTopUp.objects.filter(occurrence=bill).count(), 1)
        self.assertEqual(services.calculate(self.house, self.month)['ordinary'], 0)

    def test_refund_deletion_and_historical_increase_cannot_break_later_fund_payment(self):
        fund = self.asset('fund', opening_ore=10000)
        payment = self.entry('fund', 10000, asset=fund)
        refund = self.entry('refund', 5000, original=payment)
        self.entry('fund', 5000, asset=fund)
        with self.assertRaises(ValidationError): services.delete_entry(self.user, refund.pk, refund.version)
        self.assertTrue(Entry.objects.filter(pk=refund.pk).exists())
        other = self.asset('fund', opening_ore=10000)
        first = self.entry('fund', 2500, day=self.prior, asset=other)
        self.entry('fund', 7500, asset=other)
        first.amount_ore = 5000
        with self.assertRaises(ValidationError): services.save_entry(self.user, first, first.version)

    def test_paid_debt_gets_zero_plan_and_overpayment_refund_keeps_credit(self):
        debt = self.asset('debt', opening_ore=10000, annual_rate=Decimal(0), minimum_ore=1000)
        payment = self.entry('debt', 15000, asset=debt)
        self.entry('refund', 5000, original=payment)
        self.assertEqual(services.estimated_debt_balance(debt, self.today), 0)
        services.allocate_debt_plan(self.user, self.month, 'avalanche', 0)
        self.assertEqual(MonthPlan.objects.get(asset=debt, month=self.month).amount_ore, 0)

    def test_overflow_long_email_and_module_navigation(self):
        self.assertIsNone(add_calendar_months(date(9999, 12, 1), 1))
        email = 'a' * 64 + '@' + 'b' * 60 + '.' + 'c' * 60 + '.test'
        identity.send_code(email, '127.0.0.2')
        code = mail.outbox[-1].body.split('Din kode er ')[1][:6]
        self.assertEqual(self.client.post('/kode/', {'email': email, 'code': code}).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get('/app/mer/')
        for route in ['gjeld', 'arsutgifter', 'utland']: self.assertNotContains(response, f'href="/app/{route}/"')
        self.house.modules = {'debt': True, 'fund': True, 'remittance': True}
        self.house.save()
        response = self.client.get('/app/mer/')
        for route in ['gjeld', 'arsutgifter', 'utland']: self.assertContains(response, f'href="/app/{route}/"')

    def test_old_savings_plan_cannot_move_and_asset_plan_conflicts(self):
        goal = self.asset('savings')
        old = MonthPlan.objects.create(household=self.house, created_by=self.user, asset=goal, month=self.prior, amount_ore=1000)
        old.month = self.month
        with self.assertRaises(ValidationError): services.save_row(self.user, old, old.version, True)
        self.client.force_login(self.user)
        self.client.get(f'/endre/asset/{goal.pk}/')
        current = MonthPlan.objects.create(household=self.house, created_by=self.user, asset=goal, month=self.month, amount_ore=1000)
        data = {'version': goal.version, 'kind': 'savings', 'name': 'Felter beholdt', 'opening': '0', 'target': '100', 'opening_date': self.prior.isoformat(), 'plan': '20', 'plan_month': self.month.isoformat(), 'displayed_plan_month': self.month.isoformat(), 'plan_version': 0}
        response = self.client.post(f'/endre/asset/{goal.pk}/', data)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Felter beholdt', status_code=409)
        current.amount_ore = 3000
        services.save_row(self.user, current, current.version, True)
        data['plan_version'] = 1
        self.assertEqual(self.client.post(f'/endre/asset/{goal.pk}/', data).status_code, 409)

    def test_asset_kind_guard_includes_unpaid_obligations(self):
        debt = self.asset('debt')
        BillTemplate.objects.create(household=self.house, created_by=self.user, name='Bundet', amount_ore=100, first_due=self.today, asset=debt, accounting_class='debt')
        debt.kind = 'recipient'
        with self.assertRaises(ValidationError): services.save_row(self.user, debt, debt.version, True)

    def test_approved_decisions_reconcile_undated_and_reclassified_rows(self):
        debt = self.asset('debt')
        batch = ImportBatch.objects.create(household=self.house, created_by=self.user, series='reviewed-decisions', sha256='f' * 64, reconciliation={'source_transaction_totals_ore': {self.prior.strftime('%Y-%m'): {'expense': 100}}})
        undated = self.entry('expense', 250)
        reclassified = self.entry('debt', 100, asset=debt)
        for name, entry in [('undated', undated), ('reclassified', reclassified)]:
            ImportRecord.objects.create(household=self.house, created_by=self.user, batch=batch, source_id=name, source_kind='transactions', raw={'effective_date': None}, status='confirmed', target_id=entry.pk, approved_decision=importing.decision_snapshot(entry))
        result = importing.reconcile_batch(batch)
        self.assertTrue(result['financial_totals_verified'])
        self.assertTrue(result['raw_source_differences_ore'])
        undated.amount_ore += 1
        services.save_entry(self.user, undated, undated.version)
        self.assertFalse(importing.reconcile_batch(batch)['financial_totals_verified'])
        services.delete_entry(self.user, undated.pk, undated.version)
        self.assertIn('undated', importing.reconcile_batch(batch)['approved_record_differences'])

    def test_source_zero_and_missing_values_are_distinct(self):
        from budget.forms import AssetForm, PlanForm, EntryForm
        from budget.views import source_money
        self.assertEqual(source_money(0), Decimal('0'))
        self.assertIsNone(source_money(None))
        goal = AssetForm({'kind': 'savings', 'name': 'Nullplan', 'opening': '0', 'target': '0', 'plan': '0', 'opening_date': self.prior.isoformat(), 'plan_month': self.month.isoformat()})
        self.assertTrue(goal.is_valid(), goal.errors)
        budget = PlanForm({'month': self.month.isoformat(), 'category': self.category.pk, 'amount': '0'}, household=self.house)
        self.assertTrue(budget.is_valid(), budget.errors)
        entry = EntryForm({'kind': 'expense', 'description': 'Ugyldig', 'effective_date': self.today.isoformat(), 'amount': '0', 'category': self.category.pk, 'fee_ore': 0, 'idempotency_key': uuid.uuid4()}, household=self.house)
        self.assertFalse(entry.is_valid())
