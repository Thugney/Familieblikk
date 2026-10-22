from budget.tests.financial_support import enter_fixture_area
from datetime import date
from django.test import TestCase
from budget.models import Category, Entry, MonthPlan
from budget.tests.test_domain import setup_family


class BudgetUsabilityTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('ux-owner@example.test')
        self.other, self.foreign, self.foreign_category = setup_family('ux-foreign@example.test')
        enter_fixture_area(self, self.user)
        self.month = date(2026, 9, 1)
        self.client.force_login(self.user)

    def entry(self, description='Handlekurv', amount=10000, category=None, **kwargs):
        return Entry.objects.create(household=self.house, created_by=self.user, kind='expense', category=category or self.category, amount_ore=amount, description=description, effective_date=self.month, **kwargs)

    def get(self, screen='oversikt', **query):
        return self.client.get(f'/app/{screen}/', {'month': '2026-09', **query})

    def test_missing_zero_and_positive_limits_show_distinct_honest_graphs(self):
        self.category.color = '#8044ab'
        self.category.save()
        self.entry(amount=15000)
        response = self.get('kategorier')
        self.assertContains(response, 'style="--category:#8044ab"')
        self.assertContains(response, 'class="has-spending" style="width:100.0000%"')
        self.assertContains(response, 'Månedsgrense ikke valgt')
        self.assertNotContains(response, 'aria-label="Forbruk Mat"')
        plan = MonthPlan.objects.create(household=self.house, created_by=self.user, category=self.category, month=self.month, amount_ore=0)
        response = self.get('kategorier')
        self.assertEqual(response.context['categories'][0]['limit'], 0)
        self.assertContains(response, 'class="spending-share"')
        plan.amount_ore = 10000
        plan.save()
        response = self.get('kategorier')
        self.assertContains(response, 'max="10000" value="10000"')
        self.assertEqual(response.context['categories'][0]['over'], 5000)
        self.assertNotContains(response, 'class="spending-share"')

    def test_refunds_and_category_search_do_not_change_share_denominator_or_totals(self):
        second = Category.objects.create(household=self.house, created_by=self.user, name='Reise')
        self.entry(amount=10000)
        original = self.entry(amount=30000, category=second)
        Entry.objects.create(household=self.house, created_by=self.user, kind='refund', original=original, amount_ore=5000, description='Retur', effective_date=self.month)
        baseline = self.get('kategorier')
        searched = self.get('kategorier', category_q='Mat')
        self.assertEqual(searched.context['totals'], baseline.context['totals'])
        self.assertEqual(len(searched.context['categories']), 1)
        self.assertEqual(searched.context['categories'][0]['share_width'], '28.5714')
        # A refund this month can exceed this month's spending (original is historical).
        original.effective_date = date(2026, 8, 1)
        original.save()
        response = self.get('kategorier', category_q='Reise')
        self.assertEqual(response.context['categories'][0]['spent'], -5000)
        self.assertContains(response, 'Netto refusjon')
        self.assertContains(response, 'width:0.0000%')

    def test_overview_and_budget_share_complete_filtered_spending_workspace(self):
        for i in range(8):
            category = Category.objects.create(household=self.house, created_by=self.user, name=f'Kategori {i}')
            self.entry(category=category, amount=(i + 1) * 100)
        response = self.get()
        self.assertContains(response, 'data-spending-workspace')
        self.assertContains(response, 'id="sp-search"')
        self.assertContains(response, 'id="sp-tab-planning"')
        self.assertNotContains(response, 'Vis alle treff')
        api = self.client.get('/app/forbruk/data/', {'month': '2026-09'}).json()
        self.assertEqual(len(api['categories']), 8)
        self.assertEqual(api['total_ore'], sum(range(1, 9)) * 100)
        filtered = self.client.get('/app/forbruk/data/', {'month': '2026-09', 'q': 'Kategori 7'}).json()
        self.assertEqual(len(filtered['categories']), 1)
        self.assertEqual(filtered['period_total_ore'], api['period_total_ore'])
        for screen, tab in [('budsjett', 'spending'), ('arsoversikt', 'annual')]:
            response = self.get(screen)
            self.assertTemplateUsed(response, 'budget/spending.html')
            self.assertEqual(response.context['spending_boot']['initial_tab'], tab)
            self.assertNotContains(response, 'Kategorier gjennom året')

    def test_post_filters_persist_and_do_not_change_household_totals(self):
        wanted = self.entry(description='Matbutikk', amount=400)
        self.entry(description='Annet', amount=600)
        Entry.objects.create(household=self.house, created_by=self.user, kind='income', amount_ore=2000, received=False, description='Venter', effective_date=self.month)
        baseline = self.get('poster')
        response = self.get('poster', q='Matbutikk', kind='expense', category=str(self.category.pk), creator=str(self.user.pk), date_from='2026-09-01', date_to='2026-09-10')
        self.assertEqual(list(response.context['entries']), [wanted])
        self.assertEqual(response.context['totals'], baseline.context['totals'])
        self.assertContains(response, 'value="Matbutikk"')
        self.assertContains(response, 'value="2026-09-10"')
        self.assertContains(response, 'Nullstill filtre')
        response = self.get('poster', status='expected')
        self.assertEqual([row.description for row in response.context['entries']], ['Venter'])
        self.assertEqual(response.context['totals'], baseline.context['totals'])

    def test_foreign_filters_invalid_ranges_and_other_month_never_leak(self):
        self.entry()
        from budget.financial_areas import area_scope
        from budget.models import Membership
        with area_scope(Membership.objects.get(user=self.other), self.other.test_area.pk):
            Entry.objects.create(household=self.foreign, created_by=self.other, kind='expense', category=self.foreign_category, amount_ore=500, description='Privat fremmed post', effective_date=self.month)
        october = self.entry(description='Oktober')
        Entry.objects.filter(pk=october.pk).update(effective_date=date(2026, 10, 1))
        for query in [dict(category=str(self.foreign_category.pk)), dict(creator=str(self.other.pk)), dict(date_from='2026-09-20', date_to='2026-09-01'), dict(kind='unknown')]:
            with self.subTest(query=query):
                response = self.get('poster', **query)
                self.assertFalse(list(response.context['entries']))
                self.assertFalse(response.context['filter_form'].is_valid())
                self.assertNotContains(response, 'Privat fremmed post')
                self.assertNotContains(response, self.other.email)
        response = self.get('poster', date_from='2026-08-01', date_to='2026-10-31')
        self.assertEqual(len(response.context['entries']), 1)
        self.assertNotContains(response, 'Oktober')

    def test_pagination_has_stable_sequence_and_preserves_filter_month(self):
        rows = [self.entry(description=f'Sidepost {i}') for i in range(15)]
        first = self.get('poster', q='Sidepost')
        second = self.get('poster', q='Sidepost', page='2')
        ids1 = [row.pk for row in first.context['entries']]
        ids2 = [row.pk for row in second.context['entries']]
        self.assertEqual(len(ids1), 10)
        self.assertEqual(len(ids2), 5)
        self.assertFalse(set(ids1) & set(ids2))
        self.assertEqual(ids1 + ids2, [row.pk for row in reversed(rows)])
        self.assertContains(first, 'month=2026-09')
        self.assertContains(first, 'q=Sidepost')
        self.assertContains(first, 'page=2')
        self.assertEqual(self.get('poster', page='invalid').status_code, 200)

    def test_date_creator_category_and_refund_filters_select_matching_rows(self):
        from django.contrib.auth import get_user_model
        from budget.models import Membership
        from django.utils import timezone
        contributor = get_user_model().objects.create_user(username='ux-member', email='ux-member@example.test')
        Membership.objects.create(user=contributor, household=self.house, role='member', verified_at=timezone.now())
        first = self.entry(description='Tidlig')
        later = self.entry(description='Senere')
        Entry.objects.filter(pk=later.pk).update(effective_date=date(2026, 9, 20), created_by=contributor)
        refund = Entry.objects.create(household=self.house, created_by=contributor, kind='refund', original=first, amount_ore=500, description='Refusjon', effective_date=date(2026, 9, 22))
        response = self.get('poster', category=str(self.category.pk), creator=str(contributor.pk), date_from='2026-09-21')
        self.assertEqual(list(response.context['entries']), [refund])
        self.assertContains(response, 'class="advanced-filters" open')
        self.assertNotContains(self.get('poster'), 'class="advanced-filters" open')
        response = self.get('poster', date_to='2026-09-19')
        self.assertEqual(list(response.context['entries']), [first])

    def test_shared_brand_used_by_auth_and_member_subpages(self):
        from budget.models import Membership
        Membership.objects.filter(user=self.user).update(identity_method='preregistered_admin')
        for path in ['/passord/', '/app/oversikt/', '/registrer/medlem/', f'/endre/category/{self.category.pk}/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'budget/brand.html')
            self.assertContains(response, 'width="26" height="26" alt="">Familieblikk')
        response = self.get()
        self.assertContains(response, 'class="mobile-brand"')

    def test_refund_text_search_matches_original_category_only_for_refunds(self):
        original = self.entry(description='Kjøp')
        refund = Entry.objects.create(household=self.house, created_by=self.user, kind='refund', original=original, amount_ore=100, description='Retur uten kategorinavn', effective_date=self.month)
        response = self.get('poster', q='Mat', kind='refund')
        self.assertEqual(list(response.context['entries']), [refund])
        self.assertEqual(list(self.get('poster', category=str(self.category.pk), kind='refund').context['entries']), [refund])

    def test_category_expansion_persists_and_zero_denominator_is_explicit(self):
        response = self.get('kategorier', category_all='1', category_q='Mat')
        self.assertContains(response, 'name="category_all" value="1"')
        self.assertContains(response, 'id="category-search-status" class="chart-note" role="status" aria-live="polite"')
        self.assertContains(response, 'id="category-results" aria-busy="false"')
        self.assertLess(response.content.index(b'</form>', response.content.index(b'id="category-filters"')), response.content.index(b'id="category-results"'))
        self.assertContains(response, 'Ingen registrerte utgifter denne måneden')
        self.assertNotContains(response, '0,0 % av positivt netto kategoriforbruk')
        original = self.entry()
        Entry.objects.filter(pk=original.pk).update(effective_date=date(2026, 8, 1))
        Entry.objects.create(household=self.house, created_by=self.user, kind='refund', original=original, amount_ore=100, description='Retur', effective_date=self.month)
        response = self.get('kategorier')
        self.assertContains(response, 'Netto refusjon')
        self.assertContains(response, 'width:0.0000%')
        self.assertNotContains(response, 'positivt netto kategoriforbruk')

    def test_empty_month_and_filtered_empty_have_different_actions(self):
        response = self.get('poster')
        self.assertContains(response, 'Ingen poster denne måneden.')
        self.assertContains(response, f'href="/ny/entry/?month=2026-09&amp;area={self.area.pk}"')
        self.entry()
        response = self.get('poster', q='finnes ikke')
        self.assertContains(response, 'Ingen poster matcher valget denne måneden.')
        self.assertContains(response, f'href="/app/poster/?month=2026-09&amp;area={self.area.pk}">Nullstill filtrene')
        self.assertNotContains(response, 'Ingen poster denne måneden.')

    def test_utland_form_only_offers_relevant_types_without_income_status(self):
        response = self.get('utland')
        self.assertEqual(response.status_code, 200)
        form = response.context['filter_form']
        self.assertEqual({value for value, label in form.fields['kind'].choices}, {'', 'remittance', 'refund'})
        self.assertNotIn('status', form.fields)
        self.assertNotContains(response, 'Inntektsstatus')
        self.assertEqual(self.get('utland', kind='refund', status='expected').status_code, 200)
        response = self.get('utland', kind='income')
        self.assertFalse(response.context['filter_form'].is_valid())
        self.assertFalse(list(response.context['entries']))

    def test_archived_category_modes_keep_historical_spending_and_expansion_counts(self):
        spent = Category.objects.create(household=self.house, created_by=self.user, name='Arkivert med forbruk', archived=True)
        unused = Category.objects.create(household=self.house, created_by=self.user, name='Arkivert uten forbruk', archived=True)
        self.entry(category=spent, amount=100)
        for index in range(7):
            Category.objects.create(household=self.house, created_by=self.user, name=f'Aktiv {index}')
        def identities(response):
            return {item['row'].pk for item in response.context['categories']}
        active = self.get('kategorier', category_status='active', category_all='1')
        self.assertIn(spent.pk, identities(active))
        self.assertNotIn(unused.pk, identities(active))
        self.assertIn(self.category.pk, identities(active))
        archived = self.get('kategorier', category_status='archived', category_all='1')
        self.assertEqual(identities(archived), {spent.pk, unused.pk})
        all_rows = self.get('kategorier', category_status='all', category_all='1')
        self.assertEqual(len(identities(all_rows)), 10)
        compact = self.get('kategorier', category_status='all')
        self.assertEqual(len(compact.context['categories']), 10)
        self.assertEqual(compact.context['category_matched_count'], 10)
        self.assertIn(spent.pk, identities(compact))
        self.assertEqual(compact.context['totals'], all_rows.context['totals'])

    def test_public_info_error_and_offline_share_brand_without_private_context(self):
        from django.test import Client, override_settings
        guest = Client()
        with override_settings(DEBUG=False):
            for path, status in [('/info/personvern/', 200), ('/info/hjelp/', 200), ('/does-not-exist/', 404), ('/offline/', 200)]:
                with self.subTest(path=path):
                    response = guest.get(path)
                    self.assertEqual(response.status_code, status)
                    self.assertTemplateUsed(response, 'budget/brand.html')
                    self.assertContains(response, 'width="26" height="26" alt="">Familieblikk', status_code=status)
                    self.assertNotContains(response, self.user.email, status_code=status)
        offline_guest = guest.get('/offline/')
        offline_signed_in = self.client.get('/offline/')
        self.assertEqual(offline_guest.content, offline_signed_in.content)
        self.assertContains(offline_guest, '/static/budget/app.css')
        self.assertContains(offline_guest, '/static/budget/icon.svg')
        self.assertNotIn('sessionid', offline_guest.cookies)
        self.assertNotIn('Cookie', offline_guest.get('Vary', ''))
        self.assertNotContains(offline_guest, self.house.name)
        self.assertNotContains(offline_guest, 'csrfmiddlewaretoken')
