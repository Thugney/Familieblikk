from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from budget.models import Household, Membership, Category, Entry, MonthPlan
from budget.financial_areas import create_area, area_scope

@override_settings(ALLOWED_HOSTS=['testserver'])
class OverviewMetricsTests(TestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic metrics')
        self.user = get_user_model().objects.create_user(username='metrics')
        self.member = Membership.objects.create(user=self.user, household=self.house, role='admin')
        self.area = create_area(self.member, 'Metrics')
        self.other = create_area(self.member, 'Other')
        self.client.force_login(self.user)
        with area_scope(self.member, self.area.pk):
            self.category = Category.objects.create(household=self.house, created_by=self.user, name='Food')
            self.expense = Entry.objects.create(household=self.house, created_by=self.user, kind='expense', category=self.category, amount_ore=9000, effective_date=date(2026,10,2))
            Entry.objects.create(household=self.house, created_by=self.user, kind='refund', original=self.expense, amount_ore=1000, effective_date=date(2026,10,3))
        with area_scope(self.member, self.other.pk):
            Entry.objects.create(household=self.house, created_by=self.user, kind='expense', amount_ore=990000, effective_date=date(2026,10,2))
    def overview(self, month='2026-10'):
        with patch('budget.views.timezone.localdate', return_value=date(2026,10,4)):
            return self.client.get('/app/oversikt/', {'month':month,'area':self.area.pk})
    def test_real_daily_cumulative_refunds_and_no_budget(self):
        response=self.overview()
        self.assertEqual(response.status_code,200)
        points=response.context['month_trend']
        self.assertEqual([p['amount'] for p in points[:5]], [0,9000,8000,8000,None])
        self.assertIsNone(response.context['trend_budget'])
        self.assertEqual(response.context['daily_days'],28)
        self.assertContains(response,'Ingen kategorirammer registrert')
        self.assertContains(response,'Netto frigjort sparing')
        self.assertContains(response,'Vis daglige beløp')
        self.assertTrue(all(bar['height'] >= 0 for bar in response.context['weekly_bars']))
        self.assertEqual(response.context['weekly_total'],8000)
    def test_real_budget_pace_and_warning(self):
        with area_scope(self.member,self.area.pk):
            MonthPlan.objects.create(household=self.house,created_by=self.user,category=self.category,month=date(2026,10,1),amount_ore=9000)
        response=self.overview()
        self.assertEqual(response.context['month_trend'][-1]['budget'],9000)
        self.assertContains(response,'Nær rammen')
        self.assertContains(response,'is-warning')
    def test_future_has_no_fabricated_actuals(self):
        response=self.overview('2026-11')
        self.assertTrue(all(p['amount'] is None for p in response.context['month_trend']))
        self.assertEqual(response.context['weekly_bars'],[])
    def test_grouped_accounting_query_bound(self):
        from budget import services
        with area_scope(self.member, self.area.pk):
            # Two live permission checks plus one grouped aggregate, independent of days.
            with self.assertNumQueries(3):
                daily = services.ordinary_by_date(self.house,date(2026,10,1),date(2026,10,31))
            self.assertEqual(sum(daily.values()),8000)
        with patch('budget.services.ordinary_by_date', wraps=services.ordinary_by_date) as grouped:
            self.overview()
            self.assertLessEqual(grouped.call_count,5)

    def test_historical_week_ends_at_month_end_and_comparison_ignores_future(self):
        with area_scope(self.member,self.area.pk):
            for day, amount in [(date(2026,9,2),16000),(date(2026,9,30),3000),(date(2026,10,20),90000)]:
                Entry.objects.create(household=self.house,created_by=self.user,kind='expense',category=self.category,amount_ore=amount,effective_date=day)
        response=self.overview('2026-09')
        self.assertEqual(response.context['weekly_start'],date(2026,9,24))
        self.assertEqual(response.context['weekly_end'],date(2026,9,30))
        self.assertEqual(len(response.context['weekly_bars']),7)
        self.assertEqual(response.context['weekly_total'],3000)
        current=self.overview()
        self.assertEqual(current.context['pace']['delta'],'−50,0')
        self.assertEqual(current.context['month_trend'][3]['amount'],8000)

    def test_zero_limit_positive_and_net_refund_states(self):
        with area_scope(self.member,self.area.pk):
            MonthPlan.objects.create(household=self.house,created_by=self.user,category=self.category,month=date(2026,10,1),amount_ore=0)
        response=self.overview()
        self.assertEqual(response.context['categories'][0]['bar_pct'],100)
        self.assertEqual(response.context['categories'][0]['budget_status'],'over')
        with area_scope(self.member,self.area.pk):
            Entry.objects.filter(kind='refund').update(amount_ore=11000)
        response=self.overview()
        self.assertEqual(response.context['categories'][0]['bar_pct'],0)
        self.assertEqual(response.context['categories'][0]['budget_status'],'normal')
        self.assertEqual(response.context['month_trend'][3]['amount'],-2000)
        self.assertContains(response,'is-refund')
        self.assertContains(response,'− refusjon')
        with area_scope(self.member,self.area.pk):
            Entry.objects.filter(kind='refund').update(amount_ore=9000)
        response=self.overview()
        self.assertEqual(response.context['weekly_total'],0)
        self.assertEqual(response.context['categories'][0]['budget_status'],'normal')
        self.assertContains(response,'bento-bars')

    def test_first_day_marker_and_future_empty_message(self):
        with patch('budget.views.timezone.localdate', return_value=date(2026,10,1)):
            response=self.client.get('/app/oversikt/', {'month':'2026-10','area':self.area.pk})
        self.assertContains(response,'<circle cx="8"')
        self.assertContains(self.overview('2026-11'),'Ingen inntrufne dager i denne måneden')
