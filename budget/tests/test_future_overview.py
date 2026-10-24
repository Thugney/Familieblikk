from datetime import date
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from budget import services, spending_services
from budget.financial_areas import area_scope, create_area
from budget.models import Asset, BillTemplate, Entry, Membership, MonthlyBudgetHeader, MonthPlan
from budget.tests.test_domain import setup_family


class FutureOverviewTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('future-overview@example.test')
        self.area = self.user.test_area
        self.member = Membership.objects.get(user=self.user)
        self.month = date(2026, 11, 1)
        clock = patch('django.utils.timezone.localdate', return_value=date(2026, 10, 24))
        clock.start()
        self.addCleanup(clock.stop)
        self.client = Client()
        self.client.force_login(self.user)

    def income(self, amount, **extra):
        values = dict(household=self.house, created_by=self.user, kind='income',
            amount_ore=amount, effective_date=self.month, received=False)
        values.update(extra)
        return Entry.objects.create(**values)

    def test_expected_entries_are_proposed_once_without_marking_income_received(self):
        with area_scope(self.member, self.area.pk):
            self.income(1400000)
            self.income(600000)
            self.income(999999, effective_date=date(2026, 10, 1))
            self.income(999999, active=False)
            self.income(999999, kind='expense')
            with CaptureQueriesContext(connection) as queries:
                plan = spending_services.planning(self.user, '2026-11')
            self.assertEqual(plan['expected_income_ore'], 2000000)
            self.assertEqual(plan['draft']['expected_income_ore'], 2000000)
            self.assertEqual(plan['income_source'], 'expected_entries')
            self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
            self.assertEqual(services.calculate(self.house, self.month)['income'], 0)
            self.assertFalse(Entry.objects.filter(received=True).exists())
            self.assertFalse(MonthlyBudgetHeader.objects.exists())

    def test_saved_zero_and_explicit_plan_win_over_expected_entries(self):
        with area_scope(self.member, self.area.pk):
            self.income(100000)
            header = MonthlyBudgetHeader.objects.create(household=self.house, created_by=self.user,
                month=self.month, expected_income_ore=0)
            self.assertEqual(spending_services.planning_income(self.house, self.month), (0, 'existing_plan'))
            header.expected_income_ore = 150000
            header.save()
            self.assertEqual(spending_services.planning_income(self.house, self.month), (150000, 'existing_plan'))

    def test_missing_income_stays_unknown_and_other_budget_is_excluded(self):
        other = create_area(self.member, 'Other synthetic budget')
        with area_scope(self.member, other.pk):
            self.income(9900000)
        with area_scope(self.member, self.area.pk):
            self.assertEqual(spending_services.planning_income(self.house, self.month), (None, 'missing'))
        response = self.client.get('/app/oversikt/', {'area': self.area.pk, 'month': '2026-11'})
        self.assertIsNone(response.context['future_overview']['remainder'])
        self.assertContains(response, 'Legg inn forventet inntekt')
        self.assertContains(response, 'Forventet inntekt er ikke registrert')
        self.assertNotContains(response, 'Inntekten kommer fra registrerte poster')

    def test_future_http_is_read_only_and_uses_debt_minimum_even_with_lower_plan(self):
        with area_scope(self.member, self.area.pk):
            self.income(100000)
            asset = Asset.objects.create(household=self.house, created_by=self.user, kind='debt',
                name='Synthetic minimum', opening_date=date(2026, 10, 1), minimum_ore=25000)
            BillTemplate.objects.create(household=self.house, created_by=self.user, name='Future bill',
                first_due=self.month, monthly=True, amount_ore=10000)
        for planned in (None, 0, 10000):
            with self.subTest(planned=planned):
                if planned is not None:
                    with area_scope(self.member, self.area.pk):
                        MonthPlan.objects.update_or_create(household=self.house, asset=asset, month=self.month,
                            defaults={'created_by': self.user, 'amount_ore': planned})
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get('/app/oversikt/', {'area': self.area.pk, 'month': '2026-11'})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
                self.assertEqual(response.context['future_overview']['debt'], 25000)
                self.assertEqual(response.context['future_overview']['remainder'], 65000)

    def test_future_overview_explains_fixed_deductions_and_opens_selected_plan_month(self):
        with area_scope(self.member, self.area.pk):
            self.income(2000000)
            BillTemplate.objects.create(household=self.house, created_by=self.user, name='Synthetic bill',
                first_due=self.month, monthly=False, amount_ore=1200000)
            for kind, amount in [('savings', 300000), ('debt', 200000)]:
                asset = Asset.objects.create(household=self.house, created_by=self.user, kind=kind,
                    name='Synthetic ' + kind, opening_date=date(2026, 10, 1))
                MonthPlan.objects.create(household=self.house, created_by=self.user,
                    asset=asset, month=self.month, amount_ore=amount)
        response = self.client.get('/app/oversikt/', {'area': self.area.pk, 'month': '2026-11'})
        self.assertEqual(response.context['future_overview']['remainder'], 300000)
        self.assertEqual(response.context['future_overview']['fixed'], 1700000)
        self.assertEqual(response.context['totals']['income'], 0)
        self.assertEqual(response.context['totals']['available'], -1700000)
        self.assertContains(response, 'ikke penger du kan bruke nå')
        self.assertContains(response, 'Gjennomgå og rett månedsplanen')
        self.assertEqual(response.context['spending_boot']['initial_tab'], 'planning')
        self.assertEqual(response.context['spending_boot']['plan_month'], '2026-11')
        for page in ('oversikt', 'budsjett'):
            later = self.client.get(f'/app/{page}/', {'area': self.area.pk, 'month': '2026-12'})
            self.assertEqual(later.context['spending_boot']['initial_tab'], 'planning')
            self.assertEqual(later.context['spending_boot']['plan_month'], '2026-12')

    def test_future_sections_include_projected_savings_and_unmaterialized_bills(self):
        with area_scope(self.member, self.area.pk):
            self.income(2000000)
            asset = Asset.objects.create(household=self.house, created_by=self.user,
                kind='savings', name='Carried saving', opening_date=date(2026, 10, 1))
            MonthPlan.objects.create(household=self.house, created_by=self.user,
                asset=asset, month=date(2026, 10, 1), amount_ore=30000)
            BillTemplate.objects.create(household=self.house, created_by=self.user, name='Unmaterialized bill',
                first_due=self.month, monthly=True, amount_ore=10000)
        response = self.client.get('/app/oversikt/', {'area': self.area.pk, 'month': '2026-11'})
        self.assertEqual(response.context['future_overview']['savings'], 30000)
        self.assertContains(response, 'Unmaterialized bill')
        self.assertNotContains(response, 'Ingen poster eller regninger i dette utvalget')
        self.assertNotContains(response, 'allerede satt av')

    def test_current_month_keeps_received_money_and_explicit_planning_link_works(self):
        response = self.client.get('/app/oversikt/', {'area': self.area.pk, 'month': '2026-10'})
        self.assertNotIn('future_overview', response.context)
        self.assertContains(response, 'Igjen å bruke')
        plan = self.client.get('/app/budsjett/', {'area': self.area.pk, 'month': '2026-10', 'tab': 'planning'})
        self.assertEqual(plan.context['spending_boot']['initial_tab'], 'planning')
        self.assertIsNone(plan.context['spending_boot']['plan_month'])

    def test_salary_shortcuts_open_income_in_selected_month_without_posting_receipt(self):
        for page in ('regninger', 'oversikt'):
            response = self.client.get(f'/app/{page}/', {'area': self.area.pk, 'month': '2026-11'})
            self.assertContains(response, 'Legg til lønn / inntekt')
            self.assertContains(response, 'entry_kind=income')
        response = self.client.get('/ny/entry/', {'area': self.area.pk, 'month': '2026-11', 'entry_kind': 'income'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['kind'].value(), 'income')
        self.assertFalse(response.context['form']['received'].value())
        self.assertContains(response, 'i stedet for å legge den inn på nytt')
        self.assertEqual(response.context['month'], self.month)
        with area_scope(self.member, self.area.pk):
            self.assertFalse(Entry.objects.exists())
        current = self.client.get('/ny/entry/', {'area': self.area.pk, 'month': '2026-10', 'entry_kind': 'income'})
        self.assertTrue(current.context['form']['received'].value())

    def test_salary_shortcut_respects_budget_module_access(self):
        self.member.module_access = {'budget': False}
        self.member.save()
        bills = self.client.get('/app/regninger/', {'area': self.area.pk, 'month': '2026-11'})
        self.assertNotContains(bills, 'Legg til lønn / inntekt')
        denied = self.client.get('/ny/entry/', {'area': self.area.pk, 'month': '2026-11', 'entry_kind': 'income'})
        self.assertEqual(denied.status_code, 403)
