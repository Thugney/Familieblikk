from budget.area_requests import financial_url
from budget.tests.financial_support import enter_fixture_area
"""Persisted module wiring: URL defaults never replace normal validation."""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from budget import services
from budget.models import Asset, BillOccurrence, BillTemplate, CalendarNotification, Category, Entry, Membership, MonthPlan
from budget.tests.test_domain import setup_family


class PlansModulesTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('modules-owner@example.test')
        self.other, self.foreign, self.foreign_category = setup_family('modules-other@example.test')
        enter_fixture_area(self, self.user)
        self.month = timezone.localdate().replace(day=1)
        self.key = self.month.strftime('%Y-%m')
        self.client.force_login(self.user)

    def asset(self, kind='debt', foreign=False):
        from budget.financial_areas import area_scope
        owner = self.other if foreign else self.user
        with area_scope(Membership.objects.get(user=owner), owner.test_area.pk):
            return Asset.objects.create(household=self.foreign if foreign else self.house,
            created_by=self.other if foreign else self.user, kind=kind, name='Modul '+kind,
            opening_date=self.month, opening_ore=100000, target_ore=120000,
            annual_rate=Decimal('6'), minimum_ore=10000)

    def asset_data(self, kind='debt', **extra):
        return dict(kind=kind, name='Lagret '+kind, opening_date=self.month.isoformat(), opening='1000',
                    target='1200', plan='100', plan_month=self.month.isoformat(),
                    annual_rate='6', version=0, plan_version=0, **extra)

    def entry_data(self, asset, kind='debt', **extra):
        return dict(kind=kind, description='Lagret modulbetaling', effective_date=self.month.isoformat(),
                    amount='20', asset=str(asset.pk), fee_ore=0, idempotency_key=str(uuid.uuid4()), version=0, **extra)

    def test_navigation_respects_modules_and_selected_month(self):
        self.area.modules = dict(debt=True, fund=True, remittance=True, annual_navigation=True)
        self.area.save()
        response = self.client.get('/app/mer/', {'month': '2026-09'})
        for page in ('regninger', 'gjeld', 'arsutgifter', 'utland', 'familie', 'tilpass', 'varsler'):
            self.assertContains(response, f'/app/{page}/?month=2026-09')
        self.assertContains(response, '/app/arsoversikt/?month=2026-09&amp;view=matrix')
        self.assertContains(response, 'Planer &amp; moduler')
        self.assertContains(response, 'id="notification-bell"')
        self.area.modules = dict(debt=False, fund=False, remittance=False, annual_navigation=False)
        self.area.save()
        response = self.client.get('/app/mer/', {'month': self.key})
        for page in ('gjeld', 'arsutgifter', 'utland', 'arsoversikt'):
            self.assertNotContains(response, f'href="/app/{page}/')
        # Hiding navigation preserves existing history and direct access.
        debt = self.asset()
        self.assertEqual(self.client.get('/app/gjeld/', {'month': self.key}).status_code, 200)
        self.assertTrue(Asset.objects.filter(pk=debt.pk).exists())

    def test_badges_count_only_own_overdue_bills_and_unread(self):
        from budget.financial_areas import area_scope
        for user, house, category in ((self.user, self.house, self.category), (self.other, self.foreign, self.foreign_category)):
            with area_scope(Membership.objects.get(user=user), user.test_area.pk):
                template = BillTemplate.objects.create(household=house, created_by=user, name='Forfalt',
                    amount_ore=100, first_due=date(2026, 1, 1), monthly=False, category=category)
                services.materialize_template(template, self.month)
                CalendarNotification.objects.create(household=house, recipient=user, original_date=self.month,
                    kind='created', detail='Syntetisk', action_key=uuid.uuid4())
        response = self.client.get('/app/mer/', {'month': self.key})
        self.assertContains(response, 'aria-label="1 forfalte"')
        self.assertContains(response, 'aria-label="1 uleste"')

    def test_create_and_edit_asset_return_to_actual_module_and_month(self):
        for kind, page in (('debt', 'gjeld'), ('fund', 'arsutgifter'), ('recipient', 'utland'), ('savings', 'sparing')):
            url = f'/ny/asset/?month={self.key}&asset_kind={kind}'
            response = self.client.get(url)
            self.assertEqual(response.context['form']['kind'].value(), kind)
            self.assertEqual(response.context['form']['plan_month'].value(), self.month)
            response = self.client.post(url, self.asset_data(kind))
            self.assertEqual(response.status_code, 302, (kind, response.context['form'].errors if response.context else ''))
            self.assertRedirects(response, financial_url(f'/app/{page}/?month={self.key}', self.area.pk), fetch_redirect_response=False)
            asset = Asset.objects.get(household=self.house, name='Lagret '+kind)
            response = self.client.get(f'/endre/asset/{asset.pk}/?month={self.key}')
            self.assertEqual(response.context['page'], page)
            self.assertContains(response, f'href="/app/{page}/?month={self.key}&amp;area={self.area.pk}"')
            data = self.asset_data(kind)
            data.update(name='Redigert '+kind, country='Bekreftet land', version=asset.version,
                        displayed_plan_month=self.month.isoformat(),
                        plan_version=response.context['form']['plan_version'].value())
            response = self.client.post(f'/endre/asset/{asset.pk}/?month={self.key}', data)
            self.assertRedirects(response, financial_url(f'/app/{page}/?month={self.key}', self.area.pk), fetch_redirect_response=False)
            asset.refresh_from_db()
            self.assertEqual(asset.name, 'Redigert '+kind)
            self.assertEqual(asset.country, 'Bekreftet land')

    def test_stale_asset_plan_is_still_rejected_without_overwriting(self):
        asset = self.asset('fund')
        plan = MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=asset, month=self.month, amount_ore=10000, version=2)
        data = self.asset_data('fund')
        data.update(version=asset.version, displayed_plan_month=self.month.isoformat(), plan_version=1)
        response = self.client.post(f'/endre/asset/{asset.pk}/?month={self.key}', data)
        self.assertEqual(response.status_code, 409)
        plan.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(plan.amount_ore, 10000)
        self.assertEqual(asset.name, 'Modul fund')

    def test_entry_defaults_and_submission_remain_independent(self):
        asset = self.asset()
        url = f'/ny/entry/?month={self.key}&entry_kind=debt&asset={asset.pk}&return_to=gjeld'
        form = self.client.get(url).context['form']
        self.assertEqual(form['kind'].value(), 'debt')
        self.assertEqual(str(form['asset'].value()), str(asset.pk))
        self.assertEqual(form['effective_date'].value(), self.month)
        self.assertRedirects(self.client.post(url, self.entry_data(asset)), financial_url(f'/app/gjeld/?month={self.key}', self.area.pk), fetch_redirect_response=False)
        self.assertEqual(Entry.objects.get(household=self.house).asset, asset)
        # The hint must not turn an invalid expense into a debt payment.
        response = self.client.post(url, self.entry_data(asset, kind='expense'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context['form']['kind'].value(), 'expense')
        self.assertEqual(Entry.objects.filter(household=self.house).count(), 1)

    def test_foreign_hints_posts_and_member_setup_are_rejected(self):
        foreign = self.asset(foreign=True)
        for value in (str(foreign.pk), 'bad-uuid'):
            self.assertEqual(self.client.get('/ny/entry/', {'asset': value}).status_code, 404)
        own = self.asset()
        response = self.client.post(f'/ny/entry/?month={self.key}&entry_kind=debt&asset={own.pk}', self.entry_data(foreign))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Entry.objects.filter(household=self.house).exists())
        member = get_user_model().objects.create_user(username='modules-member@example.test')
        from budget.financial_models import FinancialAreaGrant
        membership = Membership.objects.create(user=member, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=membership, role='reader')
        self.client.force_login(member)
        self.assertEqual(self.client.get('/ny/asset/?asset_kind=debt').status_code, 403)
        self.assertEqual(self.client.get(f'/endre/asset/{own.pk}/').status_code, 403)
        self.assertEqual(self.client.get('/app/arsoversikt/', {'month': self.key, 'view': 'matrix'}).status_code, 200)

    def test_return_target_cannot_be_an_external_url(self):
        debt = self.asset()
        response = self.client.post(f'/ny/entry/?month={self.key}&return_to=https://evil.example', self.entry_data(debt))
        self.assertRedirects(response, financial_url(f'/app/poster/?month={self.key}', self.area.pk), fetch_redirect_response=False)

    def test_fund_obligation_defaults_and_payment_remain_persisted(self):
        fund = self.asset('fund')
        response = self.client.get('/ny/bill/', dict(month=self.key, accounting_class='fund', asset=fund.pk, once=1, return_to='arsutgifter'))
        self.assertEqual(response.context['form']['accounting_class'].value(), 'fund')
        self.assertFalse(response.context['form']['monthly'].value())
        url = f'/ny/bill/?month={self.key}&return_to=arsutgifter'
        response = self.client.post(url, dict(name='Årlig faktura', first_due=self.month.isoformat(),
            accounting_class='fund', asset=fund.pk, amount='25', version=0))
        self.assertRedirects(response, financial_url(f'/app/arsutgifter/?month={self.key}', self.area.pk), fetch_redirect_response=False)
        self.client.get('/app/regninger/', {'month': self.key})
        bill = BillOccurrence.objects.get(household=self.house, name='Årlig faktura')
        response = self.client.post(f'/betal/{bill.pk}/?month={self.key}', dict(date=self.month.isoformat(), key=uuid.uuid4(), version=bill.version))
        self.assertRedirects(response, financial_url(f'/app/regninger/?month={self.key}', self.area.pk), fetch_redirect_response=False)
        self.assertEqual(Entry.objects.get(occurrence=bill).kind, 'fund')

    def test_debt_strategy_extra_and_selected_month_survive_save(self):
        self.asset()
        response = self.client.get('/app/gjeld/', dict(month=self.key, strategy='snowball', extra='125,50'))
        form = response.context['debt_plan_form']
        self.assertEqual(form['extra'].value(), Decimal('125.50'))
        self.assertContains(response, 'value="snowball" selected')
        self.assertContains(response, f'name="month" value="{self.key}"')
        response = self.client.post('/gjeldsplan/', dict(month=self.month.isoformat(), strategy='snowball', extra='125,50', confirm='on'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'month={self.key}&strategy=snowball&extra=125.50', response.url)
        self.assertTrue(MonthPlan.objects.filter(household=self.house, month=self.month, asset__kind='debt').exists())

    def test_matrix_is_read_only_and_uses_engine_classes_refunds_and_family(self):
        debt = self.asset()
        rows = []
        for kind, amount in (('expense', 10000), ('remittance', 2000), ('debt', 3000), ('income', 50000)):
            rows.append(Entry.objects.create(household=self.house, created_by=self.user, kind=kind,
                description='Årspost', amount_ore=amount, category=self.category,
                asset=debt if kind == 'debt' else None, effective_date=self.month))
        Entry.objects.create(household=self.house, created_by=self.user, kind='refund', description='Retur',
            amount_ore=1000, original=rows[0], effective_date=self.month)
        Entry.objects.create(household=self.house, created_by=self.user, kind='refund', description='Gjeldsrefusjon',
            amount_ore=500, original=rows[2], effective_date=self.month)
        from budget.financial_areas import area_scope
        with area_scope(Membership.objects.get(user=self.other), self.other.test_area.pk):
            Entry.objects.create(household=self.foreign, created_by=self.other, kind='expense', description='Fremmed',
                amount_ore=999999, category=self.foreign_category, effective_date=self.month)
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category, month=self.month, amount_ore=20000)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Ikke materialiser',
            amount_ore=100, category=self.category, first_due=self.month, monthly=True)
        counts = (MonthPlan.objects.count(), BillOccurrence.objects.count())
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/app/arsoversikt/', {'month': self.key, 'view': 'matrix'})
        writes = [q['sql'] for q in captured if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))]
        self.assertEqual(writes, [])
        self.assertEqual(counts, (MonthPlan.objects.count(), BillOccurrence.objects.count()))
        self.assertEqual(response.context['year_categories'][0]['actual'], 11000)
        self.assertEqual(response.context['year_categories'][0]['budget'], 20000 * (13-self.month.month))
        selected = response.context['year_rows'][self.month.month-1]
        self.assertEqual(selected['totals'], services.calculate(self.house, self.month))
        self.assertEqual(selected['totals']['cash'], 36500)
        self.assertNotContains(response, 'Fremmed')
        self.assertContains(response, 'Vis årsgraf')
        self.assertFalse(BillOccurrence.objects.filter(template=template).exists())
        self.assertTemplateUsed(self.client.get('/app/arsoversikt/', {'month': self.key}), 'budget/spending.html')

    def test_csrf_is_still_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(f'/ny/asset/?month={self.key}&asset_kind=debt', self.asset_data()).status_code, 403)
    def test_matrix_effective_projection_ytd_and_query_growth(self):
        today = date(2026, 3, 15)
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
            month=date(2025, 12, 1), amount_ore=100)
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
            month=date(2026, 1, 1), amount_ore=10, derived=True)
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
            month=date(2026, 2, 1), amount_ore=250)
        fund = self.asset('fund')
        fund.opening_date = date(2026, 1, 1); fund.save()
        MonthPlan.objects.create(household=self.house, created_by=self.user, asset=fund,
            month=date(2026, 1, 1), amount_ore=10000, annual_total_ore=120001)
        for day, amount in ((date(2026, 3, 10), 500), (date(2026, 3, 20), 700)):
            Entry.objects.create(household=self.house, created_by=self.user, category=self.category,
                kind='expense', amount_ore=amount, effective_date=day, description='Datert')
        def read_matrix():
            with patch('budget.views.timezone.localdate', return_value=today), CaptureQueriesContext(connection) as queries:
                response = self.client.get('/app/arsoversikt/?month=2026-03&view=matrix')
            self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))])
            return response, len(queries)
        response, initial_queries = read_matrix()
        category = response.context['year_categories'][0]
        self.assertEqual(category['periods'][0]['budget'], 10)
        self.assertEqual(category['periods'][1]['budget'], 250)
        self.assertEqual(category['ytd'], 500)
        self.assertEqual(category['actual'], 500)  # Future-dated actuals wait until their effective date.
        self.assertContains(response, 'Foreløpig disponering')
        self.assertContains(response, 'kjente gjentakende regninger og beregnet fondspåfyll, også før månedspostene er opprettet')
        december = response.context['year_rows'][11]
        self.assertFalse(december['has_data'])
        self.assertTrue(december['has_values'])
        self.assertEqual(december['totals']['funds'], 10001)
        self.assertLess(december['totals']['available'], 0)
        # Same engine totals once the existing preparation service materializes them.
        with patch('budget.services.timezone.localdate', return_value=today):
            services.prepare_month(self.house, date(2026, 12, 1))
            self.assertEqual(december['totals'], services.calculate(self.house, date(2026, 12, 1)))
            self.assertEqual(category['periods'][0]['budget'], MonthPlan.objects.get(household=self.house, category=self.category, month=date(2026, 1, 1)).amount_ore)
        Category.objects.bulk_create([Category(household=self.house, created_by=self.user, name=f'Ekstra {i}') for i in range(30)])
        _, many_queries = read_matrix()
        self.assertLessEqual(many_queries, initial_queries + 2)

    def test_header_switch_preserves_safe_module_hints_and_debt_context(self):
        debt = self.asset()
        query = f'month={self.key}&return_to=gjeld&entry_kind=debt&asset={debt.pk}&strategy=snowball&extra=25,50'
        response = self.client.get('/ny/entry/?'+query)
        for key, value in (('return_to', 'gjeld'), ('entry_kind', 'debt'), ('asset', str(debt.pk)), ('strategy', 'snowball'), ('extra', '25.50')):
            self.assertContains(response, f'type="hidden" name="{key}" value="{value}"')
        response = self.client.post('/ny/entry/?'+query, self.entry_data(debt))
        self.assertEqual(response.url, f'/app/gjeld/?month={self.key}&strategy=snowball&extra=25.50&area={self.area.pk}')
        response = self.client.get('/app/gjeld/?'+query)
        self.assertContains(response, f'/endre/asset/{debt.pk}/?month={self.key}&amp;strategy=snowball&amp;extra=25.50')
        bad = self.client.get('/ny/entry/?return_to=https://evil.example&asset=bad&entry_kind=bad')
        self.assertEqual(bad.status_code, 404)

    def test_overview_entry_returns_and_cancel_stay_in_overview(self):
        response = self.client.get(f'/ny/entry/?month={self.key}&return_to=oversikt')
        self.assertContains(response, f'href="/app/oversikt/?month={self.key}&amp;area={self.area.pk}"')
        debt = self.asset()
        response = self.client.post(f'/ny/entry/?month={self.key}&return_to=oversikt', self.entry_data(debt))
        self.assertEqual(response.url, f'/app/oversikt/?month={self.key}&area={self.area.pk}')

    def test_private_import_link_requires_actual_authenticated_owner_guard(self):
        response = self.client.get('/app/mer/')
        self.assertNotContains(response, 'href="/app/import/')
        self.assertContains(response, 'href="/app/mer/')
        binding = {'owner_email': self.user.email, 'household_id': str(self.house.pk)}
        session = self.client.session
        session['verified_email'] = self.user.email
        session.save()
        with patch('budget.importing.load_private_source', return_value=({}, binding)):
            self.assertContains(self.client.get('/app/mer/'), 'href="/app/import/')
            member = Membership.objects.get(user=self.user)
            member.role = 'member'; member.save()
            self.assertNotContains(self.client.get('/app/mer/'), 'href="/app/import/')

    def test_notification_read_keeps_selected_period(self):
        notice = CalendarNotification.objects.create(household=self.house, recipient=self.user,
            original_date=self.month, kind='created', detail='Test', action_key=uuid.uuid4())
        response = self.client.get('/app/varsler/?month=2026-09')
        self.assertContains(response, f'/push/read/{notice.pk}/?month=2026-09')
        response = self.client.post(f'/push/read/{notice.pk}/?month=2026-09')
        self.assertEqual(response.url, '/app/varsler/?month=2026-09')
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
    def test_matrix_projects_implicit_fund_and_stops_archived_future_carry(self):
        today = date(2026, 3, 15)
        self.category.archived = True; self.category.save()
        MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category,
            month=date(2026, 1, 1), amount_ore=500)
        fund = self.asset('fund')
        fund.opening_date = date(2026, 1, 1); fund.target_ore = 120001; fund.save()
        debt = self.asset('debt'); debt.archived = True; debt.save()
        MonthPlan.objects.create(household=self.house, created_by=self.user, asset=debt,
            month=date(2026, 1, 1), amount_ore=1000)
        with patch('budget.views.timezone.localdate', return_value=today), CaptureQueriesContext(connection) as queries:
            response = self.client.get('/app/arsoversikt/?month=2026-03&view=matrix')
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))])
        december = response.context['year_rows'][11]
        self.assertEqual(response.context['year_rows'][0]['totals']['funds'], 10000)
        self.assertEqual(december['budget'], 0)
        self.assertEqual(december['totals']['debt'], 0)
        self.assertEqual(december['totals']['funds'], 10001)
        self.assertFalse(MonthPlan.objects.filter(asset=fund).exists())
        with patch('budget.services.timezone.localdate', return_value=today):
            services.prepare_month(self.house, date(2026, 12, 1))
            self.assertEqual(december['totals'], services.calculate(self.house, date(2026, 12, 1)))
        self.assertFalse(MonthPlan.objects.filter(category=self.category, month=date(2026, 12, 1)).exists())

    def test_implicit_fund_opening_in_december_includes_remainder(self):
        fund = self.asset('fund')
        fund.opening_date = date(2025, 12, 1); fund.target_ore = 120001; fund.save()
        response = self.client.get('/app/arsoversikt/?month=2025-12&view=matrix')
        december = response.context['year_rows'][11]
        self.assertEqual(december['totals']['funds'], 10001)
        self.assertEqual(response.context['year_rows'][10]['totals']['funds'], 0)
        self.assertFalse(MonthPlan.objects.filter(asset=fund).exists())
