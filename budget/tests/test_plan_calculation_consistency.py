"""Bekreftet månedsplan og oversikt må bruke samme penger én gang."""
from datetime import date
from unittest.mock import patch
import uuid

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from budget import services, spending_services as planner
from budget.financial_projection import month_basis
from budget.models import Asset, BillOccurrence, BillTemplate, FundTopUp, MonthPlan
from budget.spending_forms import MAX_ORE
from budget.tests.financial_support import enter_fixture_area
from budget.tests.test_domain import setup_family


class PlanCalculationConsistencyTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('plan-consistency@example.test')
        enter_fixture_area(self, self.user)
        self.month, self.target = date(2026, 10, 1), date(2026, 11, 1)
        clock = patch('django.utils.timezone.localdate', return_value=date(2026, 10, 24))
        clock.start()
        self.addCleanup(clock.stop)

    def draft(self):
        draft = planner.planning(self.user, '2026-11')['draft']
        draft.update(expected_income_ore=50000, acknowledge_incomplete=True)
        for row in draft['categories']:
            row['other_ore'] = 0
        for row in draft['assets']:
            row['amount_ore'] = row['amount_ore'] or 0
        return draft

    def check_old_fund_gap(self, materialized=False):
        fund = Asset.objects.create(household=self.house, created_by=self.user,
            kind='fund', name='Fiktive årsutgifter', opening_date=self.month)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=fund, month=self.month, amount_ore=0)
        bill = BillTemplate.objects.create(household=self.house, created_by=self.user,
            name='Fiktiv gammel årsregning', first_due=self.month, monthly=False,
            amount_ore=10000, accounting_class='fund', asset=fund)
        if materialized:
            services.materialize_template(bill, self.month)
        self.assertFalse(FundTopUp.objects.exists())
        with CaptureQueriesContext(connection) as queries:
            before = planner.preview(self.user, self.draft())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(month_basis(self.house, self.target)['fund_topups'][fund.pk], 0)
        self.assertEqual(before['totals']['funds_ore'], 0)
        self.assertEqual(before['totals']['planned_remainder_ore'], 50000)
        services.prepare_month(self.house, self.month)
        self.assertEqual(FundTopUp.objects.get(occurrence__template=bill).amount_ore, 10000)
        after = planner.preview(self.user, self.draft())
        self.assertEqual(before['totals'], after['totals'])
        self.assertEqual(services.calculate(self.house, self.target)['funds'], 0)

    def test_virtual_old_fund_bill_does_not_repeat_shortfall_next_month(self):
        self.check_old_fund_gap()

    def test_materialized_unreconciled_fund_bill_has_identical_forecast(self):
        self.check_old_fund_gap(materialized=True)

    def test_fund_opening_in_target_month_finances_bill_without_extra_topup(self):
        for day in (1, 15):
            with self.subTest(opening_day=day):
                opening = self.target.replace(day=day)
                fund = Asset.objects.create(household=self.house, created_by=self.user,
                    kind='fund', name=f'Fiktiv åpning {day}', opening_date=opening,
                    opening_ore=10000)
                MonthPlan.objects.create(household=self.house, created_by=self.user,
                    asset=fund, month=self.target, amount_ore=0)
                BillTemplate.objects.create(household=self.house, created_by=self.user,
                    name=f'Fiktiv årsregning {day}', first_due=opening, monthly=False,
                    amount_ore=10000, accounting_class='fund', asset=fund)
                preview = planner.preview(self.user, self.draft())
                self.assertEqual(preview['totals']['funds_ore'], 0)
                self.assertEqual(preview['totals']['planned_remainder_ore'], 50000)
                self.assertEqual(month_basis(self.house, self.target)['fund_topups'][fund.pk], 0)
                self.assertEqual(services.calculate(self.house, self.target)['funds'], 0)

    def test_fund_opening_after_target_month_does_not_increase_available_balance(self):
        fund = Asset.objects.create(household=self.house, created_by=self.user,
            kind='fund', name='Fiktiv senare åpning', opening_date=date(2026, 12, 1),
            opening_ore=10000)
        self.assertEqual(planner.fund_available_before(self.house, fund, self.target), 0)
        line = next(row for row in planner.planning(self.user, '2026-11')['assets']
                    if row['id'] == str(fund.pk))
        self.assertEqual(line['available_balance_ore'], 0)

    def check_debt_save(self, requested, bill_amount=0):
        debt = Asset.objects.create(household=self.house, created_by=self.user,
            kind='debt', name='Fiktivt lån', opening_date=self.month,
            opening_ore=100000, annual_rate=0, minimum_ore=25000)
        if bill_amount:
            BillTemplate.objects.create(household=self.house, created_by=self.user,
                name='Fiktiv lånebetaling', first_due=self.target, monthly=False,
                amount_ore=bill_amount, accounting_class='debt', asset=debt)
        draft = self.draft()
        draft['assets'][0]['amount_ore'] = requested
        preview = planner.preview(self.user, draft)
        expected = max(requested, bill_amount, 25000)
        self.assertEqual(preview['totals']['debt_ore'], expected)
        payload = dict(draft=preview['draft'], confirmation_digest=preview['confirmation_digest'],
                       confirm=True, key=str(uuid.uuid4()))
        planner.save_plan(self.user, payload)
        saved = services.calculate(self.house, self.target)
        self.assertEqual(saved['debt'], expected)
        self.assertEqual(saved['available'], -expected)
        change = next(row for row in preview['changes'] if row['kind'] == 'debt')
        self.assertEqual(MonthPlan.objects.get(asset=debt, month=self.target).amount_ore, change['after_ore'])
        planner.save_plan(self.user, payload)
        services.prepare_month(self.house, self.target)
        self.assertEqual(services.calculate(self.house, self.target), saved)
        self.assertEqual(MonthPlan.objects.filter(asset=debt, month=self.target).count(), 1)

    def test_zero_debt_draft_saves_the_confirmed_minimum(self):
        self.check_debt_save(0)

    def test_below_minimum_debt_draft_saves_the_confirmed_minimum(self):
        self.check_debt_save(10000)

    def test_linked_debt_bill_is_reserved_once_after_save(self):
        self.check_debt_save(0, bill_amount=30000)

    def test_higher_debt_plan_survives_save(self):
        self.check_debt_save(40000, bill_amount=30000)

    def debt_boundary_draft(self, minimum, bill_amounts=()):
        debt = Asset.objects.create(household=self.house, created_by=self.user,
            kind='debt', name='Fiktiv beløpsgrense', opening_date=self.month,
            opening_ore=MAX_ORE, annual_rate=0, minimum_ore=minimum)
        for index, amount in enumerate(bill_amounts):
            BillTemplate.objects.create(household=self.house, created_by=self.user,
                name=f'Fiktivt forfall {index}', first_due=self.target, monthly=False,
                amount_ore=amount, accounting_class='debt', asset=debt)
        draft = self.draft()
        draft['assets'][0]['amount_ore'] = 0
        return debt, draft

    def test_debt_minimum_above_amount_limit_is_rejected_during_preview(self):
        _, draft = self.debt_boundary_draft(MAX_ORE + 1)
        with self.assertRaises(ValidationError):
            planner.preview(self.user, draft)
        self.assertFalse(MonthPlan.objects.exists())

    def test_combined_debt_bills_above_amount_limit_are_rejected_during_preview(self):
        _, draft = self.debt_boundary_draft(0, (MAX_ORE, 1))
        with self.assertRaises(ValidationError):
            planner.preview(self.user, draft)
        self.assertFalse(MonthPlan.objects.exists())

    def test_debt_normalized_exact_amount_limit_can_be_confirmed_and_saved(self):
        debt, draft = self.debt_boundary_draft(MAX_ORE)
        preview = planner.preview(self.user, draft)
        self.assertEqual(preview['draft']['assets'][0]['amount_ore'], MAX_ORE)
        planner.save_plan(self.user, dict(draft=preview['draft'],
            confirmation_digest=preview['confirmation_digest'], confirm=True, key=str(uuid.uuid4())))
        self.assertEqual(MonthPlan.objects.get(asset=debt, month=self.target).amount_ore, MAX_ORE)
        self.assertEqual(services.calculate(self.house, self.target)['debt'], MAX_ORE)
