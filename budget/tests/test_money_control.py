from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from budget import money_control, services
from budget.financial_areas import area_scope, create_area
from budget.financial_models import FinancialAreaGrant
from budget.models import Asset, BillTemplate, BillOccurrence, Category, Entry, Household, Membership, MonthPlan, ImportBatch, ImportRecord


@override_settings(ALLOWED_HOSTS=['testserver'])
class MoneyControlTests(TestCase):
    def setUp(self):
        self.today = date(2026, 10, 23)
        self.month = self.today.replace(day=1)
        self.clock = patch('django.utils.timezone.localdate', return_value=self.today)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.user = get_user_model().objects.create_user(username='control')
        self.house = Household.objects.create(name='Synthetic control')
        self.member = Membership.objects.create(user=self.user, household=self.house, role='admin')
        self.area = create_area(self.member, 'Synthetic budget')
        self.scope = area_scope(self.member, self.area.pk)
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.food = Category.objects.create(household=self.house, created_by=self.user, name='Food')
        self.client.force_login(self.user)

    def entry(self, kind, amount, **kwargs):
        return Entry.objects.create(household=self.house, created_by=self.user, kind=kind,
            amount_ore=amount, effective_date=kwargs.pop('effective_date', self.today), **kwargs)

    def limit(self, amount, category=None):
        return MonthPlan.objects.create(household=self.house, created_by=self.user,
            category=category or self.food, month=self.month, amount_ore=amount)

    def report(self, month=None):
        month = month or self.month
        return money_control.overview(self.member, month, services.calculate(self.house, month), today=self.today)

    def test_remaining_category_plan_does_not_reserve_unpaid_bill_twice(self):
        self.entry('income', 100000)
        paid = self.entry('expense', 20000, category=self.food)
        self.entry('refund', 5000, original=paid)
        self.limit(50000)
        BillTemplate.objects.create(household=self.house, created_by=self.user, category=self.food,
            name='Known bill', amount_ore=10000, first_due=date(2026, 10, 28))
        services.prepare_month(self.house, self.month)
        report = self.report()
        self.assertEqual(report['ordinary_gross'], 20000)
        self.assertEqual(report['ordinary_refunds'], 5000)
        self.assertEqual(report['remaining_categories'], 25000)
        self.assertEqual(report['plan_remainder'], 50000)
        self.assertEqual(report['rows'][0]['pending'], 10000)

    def test_money_flow_separates_transfers_and_debt_fund_refunds(self):
        self.entry('income', 100000)
        self.entry('income', 80000, received=False)
        expense = self.entry('expense', 10000, category=self.food)
        self.entry('refund', 2000, original=expense)
        for kind, payment_kind, amount in [('savings', 'deposit', 15000), ('debt', 'debt', 10000), ('fund', 'fund', 5000)]:
            asset = Asset.objects.create(household=self.house, created_by=self.user, kind=kind,
                name=kind, opening_date=self.month, opening_ore=50000)
            original = self.entry(payment_kind, amount, asset=asset)
            if kind == 'savings':
                self.entry('withdrawal', 3000, asset=asset)
            else:
                self.entry('refund', 1000, original=original, asset=asset)
        report = self.report()
        self.assertEqual(report['ordinary_net'], 8000)
        self.assertEqual(report['cash_in'], 107000)
        self.assertEqual(report['cash_out'], 40000)
        self.assertEqual(report['cash_net'], 67000)
        self.assertEqual(report['cash_net'], services.calculate(self.house, self.month)['cash'])

    def test_refund_in_other_category_cannot_hide_zero_limit_excess(self):
        self.limit(0)
        self.entry('expense', 10000, category=self.food)
        other = Category.objects.create(household=self.house, created_by=self.user, name='Other')
        old = self.entry('expense', 50000, category=other, effective_date=date(2026, 9, 1))
        self.entry('refund', 40000, original=old)
        report = self.report()
        self.assertEqual(report['ordinary_net'], -30000)
        food = next(row for row in report['rows'] if row['name'] == 'Food')
        self.assertEqual(food['over'], 10000)
        self.assertEqual(food['limit'], 0)
        self.assertTrue(any(n['title'] == 'Over kategorirammene' for n in report['notices']))

    def test_missing_limits_archived_and_uncategorized_are_visible(self):
        self.food.archived = True
        self.food.save()
        self.entry('expense', 5000, category=self.food)
        self.entry('expense', 3000)
        report = self.report()
        self.assertEqual(sum(row['gross'] for row in report['rows']), 8000)
        self.assertTrue(next(row for row in report['rows'] if row['name'] == 'Food')['archived'])
        self.assertTrue(any(row['uncategorized'] for row in report['rows']))
        self.assertTrue(all(row['limit'] is None for row in report['rows']))
        self.assertTrue(any(n['title'] == 'Pengebruk uten månedsramme' for n in report['notices']))

    def test_positive_available_can_still_have_unfunded_category_plan(self):
        self.entry('income', 10000)
        self.limit(30000)
        report = self.report()
        self.assertEqual(report['plan_remainder'], -20000)
        self.assertTrue(any(n['title'] == 'Månedsrammene mangler dekning' for n in report['notices']))
        self.assertFalse(any(n['title'] == 'Vurder buffer før ekstra forbruk' for n in report['notices']))

    def test_incomplete_import_discloses_drafts_and_suppresses_savings_suggestion(self):
        self.entry('income', 100000)
        self.entry('expense', 10000, category=self.food)
        self.limit(20000)
        batch = ImportBatch.objects.create(household=self.house, created_by=self.user,
            series='synthetic-control', sha256='c' * 64)
        ImportRecord.objects.create(household=self.house, created_by=self.user, batch=batch,
            source_id='synthetic-draft', source_kind='expenses', raw={}, status='needs_review')
        report = self.report()
        self.assertEqual(report['coverage']['unresolved_import_count'], 1)
        self.assertFalse(any(n['title'] == 'Vurder buffer før ekstra forbruk' for n in report['notices']))

    def test_read_only_report_and_area_links(self):
        self.entry('expense', 5000, category=self.food)
        totals = services.calculate(self.house, self.month)
        with CaptureQueriesContext(connection) as queries:
            report = money_control.overview(self.member, self.month, totals)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        for link in [report['entries_url'], report['categories_url'], report['rows'][0]['entries_url']]:
            self.assertIn('area=' + str(self.area.pk), link)

    def test_other_budget_is_excluded_and_restricted_member_cannot_get_summary(self):
        other = create_area(self.member, 'Private other budget')
        with area_scope(self.member, other.pk):
            hidden = Category.objects.create(household=self.house, created_by=self.user, name='Hidden other category')
            self.entry('expense', 900000, category=hidden)
        self.assertEqual(self.report()['ordinary_net'], 0)
        self.member.module_access = {'savings': False}
        self.member.save()
        with self.assertRaises(PermissionDenied):
            self.report()
        response = self.client.get('/app/oversikt/', {'month':'2026-10', 'area':self.area.pk})
        self.assertNotContains(response, 'Hvor ble pengene av?')

    def test_historical_and_future_periods_do_not_give_current_spending_advice(self):
        self.entry('expense', 10000, category=self.food, effective_date=date(2026, 9, 2))
        report = self.report(date(2026, 9, 1))
        self.assertFalse(report['current'])
        self.assertEqual(report['notices'], [])
        self.assertIsNone(self.report(date(2026, 11, 1)))

    def test_dashboard_renders_explanation_and_real_amounts(self):
        self.entry('expense', 12345, category=self.food)
        response = self.client.get('/app/oversikt/', {'month':'2026-10', 'area':self.area.pk})
        self.assertContains(response, 'Hvor ble pengene av?')
        self.assertContains(response, '123,45')
        self.assertContains(response, 'Kjøp som ikke er registrert, kan appen ikke oppdage')
        self.assertContains(response, 'Pengebruk uten månedsramme')

    def test_reader_before_and_editor_after_preparation_see_same_money_and_limits(self):
        user = get_user_model().objects.create_user(username='control-reader')
        reader = Membership.objects.create(user=user, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=reader, role='reader')
        self.entry('income', 100000)
        self.entry('expense', 10000, category=self.food)
        limit = self.limit(40000)
        limit.month = date(2026, 9, 1)
        limit.save()
        saving = Asset.objects.create(household=self.house, created_by=self.user,
            kind='savings', name='Carried saving', opening_date=date(2026, 9, 1))
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=saving, month=date(2026, 9, 1), amount_ore=5000)
        BillTemplate.objects.create(household=self.house, created_by=self.user,
            name='Not yet materialized', category=self.food, amount_ore=10000, first_due=date(2026, 10, 28))
        self.client.force_login(user)
        before = self.client.get('/app/oversikt/', {'month':'2026-10', 'area':self.area.pk})
        self.assertEqual(before.status_code, 200)
        self.assertEqual(BillOccurrence.objects.count(), 0)
        self.assertEqual(MonthPlan.objects.count(), 2)
        self.assertEqual(before.context['money_control']['rows'][0]['pending'], 10000)
        self.assertEqual(before.context['categories'][0]['limit'], 40000)
        self.assertEqual(before.context['trend_budget'], 40000)
        self.assertEqual(before.context['totals']['planned_savings'], 5000)
        self.client.force_login(self.user)
        after = self.client.get('/app/oversikt/', {'month':'2026-10', 'area':self.area.pk})
        self.assertEqual(after.status_code, 200)
        self.assertEqual(BillOccurrence.objects.count(), 1)
        self.assertEqual(before.context['money_control'], after.context['money_control'])
        self.assertEqual(before.context['totals'], after.context['totals'])

    def test_future_dated_actuals_do_not_make_current_advice_richer_or_poorer(self):
        self.entry('income', 100000)
        self.entry('income', 700000, effective_date=date(2026, 10, 29))
        self.entry('expense', 50000, category=self.food, effective_date=date(2026, 10, 28))
        self.entry('income', 90000, received=False, effective_date=date(2026, 10, 30))
        self.limit(10000)
        report = self.report()
        self.assertEqual(report['ordinary_gross'], 0)
        self.assertEqual(report['cash_in'], 100000)
        self.assertEqual(report['plan_remainder'], 90000)
        totals = services.calculate(self.house, self.month)
        self.assertEqual(totals['expected'], 90000)
        self.assertEqual(totals['available'], 100000)

    def test_pages_exclude_future_actuals_but_keep_them_in_records(self):
        self.entry('expense', 10000, category=self.food)
        future = self.entry('expense', 50000, category=self.food, effective_date=date(2026, 10, 28))
        self.entry('refund', 20000, original=future, effective_date=date(2026, 10, 29))
        saving = Asset.objects.create(household=self.house, created_by=self.user,
            kind='savings', name='Saving', opening_date=self.month)
        self.entry('deposit', 30000, asset=saving, effective_date=date(2026, 10, 30))
        args = {'month': '2026-10', 'area': self.area.pk}
        overview = self.client.get('/app/oversikt/', args)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.context['categories'][0]['spent'], 10000)
        self.assertEqual(overview.context['money_control']['ordinary_net'], 10000)
        self.assertEqual(overview.context['totals']['gross_deposits'], 0)
        annual = self.client.get('/app/arsoversikt/', {**args, 'view': 'matrix'})
        self.assertEqual(annual.status_code, 200)
        self.assertEqual(annual.context['year_categories'][0]['actual'], 10000)
        records = self.client.get('/app/poster/', args)
        self.assertEqual(records.status_code, 200)
        self.assertIn(future.pk, [entry.pk for entry in records.context['entries']])
