"""Regressions for reference balances, explicit plans and debt budget allocation."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from budget import services
from budget.financial_areas import area_scope
from budget.financial_projection import month_basis
from budget.models import (Asset, BillOccurrence, BillTemplate, Entry, FinancialAreaGrant,
                           FundTopUp, Membership, MonthPlan)
from budget.tests.financial_support import enter_fixture_area
from budget.tests.test_domain import setup_family


@override_settings(ALLOWED_HOSTS=['testserver'])
class MoneyCalculationTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family()
        enter_fixture_area(self, self.user)
        self.today = timezone.localdate()
        self.month = services.month_start(self.today)
        self.prior = (self.month - timedelta(days=1)).replace(day=1)

    def asset(self, kind, **values):
        return Asset.objects.create(household=self.house, created_by=self.user,
                                    kind=kind, name='Synthetic ' + kind,
                                    opening_date=self.prior, **values)

    def debt(self, opening, minimum, rate='0'):
        return self.asset('debt', opening_ore=opening, minimum_ore=minimum,
                          annual_rate=Decimal(rate))

    def test_fund_reference_date_cannot_cross_existing_allocations(self):
        fund = self.asset('fund', target_ore=120000)
        services.prepare_month(self.house, self.month)
        before = list(MonthPlan.objects.filter(asset=fund).order_by('month').values())
        original_balance = services.fund_balance(fund, services.month_end(self.month))
        fund.opening_date, fund.opening_ore = self.month, 10000
        with self.assertRaisesMessage(ValidationError, 'Åpningsdatoen kan ikke flyttes'):
            services.save_row(self.user, fund, fund.version, True)
        fund.refresh_from_db()
        self.assertEqual((fund.opening_date, fund.opening_ore), (self.prior, 0))
        self.assertEqual(list(MonthPlan.objects.filter(asset=fund).order_by('month').values()), before)
        self.assertEqual(services.fund_balance(fund, services.month_end(self.month)), original_balance)

    def test_fund_reference_edit_http_rejects_without_changing_balance(self):
        fund = self.asset('fund', target_ore=120000)
        services.prepare_month(self.house, self.month)
        self.client.force_login(self.user)
        response = self.client.post(f'/endre/asset/{fund.pk}/', {
            'kind': 'fund', 'name': fund.name, 'version': fund.version,
            'opening_date': self.month.isoformat(), 'opening': '100', 'target': '1200',
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Åpningsdatoen kan ikke flyttes', status_code=400)
        fund.refresh_from_db()
        self.assertEqual((fund.opening_date, fund.opening_ore), (self.prior, 0))

    def test_fund_transaction_history_also_blocks_reference_date_change(self):
        fund = self.asset('fund', opening_ore=10000)
        payment = services.save_entry(self.user, Entry(kind='fund', asset=fund,
            amount_ore=1000, effective_date=self.prior, description='Synthetic payment'))
        self.assertFalse(MonthPlan.objects.filter(asset=fund).exists())
        fund.opening_date = self.month
        with self.assertRaisesMessage(ValidationError, 'Åpningsdatoen kan ikke flyttes'):
            services.save_row(self.user, fund, fund.version, True)
        fund.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(fund.opening_date, self.prior)
        self.assertEqual(services.fund_balance(fund, self.today), 9000)
        self.assertTrue(payment.active)

    def test_unused_fund_reference_date_can_be_corrected(self):
        fund = self.asset('fund', opening_ore=10000)
        fund.opening_date = self.month
        services.save_row(self.user, fund, fund.version, True)
        fund.refresh_from_db()
        self.assertEqual((fund.opening_date, fund.opening_ore), (self.month, 10000))
        self.assertEqual(services.fund_balance(fund, self.today), 10000)

    def test_manual_fund_plan_overrides_annual_carry_without_rewriting_history(self):
        fund = self.asset('fund', target_ore=240005)
        future = services.next_month(self.month)
        later = services.next_month(future)
        services.prepare_month(self.house, later)
        historical = MonthPlan.objects.get(asset=fund, month=self.prior)
        explicit = MonthPlan.objects.get(asset=fund, month=later)
        explicit.amount_ore = 30000
        services.save_row(self.user, explicit, explicit.version, True)
        anchor = MonthPlan.objects.get(asset=fund, month=self.month)
        anchor.amount_ore = 10000
        services.save_row(self.user, anchor, anchor.version, True)
        anchor.refresh_from_db()
        historical.refresh_from_db()
        self.assertIsNone(anchor.annual_total_ore)
        self.assertEqual(historical.amount_ore, services.plan_amount(historical, self.prior))
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=future).amount_ore, 10000)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=later).amount_ore, 30000)
        services.prepare_month(self.house, services.next_month(later))
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=services.next_month(later)).amount_ore, 30000)

    def test_annual_target_edit_restores_annual_rounding_after_month_override(self):
        fund = self.asset('fund', target_ore=120000)
        december = date(self.month.year, 12, 1)
        services.prepare_month(self.house, december)
        anchor = MonthPlan.objects.get(asset=fund, month=self.month)
        anchor.amount_ore = 5000
        services.save_row(self.user, anchor, anchor.version, True)
        fund.target_ore = 240005
        services.save_row(self.user, fund, fund.version, True)
        anchor.refresh_from_db()
        self.assertEqual(anchor.annual_total_ore, 240005)
        self.assertEqual(MonthPlan.objects.get(asset=fund, month=december).amount_ore, 20005)

    def test_debt_plan_rolls_freed_minimum_into_remaining_debt(self):
        small, large = self.debt(5000, 10000), self.debt(100000, 10000)
        for strategy, extra in [('snowball', 0), ('avalanche', 1000)]:
            with self.subTest(strategy=strategy):
                services.allocate_debt_plan(self.user, self.month, strategy, extra)
                self.assertEqual(MonthPlan.objects.get(asset=small, month=self.month).amount_ore, 5000)
                self.assertEqual(MonthPlan.objects.get(asset=large, month=self.month).amount_ore, 15000 + extra)
                self.assertEqual(services.calculate(self.house, self.month)['debt'], 20000 + extra)

    def test_freed_minimum_follows_selected_strategy(self):
        small = self.debt(5000, 10000)
        low = self.debt(30000, 1000)
        high = self.debt(100000, 1000, rate='12')
        services.allocate_debt_plan(self.user, self.month, 'snowball', 0)
        self.assertEqual(MonthPlan.objects.get(asset=low, month=self.month).amount_ore, 6000)
        self.assertEqual(MonthPlan.objects.get(asset=high, month=self.month).amount_ore, 1000)
        services.allocate_debt_plan(self.user, self.month, 'avalanche', 0)
        self.assertEqual(MonthPlan.objects.get(asset=low, month=self.month).amount_ore, 1000)
        self.assertEqual(MonthPlan.objects.get(asset=high, month=self.month).amount_ore, 6000)
        self.assertEqual(MonthPlan.objects.get(asset=small, month=self.month).amount_ore, 5000)

    def test_excess_extra_rejects_without_partial_plan_changes(self):
        first, second = self.debt(5000, 10000), self.debt(10000, 10000)
        services.allocate_debt_plan(self.user, self.month, 'snowball', 0)
        before = list(MonthPlan.objects.order_by('pk').values())
        with self.assertRaisesMessage(ValidationError, 'Ekstrabeløpet overstiger'):
            services.allocate_debt_plan(self.user, self.month, 'snowball', 100)
        self.assertEqual(list(MonthPlan.objects.order_by('pk').values()), before)
        self.assertEqual(MonthPlan.objects.get(asset=first).amount_ore, 5000)
        self.assertEqual(MonthPlan.objects.get(asset=second).amount_ore, 10000)

    def test_paid_off_and_empty_debt_projection_take_zero_months(self):
        paid = self.debt(0, 10000)
        self.assertEqual(services.debt_projection([paid]), {'months': 0, 'interest_ore': 0})
        self.assertEqual(services.debt_projection([]), {'months': 0, 'interest_ore': 0})
        services.allocate_debt_plan(self.user, self.month, 'snowball', 0)
        self.assertEqual(MonthPlan.objects.get(asset=paid).amount_ore, 0)

    def test_projection_retains_fixed_budget_and_interest_rounding(self):
        first, second = self.debt(5000, 10000), self.debt(100000, 10000)
        self.assertEqual(services.debt_projection([first, second], 'snowball'),
                         {'months': 6, 'interest_ore': 0})
        interest = self.debt(100000, 101000, rate='12')
        self.assertEqual(services.debt_projection([interest]), {'months': 1, 'interest_ore': 1000})

    def read_only(self, callback):
        with CaptureQueriesContext(connection) as captured:
            result = callback()
        writes = [row['sql'] for row in captured if row['sql'].lstrip().upper().startswith(
            ('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'ALTER ', 'DROP '))]
        self.assertEqual(writes, [])
        return result

    def bill(self, name, amount, day, accounting_class='ordinary', asset=None):
        return BillTemplate.objects.create(household=self.house, created_by=self.user,
            name=name, amount_ore=amount, first_due=day, monthly=False,
            category=self.category, accounting_class=accounting_class, asset=asset)

    def test_reader_and_writer_match_before_and_after_plan_bill_materialization(self):
        goal, debt = self.asset('savings'), self.debt(100000, 2000)
        fund = self.asset('fund', opening_ore=3000, target_ore=12000)
        for asset, amount in [(goal, 500), (debt, 2000)]:
            MonthPlan.objects.create(household=self.house, created_by=self.user,
                asset=asset, month=self.prior, amount_ore=amount)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            category=self.category, month=self.prior, amount_ore=14000)
        self.bill('Old ordinary', 4000, self.prior)
        self.bill('Current ordinary', 6000, self.month)
        self.bill('Debt bill', 1500, self.month, 'debt', debt)
        self.bill('Old fund', 6000, self.prior, 'fund', fund)
        self.bill('Current fund', 7000, self.month, 'fund', fund)
        reader_user = get_user_model().objects.create_user(username='synthetic-money-reader')
        reader = Membership.objects.create(household=self.house, user=reader_user, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=reader, role='reader')
        with area_scope(reader, self.area.pk):
            before = self.read_only(lambda: services.calculate(self.house, self.month))
            basis = self.read_only(lambda: month_basis(self.house, self.month))
        self.assertEqual(before['bills'], 10000)
        self.assertEqual(before['savings'], 500)
        self.assertEqual(before['debt'], 2000)
        self.assertEqual(before['funds'], 7000)
        self.assertEqual(basis['category_limits'][self.category.pk], 14000)
        self.assertEqual(len(basis['pending']), 5)
        self.assertTrue(all(row['virtual'] for row in basis['pending']))
        self.assertFalse(BillOccurrence.objects.exists())
        self.assertFalse(FundTopUp.objects.exists())
        services.prepare_month(self.house, self.month)
        self.assertEqual(services.calculate(self.house, self.month), before)
        with area_scope(reader, self.area.pk):
            self.assertEqual(self.read_only(lambda: services.calculate(self.house, self.month)), before)
            self.assertEqual(month_basis(self.house, self.month)['fund_balances'][fund.pk],
                             services.fund_balance(fund, services.month_end(self.month)))

    def test_fund_projection_replays_payment_refund_and_unpaid_reservation_once(self):
        fund = self.asset('fund', opening_ore=3000, target_ore=12000)
        old = self.bill('Old fund payment', 6000, self.prior, 'fund', fund)
        services.prepare_month(self.house, self.prior)
        occurrence = BillOccurrence.objects.get(template=old)
        import uuid
        payment = services.pay_bill(self.user, occurrence.pk, self.prior, uuid.uuid4())
        services.save_entry(self.user, Entry(kind='refund', amount_ore=2000, original=payment,
            description='Synthetic fund refund', effective_date=self.month))
        self.bill('New fund obligation', 7000, self.month.replace(day=5), 'fund', fund)
        before = self.read_only(lambda: services.calculate(self.house, self.month))
        self.assertEqual(before['funds'], 5000)  # 1000 allocation + 4000 funding gap.
        self.assertEqual(before['cash'], 2000)
        self.assertEqual(before['ordinary'], 0)
        services.prepare_month(self.house, self.month)
        self.assertEqual(services.calculate(self.house, self.month), before)
        historical = self.read_only(lambda: services.calculate(self.house, self.prior))
        self.assertEqual(historical['funds'], 3000)
        self.assertEqual(historical['cash'], -6000)

    def test_future_actuals_do_not_hide_bills_or_increase_cash_but_forecasts_remain(self):
        as_of, future_day = self.month.replace(day=10), self.month.replace(day=20)
        template = self.bill('Known later bill', 5000, future_day)
        services.materialize_template(template, self.month)
        occurrence = BillOccurrence.objects.get(template=template)
        # Simulate imported dated rows, bypassing interactive no-future-entry validation.
        for kind, amount, received, linked in [('income', 10000, True, None),
                ('income', 3000, False, None), ('expense', 5000, True, occurrence)]:
            Entry.objects.create(household=self.house, created_by=self.user, kind=kind,
                amount_ore=amount, effective_date=future_day, received=received,
                occurrence=linked, category=self.category)
        values = self.read_only(lambda: services.calculate(self.house, self.month, today=as_of))
        self.assertEqual((values['income'], values['ordinary'], values['cash']), (0, 0, 0))
        self.assertEqual((values['expected'], values['bills'], values['available']), (3000, 5000, -5000))
        self.assertTrue(services.pending_bills(self.house, services.month_end(self.month), today=as_of).exists())
        self.assertEqual(len(month_basis(self.house, self.month, today=as_of)['pending']), 1)
        historical = services.calculate(self.house, self.month, today=services.next_month(self.month))
        self.assertEqual((historical['income'], historical['ordinary'], historical['cash']), (10000, 5000, 5000))
        self.assertEqual(historical['bills'], 0)
        self.assertIsNone(historical['daily'])

    def test_future_month_contains_known_plans_and_expected_income_without_actual_cash(self):
        goal = self.asset('savings')
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=goal, month=self.month, amount_ore=500)
        future = services.next_month(self.month)
        self.bill('Future planned bill', 1000, future)
        for received, amount in [(True, 9000), (False, 7000)]:
            Entry.objects.create(household=self.house, created_by=self.user, kind='income',
                received=received, amount_ore=amount, effective_date=future)
        before = self.read_only(lambda: services.calculate(self.house, future))
        self.assertEqual((before['income'], before['cash'], before['expected']), (0, 0, 7000))
        self.assertEqual((before['savings'], before['bills'], before['available']), (500, 1000, -1500))
        self.assertIsNone(before['daily'])
        services.prepare_month(self.house, future)
        self.assertEqual(services.calculate(self.house, future), before)

    def test_archived_future_carry_stops_but_explicit_future_plan_is_preserved(self):
        goal = self.asset('savings', archived=True)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=goal, month=self.month, amount_ore=500)
        future = services.next_month(self.month)
        self.assertEqual(month_basis(self.house, future)['asset_plans'].get(goal.pk, 0), 0)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=goal, month=future, amount_ore=200)
        self.assertEqual(month_basis(self.house, future)['asset_plans'][goal.pk], 200)

    def test_moved_and_cancelled_occurrences_do_not_reappear_as_virtual_slots(self):
        future = services.next_month(self.month)
        moved = self.bill('Moved bill', 1000, self.month)
        cancelled = self.bill('Cancelled bill', 2000, self.month)
        for template in (moved, cancelled):
            services.materialize_template(template, self.month)
        BillOccurrence.objects.filter(template=moved).update(due_date=future, individually_corrected=True)
        BillOccurrence.objects.filter(template=cancelled).update(cancelled=True)
        basis = self.read_only(lambda: month_basis(self.house, self.month))
        self.assertEqual(basis['pending'], [])
        later = self.read_only(lambda: month_basis(self.house, future))
        self.assertEqual([(row['name'], row['amount_ore'], row['virtual']) for row in later['pending']],
                         [('Moved bill', 1000, False)])
        before = services.calculate(self.house, future)
        services.prepare_month(self.house, future)
        self.assertEqual(services.calculate(self.house, future), before)

    def test_closed_derived_snapshot_is_preserved_while_missing_months_carry(self):
        goal = self.asset('savings')
        older = (self.prior - timedelta(days=1)).replace(day=1)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=goal, month=older, amount_ore=500)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=goal, month=self.prior, amount_ore=200, derived=True)
        self.assertEqual(month_basis(self.house, self.prior)['asset_plans'][goal.pk], 200)
        before = self.read_only(lambda: services.calculate(self.house, self.month))
        self.assertEqual(before['savings'], 500)
        services.prepare_month(self.house, self.month)
        self.assertEqual(services.calculate(self.house, self.month), before)
        self.assertEqual(MonthPlan.objects.get(asset=goal, month=self.prior).amount_ore, 200)

    def test_read_only_projection_rejects_foreign_household_and_uses_selected_area(self):
        other, foreign_house, _ = setup_family('money-foreign@example.test')
        with self.assertRaises(PermissionDenied):
            month_basis(foreign_house, self.month)
        self.bill('Private own bill', 2500, self.month)
        with area_scope(Membership.objects.get(user=other), other.test_area.pk):
            self.assertEqual(month_basis(foreign_house, self.month)['pending'], [])
            self.assertEqual(services.calculate(foreign_house, self.month)['bills'], 0)
