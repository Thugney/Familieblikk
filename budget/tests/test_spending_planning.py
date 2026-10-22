import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from budget.financial_areas import area_scope, create_area
from budget.financial_test_helpers import install_area, AreaClient
from budget.models import (Household, Membership, Category, Asset, Entry, MonthPlan, BillTemplate,
                           BillOccurrence, FundTopUp, ImportBatch, ImportRecord, Audit,
                           MonthlyBudgetHeader, PlanningRequest)
from budget import spending_services as sp
from budget.services import Conflict


def run_scoped(area, function, actor, *args, **kwargs):
    try:
        member = Membership.objects.get(user=actor)
    except Membership.DoesNotExist:
        return function(actor, *args, **kwargs)
    with area_scope(member, area.pk):
        return function(actor, *args, **kwargs)



TODAY = date(2026, 10, 20)


class SpendingPlanningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.house = Household.objects.create(name='Testhjem')
        cls.other = Household.objects.create(name='Annet testhjem')
        cls.admin = get_user_model().objects.create_user(username='plan-admin', password='Test-password-only-3344')
        cls.member = get_user_model().objects.create_user(username='plan-member', password='Test-password-only-3344')
        cls.foreign = get_user_model().objects.create_user(username='plan-foreign', password='Test-password-only-3344')
        cls.nofamily = get_user_model().objects.create_user(username='plan-alone', password='Test-password-only-3344')
        for user, house, role in [(cls.admin, cls.house, 'admin'), (cls.member, cls.house, 'member'), (cls.foreign, cls.other, 'admin')]:
            Membership.objects.create(user=user, household=house, role=role)
        cls.owner_membership = Membership.objects.get(user=cls.admin)
        cls.area = create_area(cls.owner_membership, reader_ids=[Membership.objects.get(user=cls.member).pk])
        with area_scope(cls.owner_membership, cls.area.pk):
            cls.cat = Category.objects.create(household=cls.house, created_by=cls.admin, name='Mat')
            cls.cat2 = Category.objects.create(household=cls.house, created_by=cls.admin, name='Hjem')
        foreign_member = Membership.objects.get(user=cls.foreign)
        cls.foreign_area = create_area(foreign_member)
        with area_scope(foreign_member, cls.foreign_area.pk):
            cls.foreign_cat = Category.objects.create(household=cls.other, created_by=cls.foreign, name='Privat kategori')


    def setUp(self):
        install_area(self, self.owner_membership, area=self.area)
        self.clock = patch('django.utils.timezone.localdate', return_value=TODAY)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def entry(self, amount=10000, day=date(2026, 9, 5), category=None, **kwargs):
        return Entry.objects.create(household=self.house, created_by=self.admin, kind='expense',
                                    amount_ore=amount, effective_date=day, category=category or self.cat,
                                    description='Butikk', **kwargs)

    def draft(self, actor=None):
        data = run_scoped(self.area, sp.planning, actor or self.admin)
        draft = data['draft']
        draft['expected_income_ore'] = 500000
        draft['acknowledge_incomplete'] = True
        for line in draft['categories']:
            line['other_ore'] = 10000
        for line in draft['assets']:
            if line['amount_ore'] is None:
                line['amount_ore'] = 0
        return draft

    def save_payload(self, draft=None):
        preview = run_scoped(self.area, sp.preview, self.admin, draft or self.draft())
        return {'draft': preview['draft'], 'confirmation_digest': preview['confirmation_digest'],
                'confirm': True, 'key': str(uuid.uuid4())}

    def test_all_categories_refund_across_months_negative_and_uncategorized(self):
        original = self.entry(amount=20000, day=date(2026, 8, 1))
        Entry.objects.create(household=self.house, created_by=self.admin, kind='refund', original=original,
                             amount_ore=15000, effective_date=date(2026, 9, 1), description='Tilbake')
        self.entry(amount=1000)
        for index in range(8):
            cat = Category.objects.create(household=self.house, created_by=self.admin, name=f'Kategori {index}')
            self.entry(amount=1000, category=cat)
        orphan = self.entry(amount=500)
        Entry.objects.filter(pk=orphan.pk).update(category=None)
        data = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-09'})
        self.assertEqual(data['total_ore'], -5500)
        self.assertEqual(len(data['categories']), 10)
        self.assertEqual(next(x['amount_ore'] for x in data['categories'] if x['id'] == str(self.cat.pk)), -14000)
        self.assertTrue(any(x['id'] == 'uncategorized' for x in data['categories']))

    def test_same_filters_feed_trend_graph_and_entries_and_period_total(self):
        self.entry(amount=20000)
        self.entry(amount=30000, category=self.cat2)
        self.entry(amount=9000, day=date(2026, 8, 1))
        data = run_scoped(self.area, sp.spending, self.admin, {'period': 'quarter', 'month': '2026-09', 'categories': str(self.cat.pk), 'q': 'butikk'})
        self.assertEqual(data['total_ore'], 29000)
        self.assertEqual(data['period_total_ore'], 59000)
        self.assertEqual(sum(x['amount_ore'] or 0 for x in data['trend']), 29000)
        self.assertEqual(sum(x['amount_ore'] for x in data['entries']), 29000)
        self.assertEqual(data['trend'][0]['status'], 'missing')
        self.assertIsNone(data['trend'][0]['amount_ore'])

    def test_income_and_asset_movement_excluded_from_consumption(self):
        self.entry()
        Entry.objects.create(household=self.house, created_by=self.admin, kind='income', amount_ore=100000,
                             effective_date=date(2026, 9, 1), description='Lønn')
        Entry.objects.create(household=self.house, created_by=self.admin, kind='income', amount_ore=20000, received=False,
                             effective_date=date(2026, 9, 2), description='Forventning')
        Entry.objects.create(household=self.house, created_by=self.admin, kind='deposit', amount_ore=30000,
                             effective_date=date(2026, 9, 3), description='Disponering')
        data = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-09', 'q': 'treff-finnes-ikke'})
        self.assertEqual(data['total_ore'], 0)
        self.assertEqual(data['period_total_ore'], 10000)
        self.assertEqual(data['income']['received_ore'], 100000)
        self.assertEqual(data['income']['expected_entries_ore'], 20000)

    def test_income_asset_and_filter_empty_months_are_missing_not_measured_zero(self):
        for kind, month in [('income', 8), ('deposit', 9)]:
            Entry.objects.create(household=self.house, created_by=self.admin, kind=kind, amount_ore=10000,
                                 effective_date=date(2026, month, 1), description='Annen aktivitet')
            data = run_scoped(self.area, sp.spending, self.admin, {'month': f'2026-{month:02d}'})
            self.assertEqual(data['total_ore'], 0)
            self.assertIsNone(data['trend'][0]['amount_ore'])
            self.assertFalse(data['trend'][0]['has_entries'])
            self.assertEqual(data['trend'][0]['status'], 'missing')
        original = self.entry(amount=10000)
        Entry.objects.create(household=self.house, created_by=self.admin, kind='refund', amount_ore=10000,
                             original=original, effective_date=date(2026, 9, 6), description='Full retur')
        measured = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-09'})
        self.assertEqual(measured['trend'][0]['amount_ore'], 0)
        self.assertTrue(measured['trend'][0]['has_entries'])
        self.assertEqual(measured['trend'][0]['entry_count'], 2)
        filtered = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-09', 'categories': str(self.cat2.pk)})
        self.assertEqual(filtered['total_ore'], 0)
        self.assertIsNone(filtered['trend'][0]['amount_ore'])

    def test_forecast_requires_monthly_custom_scope_and_names_whole_month(self):
        MonthlyBudgetHeader.objects.create(household=self.house, created_by=self.admin, month=date(2026, 9, 1), expected_income_ore=123000)
        partial = run_scoped(self.area, sp.spending, self.admin, {'period': 'custom', 'start': '2026-09-05', 'end': '2026-09-05'})
        self.assertIsNone(partial['income']['forecast_ore'])
        self.assertIn('delvis egendefinert', partial['income']['forecast_scope'])
        for params in [{'month': '2026-09'}, {'period': 'custom', 'start': '2026-09-01', 'end': '2026-09-30'}]:
            monthly = run_scoped(self.area, sp.spending, self.admin, params)
            self.assertEqual(monthly['income']['forecast_ore'], 123000)
            self.assertIn('hele månedsplaner 2026-09', monthly['income']['forecast_scope'])

    def test_annual_ytd_forecast_coverage_excludes_future_trend_months(self):
        for month in range(1, 13):
            MonthlyBudgetHeader.objects.create(household=self.house, created_by=self.admin, month=date(2026, month, 1),
                                              expected_income_ore=10000 * month)
        data = run_scoped(self.area, sp.spending, self.admin, {'period': 'year', 'year': '2026'})
        self.assertEqual(len(data['trend']), 12)
        self.assertEqual(data['income']['forecast_ore'], sum(10000 * month for month in range(1, 11)))
        self.assertIn('hele månedsplaner 2026-01–2026-10', data['income']['forecast_scope'])
        MonthlyBudgetHeader.objects.filter(household=self.house, month=date(2026, 10, 1)).delete()
        incomplete = run_scoped(self.area, sp.spending, self.admin, {'period': 'year', 'year': '2026'})
        self.assertIsNone(incomplete['income']['forecast_ore'])
        self.assertIn('ikke fullstendig', incomplete['income']['forecast_scope'])

    def test_clamps_future_actual_rows_and_custom_inclusive(self):
        self.entry(day=TODAY)
        self.entry(day=date(2026, 10, 21))
        data = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-10'})
        self.assertEqual(data['total_ore'], 10000)
        self.assertTrue(data['period']['to_today'])
        data = run_scoped(self.area, sp.spending, self.admin, {'period': 'custom', 'start': '2026-10-20', 'end': '2026-10-20'})
        self.assertEqual(data['total_ore'], 10000)

    def test_future_only_period_is_rejected_without_inverted_range(self):
        with self.assertRaisesMessage(ValidationError, 'Perioden har ikke startet'):
            run_scoped(self.area, sp.spending, self.admin, {'month': '2026-11'})
        response = AreaClient(self.area)
        response.force_login(self.admin)
        self.assertEqual(response.get('/app/forbruk/data/?month=2026-11').status_code, 400)

    def test_pagination_and_tenant_filter(self):
        for _ in range(25):
            self.entry()
        with area_scope(Membership.objects.get(user=self.foreign), self.foreign_area.pk):
            Entry.objects.create(household=self.other, created_by=self.foreign, kind='expense', amount_ore=999999,
                                 effective_date=date(2026, 9, 1), category=self.foreign_cat, description='Hemmelig')
        data = run_scoped(self.area, sp.spending, self.admin, {'month': '2026-09', 'page': '2'})
        self.assertEqual(data['pagination']['count'], 25)
        self.assertEqual(len(data['entries']), 5)
        self.assertNotIn('Hemmelig', json.dumps(data))
        with self.assertRaises(ValidationError):
            run_scoped(self.area, sp.spending, self.admin, {'categories': str(self.foreign_cat.pk)})

    def test_get_and_preview_do_not_materialize_or_change_finance(self):
        BillTemplate.objects.create(household=self.house, created_by=self.admin, name='Husleie', amount_ore=120000,
                                     first_due=date(2026, 9, 1), category=self.cat2)
        before = {m: m.objects.count() for m in [MonthPlan, BillOccurrence, FundTopUp, Entry, Audit, MonthlyBudgetHeader]}
        data = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual(len(data['commitments']), 3)
        self.assertEqual(data['totals']['ordinary_fixed_ore'], 360000)
        self.assertIsNone(data['totals']['planned_remainder_ore'])
        self.assertTrue(data['no_savings_goals'])
        run_scoped(self.area, sp.preview, self.admin, self.draft())
        self.assertEqual(before, {m: m.objects.count() for m in before})

    def test_history_average_excludes_bill_payment_and_unknown_month_does_not_become_zero(self):
        self.entry(amount=30000, day=date(2026, 8, 1))
        self.entry(amount=50000, day=date(2026, 9, 1))
        data = run_scoped(self.area, sp.planning, self.admin, history=['2026-08', '2026-09'])
        line = next(x for x in data['categories'] if x['id'] == str(self.cat.pk))
        self.assertEqual(line['other_ore'], 40000)
        self.assertEqual(line['observations'], 2)
        self.assertTrue(data['coverage']['requires_acknowledgement'])
        missing = run_scoped(self.area, sp.planning, self.admin, history=['2026-07', '2026-09'])
        self.assertIsNone(next(x for x in missing['categories'] if x['id'] == str(self.cat.pk))['other_ore'])

    def test_refund_negative_average_requires_manual_nonnegative_budget(self):
        original = self.entry(amount=20000, day=date(2026, 8, 1))
        Entry.objects.create(household=self.house, created_by=self.admin, kind='refund', amount_ore=10000,
                             effective_date=date(2026, 9, 1), original=original, category=self.cat, description='Retur')
        line = next(x for x in run_scoped(self.area, sp.planning, self.admin, history=['2026-09'])['categories'] if x['id'] == str(self.cat.pk))
        self.assertEqual(line['historical_average_ore'], -10000)
        self.assertIsNone(line['other_ore'])

    def test_import_draft_warning_ignores_raw_amount(self):
        batch = ImportBatch.objects.create(household=self.house, created_by=self.admin, series='synthetic', sha256='a' * 64)
        ImportRecord.objects.create(household=self.house, created_by=self.admin, batch=batch,
                                    source_id='synthetic-1', source_kind='expense', raw={'amount': 99999999})
        data = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual(data['coverage']['unresolved_import_count'], 1)
        self.assertNotIn('99999999', json.dumps(data))

    def test_income_only_months_never_attest_expense_completeness(self):
        for month in (7, 8, 9):
            Entry.objects.create(household=self.house, created_by=self.admin, kind='income', amount_ore=100000,
                                 effective_date=date(2026, month, 1), description='Lønn')
        data = run_scoped(self.area, sp.planning, self.admin, history=['2026-07', '2026-08', '2026-09'])
        self.assertTrue(data['coverage']['requires_acknowledgement'])
        self.assertTrue(all(x['status'] == 'partial' for x in data['history_options']))
        self.assertTrue(all(x['other_ore'] is None for x in data['categories']))
        self.assertFalse(data['coverage']['completeness_confirmed'])
        annual = run_scoped(self.area, sp.spending, self.admin, {'period': 'year', 'year': '2026'})
        self.assertTrue(all(x['status'] != 'completed' for x in annual['trend']))

    def test_category_absence_in_one_source_month_is_unknown_not_zero(self):
        self.entry(amount=30000, day=date(2026, 8, 1))
        self.entry(amount=90000, day=date(2026, 9, 1), category=self.cat2)
        data = run_scoped(self.area, sp.planning, self.admin, history=['2026-08', '2026-09'])
        line = next(x for x in data['categories'] if x['id'] == str(self.cat.pk))
        self.assertIsNone(line['historical_average_ore'])
        self.assertIsNone(line['other_ore'])
        self.assertEqual(line['observed_months'], 1)

    def test_history_explicitly_replaces_existing_plan_suggestion(self):
        MonthPlan.objects.create(household=self.house, created_by=self.admin, category=self.cat, month=date(2026, 11, 1), amount_ore=999000)
        self.entry(amount=40000)
        line = next(x for x in run_scoped(self.area, sp.planning, self.admin, history=['2026-09'])['categories'] if x['id'] == str(self.cat.pk))
        self.assertEqual(line['other_ore'], 40000)
        self.assertEqual(line['historical_other_ore'], 40000)
        self.assertEqual(line['source'], 'history')

    def test_unmaterialized_prior_bill_months_carry_but_paid_occurrences_do_not(self):
        template = BillTemplate.objects.create(household=self.house, created_by=self.admin, name='Husleie', amount_ore=10000,
                                     first_due=date(2026, 8, 31), category=self.cat)
        paid = BillOccurrence.objects.create(household=self.house, created_by=self.admin, template=template, name='Husleie',
                        due_date=date(2026, 9, 29), amount_ore=10000, accounting_class='ordinary', category=self.cat)
        self.entry(amount=10000, occurrence=paid)
        data = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual([b['due_date'] for b in data['commitments']], ['2026-08-31', '2026-10-31', '2026-11-30'])
        self.assertEqual(data['totals']['ordinary_fixed_ore'], 30000)
        self.assertEqual(BillOccurrence.objects.count(), 1)

    def test_fixed_category_debt_and_fund_not_doubled(self):
        debt = Asset.objects.create(household=self.house, created_by=self.admin, kind='debt', name='Gjeld', opening_ore=500000,
                                     opening_date=date(2026, 9, 1), minimum_ore=25000)
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Årsfond', opening_ore=50000,
                                     opening_date=date(2026, 9, 1), target_ore=0)
        for name, kind, amount, asset in [('Husleie', 'ordinary', 100000, None), ('Gjeld', 'debt', 30000, debt), ('Årsregning', 'fund', 80000, fund)]:
            BillTemplate.objects.create(household=self.house, created_by=self.admin, name=name, accounting_class=kind,
                                         amount_ore=amount, first_due=date(2026, 11, 5), category=self.cat2 if kind == 'ordinary' else None, asset=asset)
        draft = self.draft()
        for line in draft['assets']:
            line['amount_ore'] = 20000
        preview = run_scoped(self.area, sp.preview, self.admin, draft)
        self.assertEqual(preview['totals']['ordinary_fixed_ore'], 100000)
        self.assertEqual(preview['totals']['other_categories_ore'], 20000)
        self.assertEqual(preview['totals']['debt_ore'], 30000)
        self.assertEqual(preview['totals']['funds_ore'], 30000)  # 20 allocation + 10 gap; not 80 bill again
        self.assertEqual(preview['totals']['planned_remainder_ore'], 320000)

    def test_edited_debt_plan_cannot_lower_known_minimum_deduction(self):
        debt = Asset.objects.create(household=self.house, created_by=self.admin, kind='debt', name='Minstebeløp',
                                    opening_date=date(2026, 9, 1), opening_ore=100000, minimum_ore=25000)
        data = run_scoped(self.area, sp.planning, self.admin)
        asset = next(x for x in data['assets'] if x['id'] == str(debt.pk))
        self.assertEqual(asset['obligation_ore'], 25000)
        draft = self.draft()
        draft['assets'][0]['amount_ore'] = 0
        self.assertEqual(run_scoped(self.area, sp.preview, self.admin, draft)['totals']['debt_ore'], 25000)
        run_scoped(self.area, sp.save_plan, self.admin, self.save_payload(draft))
        fresh = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual(fresh['assets'][0]['amount_ore'], 0)
        self.assertEqual(fresh['assets'][0]['obligation_ore'], 25000)
        self.assertEqual(fresh['totals']['debt_ore'], 25000)

    def test_fund_reserves_previous_unpaid_and_multiple_bills_once(self):
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Fond', opening_ore=100000,
                                     opening_date=date(2026, 9, 1))
        for index, (day, amount) in enumerate([(date(2026, 10, 1), 60000), (date(2026, 11, 1), 50000), (date(2026, 11, 2), 50000)]):
            template = BillTemplate.objects.create(household=self.house, created_by=self.admin, name=f'Årsregning {index}',
                         accounting_class='fund', amount_ore=amount, first_due=day, monthly=False, asset=fund)
            if day.month == 10:
                BillOccurrence.objects.create(household=self.house, created_by=self.admin, template=template, name=template.name,
                         due_date=day, amount_ore=amount, accounting_class='fund', asset=fund)
        draft = self.draft()
        draft['assets'][0]['amount_ore'] = 20000
        totals = run_scoped(self.area, sp.preview, self.admin, draft)['totals']
        self.assertEqual(totals['funds_ore'], 60000)  # available 40, target need100:20 allocation+40 topup

    def test_fund_forecasts_missing_historical_annual_allocations_without_writes(self):
        from budget.services import prepare_month, fund_balance
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Årsplan',
                        opening_date=date(2026, 9, 1), opening_ore=0, target_ore=120000)
        projected = sp.fund_available_before(self.house, fund, date(2026, 12, 1), [])
        self.assertEqual(projected, 30000)  # September, October and November, including unmaterialized September.
        self.assertEqual(MonthPlan.objects.count(), 0)
        prepare_month(self.house, date(2026, 11, 1))
        self.assertEqual(projected, fund_balance(fund, date(2026, 11, 30)))
        self.assertEqual(sp.fund_available_before(self.house, fund, date(2026, 12, 1), []), projected)

    def test_fund_forecasts_missing_months_from_explicit_anchor_exactly_once(self):
        from budget.services import prepare_month, fund_balance
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Månedsplan',
                        opening_date=date(2026, 8, 1), opening_ore=5000)
        MonthPlan.objects.create(household=self.house, created_by=self.admin, asset=fund, month=date(2026, 8, 1), amount_ore=10000)
        projected = sp.fund_available_before(self.house, fund, date(2026, 12, 1), [])
        self.assertEqual(projected, 45000)  # Existing August plus missing September, October and November.
        self.assertEqual(MonthPlan.objects.count(), 1)
        prepare_month(self.house, date(2026, 11, 1))
        self.assertEqual(projected, fund_balance(fund, date(2026, 11, 30)))

    def test_fund_future_explicit_anchor_does_not_invent_earlier_annual_allocations(self):
        from budget.services import prepare_month, fund_balance
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Senere plan',
                        opening_date=date(2026, 9, 1), opening_ore=0, target_ore=120000)
        MonthPlan.objects.create(household=self.house, created_by=self.admin, asset=fund, month=date(2026, 11, 1), amount_ore=20000)
        projected = sp.fund_available_before(self.house, fund, date(2026, 12, 1), [])
        self.assertEqual(projected, 20000)
        self.assertEqual(MonthPlan.objects.count(), 1)
        prepare_month(self.house, date(2026, 11, 1))
        self.assertEqual(projected, fund_balance(fund, date(2026, 11, 30)))

    def test_materialized_moved_day_suppresses_virtual_and_overdue_is_included(self):
        template = BillTemplate.objects.create(household=self.house, created_by=self.admin, name='Vanlig', amount_ore=40000,
                         first_due=date(2026, 10, 5), category=self.cat)
        for due in [date(2026, 10, 7), date(2026, 11, 9)]:
            BillOccurrence.objects.create(household=self.house, created_by=self.admin, template=template, name='Flyttet',
                         due_date=due, amount_ore=40000, accounting_class='ordinary', category=self.cat)
        data = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual(len(data['commitments']), 2)
        self.assertEqual(data['totals']['ordinary_fixed_ore'], 80000)

    def test_unknown_amounts_acknowledgement_and_typed_values(self):
        draft = run_scoped(self.area, sp.planning, self.admin)['draft']
        with self.assertRaises(ValidationError):
            run_scoped(self.area, sp.preview, self.admin, draft)
        draft = self.draft()
        for value in [True, -1, 1.5, '100', None]:
            modified = copy.deepcopy(draft)
            modified['expected_income_ore'] = value
            with self.assertRaises(ValidationError):
                run_scoped(self.area, sp.preview, self.admin, modified)
        draft['acknowledge_incomplete'] = False
        with self.assertRaises(ValidationError):
            run_scoped(self.area, sp.preview, self.admin, draft)

    def test_duplicate_missing_foreign_lines_and_past_target_rejected(self):
        draft = self.draft()
        for mutated in [draft['categories'] + [draft['categories'][0]], draft['categories'][:1],
                        [{'id': str(self.foreign_cat.pk), 'other_ore': 0}, draft['categories'][1]]]:
            value = copy.deepcopy(draft)
            value['categories'] = mutated
            with self.assertRaises(ValidationError):
                run_scoped(self.area, sp.preview, self.admin, value)
        for target in ['2026-09', '2026-10']:
            with self.assertRaises(ValidationError):
                run_scoped(self.area, sp.planning, self.admin, target_month=target)

    def test_explicit_atomic_save_preserves_actuals_historical_and_other_target_months(self):
        original = self.entry()
        old = MonthPlan.objects.create(household=self.house, created_by=self.admin, month=date(2026, 9, 1), category=self.cat, amount_ore=10000)
        future = MonthPlan.objects.create(household=self.house, created_by=self.admin, month=date(2026, 12, 1), category=self.cat, amount_ore=10000, derived=True, annual_total_ore=120000)
        payload = self.save_payload()
        entry_before = list(Entry.objects.values())
        result = run_scoped(self.area, sp.save_plan, self.admin, payload)
        self.assertTrue(result['saved'])
        self.assertEqual(list(Entry.objects.values()), entry_before)
        old.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(old.amount_ore, 10000)
        self.assertEqual(future.annual_total_ore, 120000)
        header = MonthlyBudgetHeader.objects.get(household=self.house)
        self.assertEqual(header.expected_income_ore, 500000)
        self.assertEqual(Audit.objects.filter(operation='månedsplan bekreftet').count(), 1)
        self.assertEqual(run_scoped(self.area, sp.save_plan, self.admin, payload), result)
        self.assertEqual(PlanningRequest.objects.count(), 1)
        self.assertEqual(Entry.objects.get(pk=original.pk).amount_ore, 10000)

    def test_member_can_read_and_preview_but_cannot_save(self):
        self.assertFalse(run_scoped(self.area, sp.planning, self.member)['can_save'])
        run_scoped(self.area, sp.preview, self.member, self.draft(self.member))
        with self.assertRaises(PermissionDenied):
            run_scoped(self.area, sp.save_plan, self.member, self.save_payload())
        self.assertEqual(MonthlyBudgetHeader.objects.count(), 0)
        with self.assertRaises(PermissionDenied):
            run_scoped(self.area, sp.planning, self.nofamily)

    def test_source_changes_and_new_plan_invalidate_snapshot(self):
        payload = self.save_payload()
        self.entry()
        with self.assertRaises(Conflict):
            run_scoped(self.area, sp.save_plan, self.admin, payload)
        self.assertEqual(MonthlyBudgetHeader.objects.count(), 0)
        payload = self.save_payload()
        MonthPlan.objects.create(household=self.house, created_by=self.admin, category=self.cat, month=date(2026, 11, 1), amount_ore=10)
        with self.assertRaises(Conflict):
            run_scoped(self.area, sp.save_plan, self.admin, payload)

    def test_source_revision_is_independent_of_selected_history_but_tracks_financial_changes(self):
        self.entry()
        baseline = run_scoped(self.area, sp.planning, self.admin)
        selected = run_scoped(self.area, sp.planning, self.admin, history=['2026-09'])
        self.assertEqual(baseline['source_revision'], selected['source_revision'])
        self.assertNotEqual(baseline['snapshot'], selected['snapshot'])
        self.entry(amount=20000)
        self.assertNotEqual(run_scoped(self.area, sp.planning, self.admin)['source_revision'], baseline['source_revision'])

    def test_late_validation_failure_rolls_back_every_target_and_header(self):
        payload = self.save_payload()
        original_save = MonthPlan.save
        def fail_second(row, *args, **kwargs):
            if row.category_id == self.cat2.pk:
                raise ValidationError('Syntetisk feil i andre planlinje.')
            return original_save(row, *args, **kwargs)
        with patch.object(MonthPlan, 'save', fail_second):
            with self.assertRaises(ValidationError):
                run_scoped(self.area, sp.save_plan, self.admin, payload)
        self.assertEqual(MonthlyBudgetHeader.objects.count(), 0)
        self.assertEqual(MonthPlan.objects.count(), 0)
        self.assertEqual(PlanningRequest.objects.count(), 0)
        self.assertEqual(Audit.objects.count(), 0)

    def test_saved_target_clears_annual_override_and_keeps_creator(self):
        target = MonthPlan.objects.create(household=self.house, created_by=self.member, month=date(2026, 11, 1),
                        category=self.cat, amount_ore=10000, annual_total_ore=120000, derived=True)
        run_scoped(self.area, sp.save_plan, self.admin, self.save_payload())
        target.refresh_from_db()
        self.assertFalse(target.derived)
        self.assertIsNone(target.annual_total_ore)
        self.assertEqual(target.created_by_id, self.member.pk)

    def test_distinct_edited_category_and_asset_amounts_persist_and_reload(self):
        goal = Asset.objects.create(household=self.house, created_by=self.admin, kind='savings', name='Ferie',
                                    opening_date=date(2026, 9, 1), target_ore=1000000)
        BillTemplate.objects.create(household=self.house, created_by=self.admin, name='Fast i november', amount_ore=30000,
                                    first_due=date(2026, 11, 5), category=self.cat)
        category_plan = MonthPlan.objects.create(household=self.house, created_by=self.member, month=date(2026, 11, 1),
                                                category=self.cat, amount_ore=80000)
        asset_plan = MonthPlan.objects.create(household=self.house, created_by=self.member, month=date(2026, 11, 1),
                                             asset=goal, amount_ore=12000)
        baseline = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual(next(x for x in baseline['categories'] if x['id'] == str(self.cat.pk))['other_ore'], 50000)
        self.assertEqual(baseline['assets'][0]['amount_ore'], 12000)
        draft = self.draft()
        for category in draft['categories']:
            category['other_ore'] = 47000 if category['id'] == str(self.cat.pk) else 9000
        draft['assets'][0]['amount_ore'] = 23000
        payload = self.save_payload(draft)
        change = next(x for x in run_scoped(self.area, sp.preview, self.admin, draft)['changes'] if x['id'] == str(self.cat.pk))
        self.assertEqual((change['before_ore'], change['after_ore']), (80000, 77000))
        run_scoped(self.area, sp.save_plan, self.admin, payload)
        category_plan.refresh_from_db()
        asset_plan.refresh_from_db()
        self.assertEqual(category_plan.amount_ore, 77000)
        self.assertEqual(asset_plan.amount_ore, 23000)
        self.assertEqual((category_plan.version, asset_plan.version), (2, 2))
        fresh = run_scoped(self.area, sp.planning, self.admin)
        line = next(x for x in fresh['categories'] if x['id'] == str(self.cat.pk))
        self.assertEqual((line['fixed_ore'], line['other_ore'], line['total_ore']), (30000, 47000, 77000))
        self.assertEqual(fresh['assets'][0]['amount_ore'], 23000)
        self.assertEqual(fresh['totals']['other_categories_ore'], 56000)
        self.assertEqual(fresh['totals']['savings_ore'], 23000)
        self.assertEqual(fresh['totals']['planned_remainder_ore'], 391000)

    def test_archived_financial_obligations_remain_visible(self):
        debt = Asset.objects.create(household=self.house, created_by=self.admin, kind='debt', name='Arkivert gjeld',
                        opening_ore=500000, opening_date=date(2026, 9, 1), minimum_ore=10000, archived=True)
        fund = Asset.objects.create(household=self.house, created_by=self.admin, kind='fund', name='Arkivert fond',
                        opening_date=date(2026, 9, 1), archived=True)
        MonthPlan.objects.create(household=self.house, created_by=self.admin, asset=fund, month=date(2026, 9, 1), amount_ore=20000)
        data = run_scoped(self.area, sp.planning, self.admin)
        self.assertEqual({x['id'] for x in data['assets']}, {str(debt.pk), str(fund.pk)})
        self.assertEqual(data['totals']['debt_ore'], 10000)
        self.assertEqual(data['totals']['funds_ore'], 20000)

    def test_receipt_reuse_and_changed_confirmation_rejected(self):
        payload = self.save_payload()
        changed = copy.deepcopy(payload)
        changed['confirmation_digest'] = 'a' * 64
        with self.assertRaises(Conflict):
            run_scoped(self.area, sp.save_plan, self.admin, changed)
        run_scoped(self.area, sp.save_plan, self.admin, payload)
        changed = copy.deepcopy(payload)
        changed['draft']['expected_income_ore'] = 0
        with self.assertRaises(Conflict):
            run_scoped(self.area, sp.save_plan, self.admin, changed)

    def test_database_guards_new_tenant_relationships(self):
        for model, values in [
            (MonthlyBudgetHeader, dict(household=self.other, created_by=self.admin, month=date(2026, 11, 1))),
            (PlanningRequest, dict(household=self.other, actor=self.admin, digest='a' * 64)),
            (MonthlyBudgetHeader, dict(household=self.house, created_by=self.admin, month=date(2026, 11, 2))),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.all_objects.bulk_create([model(financial_area=self.area, **values)])
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_api_permissions_cache_csrf_and_json_validation(self):
        client = AreaClient(self.area)
        self.assertEqual(client.get('/app/forbruk/data/').status_code, 403)
        client.force_login(self.nofamily)
        self.assertEqual(client.get('/app/plan/data/').status_code, 403)
        client.force_login(self.admin)
        response = client.get('/app/forbruk/data/?month=2026-09')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        response = client.post('/app/plan/preview/', data='[]', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = client.post('/app/plan/preview/', data='{bad', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        secure = AreaClient(self.area, enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post('/app/plan/save/', data='{}', content_type='application/json').status_code, 403)


class SpendingPlanningConcurrencyTests(TransactionTestCase):
    """Independent PostgreSQL connections exercise actual row-lock serialization."""

    def setUp(self):
        self.clock = patch('django.utils.timezone.localdate', return_value=TODAY)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.house = Household.objects.create(name='Samtidig testhjem')
        self.admin = get_user_model().objects.create_user(username='concurrent-plan-admin')
        member = Membership.objects.create(user=self.admin, household=self.house, role='admin')
        install_area(self, member)
        self.cat = Category.objects.create(household=self.house, created_by=self.admin, name='Mat')

    def payload(self):
        draft = run_scoped(self.area, sp.planning, self.admin)['draft']
        draft['expected_income_ore'] = 100000
        draft['categories'][0]['other_ore'] = 22000
        draft['acknowledge_incomplete'] = True
        candidate = run_scoped(self.area, sp.preview, self.admin, draft)
        return {'draft': candidate['draft'], 'confirmation_digest': candidate['confirmation_digest'],
                'confirm': True, 'key': str(uuid.uuid4())}

    @staticmethod
    def worker(callback):
        close_old_connections()
        try:
            return callback()
        finally:
            connection.close()

    def competing_saves(self, first, second):
        barrier = Barrier(2)
        def save(payload):
            barrier.wait(timeout=10)
            try:
                return ('saved', run_scoped(self.area, sp.save_plan, self.admin, payload))
            except Conflict:
                return ('conflict', None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, lambda payload=p: save(payload)) for p in (first, second)]
            return [future.result(timeout=20) for future in futures]

    def test_simultaneous_same_key_saves_return_one_idempotent_result(self):
        payload = self.payload()
        results = self.competing_saves(payload, copy.deepcopy(payload))
        self.assertEqual([status for status, _ in results], ['saved', 'saved'])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(MonthlyBudgetHeader.objects.count(), 1)
        self.assertEqual(MonthPlan.objects.count(), 1)
        self.assertEqual(MonthPlan.objects.get().amount_ore, 22000)
        self.assertEqual(MonthPlan.objects.get().version, 1)
        self.assertEqual(PlanningRequest.objects.count(), 1)
        self.assertEqual(Audit.objects.filter(operation='månedsplan bekreftet').count(), 1)

    def test_simultaneous_different_keys_reject_losing_stale_snapshot(self):
        first = self.payload()
        second = copy.deepcopy(first)
        second['key'] = str(uuid.uuid4())
        results = self.competing_saves(first, second)
        self.assertEqual(sorted(status for status, _ in results), ['conflict', 'saved'])
        self.assertEqual(MonthlyBudgetHeader.objects.count(), 1)
        self.assertEqual(MonthPlan.objects.count(), 1)
        self.assertEqual(MonthPlan.objects.get().version, 1)
        self.assertEqual(PlanningRequest.objects.count(), 1)

    def test_planning_read_waits_for_source_writer_and_pairs_values_with_revision(self):
        row = Entry.objects.create(household=self.house, created_by=self.admin, kind='expense', amount_ore=10000,
                                   effective_date=date(2026, 9, 5), category=self.cat, description='Mat')
        writer_locked = Event()
        permit_commit = Event()
        reader_started = Event()
        reader_finished = Event()

        def writer():
            with area_scope(Membership.objects.get(user=self.admin), self.area.pk), transaction.atomic():
                Household.objects.select_for_update().get(pk=self.house.pk)
                Entry.objects.filter(pk=row.pk).update(amount_ore=47000, version=2)
                writer_locked.set()
                if not permit_commit.wait(timeout=10):
                    raise AssertionError('Reader did not release the source writer.')

        def reader():
            reader_started.set()
            try:
                return run_scoped(self.area, sp.planning, self.admin, history=['2026-09'])
            finally:
                reader_finished.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(self.worker, writer)
            self.assertTrue(writer_locked.wait(timeout=10))
            reading = pool.submit(self.worker, reader)
            self.assertTrue(reader_started.wait(timeout=10))
            try:
                self.assertFalse(reader_finished.wait(timeout=0.5), 'Planning read escaped the active household source lock.')
            finally:
                permit_commit.set()
            writing.result(timeout=20)
            candidate = reading.result(timeout=20)
        fresh = run_scoped(self.area, sp.planning, self.admin, history=['2026-09'])
        self.assertEqual(candidate['categories'][0]['other_ore'], 47000)
        self.assertEqual(candidate['source_revision'], fresh['source_revision'])
        self.assertEqual(candidate['snapshot'], fresh['snapshot'])
