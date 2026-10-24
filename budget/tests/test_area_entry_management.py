"""Ordinary browser requests for automatic entry and explicit budget management."""
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from budget import financial_areas as areas
from budget.financial_models import AreaAccessChange, FinancialAreaGrant
from budget.models import Category, Membership
from budget.tests.test_domain import setup_family


@override_settings(ALLOWED_HOSTS=['testserver'], PREREGISTERED_LOGIN_ENABLED=True)
class BudgetEntryManagementTests(TestCase):
    def setUp(self):
        self.owner, self.house, self.category = setup_family('entry-management@example.test')
        self.member = Membership.objects.get(user=self.owner)
        self.area = self.owner.test_area
        self.area.name = 'Husholdningens budsjett'
        self.area.save()
        self.reader_user = get_user_model().objects.create_user('management-reader', email='reader@example.test')
        self.reader = Membership.objects.create(user=self.reader_user, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=self.reader, role='reader')
        self.client = Client()
        self.client.force_login(self.owner)

    def assert_destination(self, response, path='/app/oversikt/', **query):
        self.assertEqual(response.status_code, 302)
        target = urlsplit(response['Location'])
        self.assertEqual(target.path, path)
        self.assertEqual(target.netloc, '')
        self.assertEqual(parse_qs(target.query), {'area': [str(self.area.pk)], **{key: [value] for key, value in query.items()}})
        return response['Location']

    def test_home_and_password_login_open_only_budget_without_chooser_click(self):
        response = self.client.get('/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/app/oversikt/')
        self.assertEqual(parse_qs(response.request['QUERY_STRING']), {'area': [str(self.area.pk)]})
        password = 'Synthetic-login-ForTests!73'
        self.owner.set_password(password)
        self.owner.save()
        self.member.identity_method = 'preregistered_owner'
        self.member.provisioned_at = timezone.now()
        self.member.provisioning_digest = 'synthetic-provisioning'
        self.member.save()
        self.client.logout()
        response = self.client.post('/passord/', {'email': self.owner.email, 'password': password}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/app/oversikt/')
        self.assertEqual(parse_qs(response.request['QUERY_STRING'])['area'], [str(self.area.pk)])

    def test_auto_open_keeps_target_filters_and_does_not_store_selection(self):
        session_before = dict(self.client.session)
        first = self.client.get('/app/poster/?month=2026-09&q=Mat')
        self.assertEqual(first.status_code, 302)
        target = self.assert_destination(self.client.get(first['Location']), '/app/poster/', month='2026-09', q='Mat')
        self.assertEqual(self.client.get(target).status_code, 200)
        self.assertEqual(dict(self.client.session), session_before)
        self.assert_destination(self.client.head('/budsjetter/'))

    def test_explicit_management_and_creation_validation_remain_visible(self):
        response = self.client.get('/budsjetter/?manage=1')
        self.assertContains(response, 'Husholdningens budsjett')
        self.assertContains(response, 'budget-card-grid')
        self.assertContains(response, 'Opprett et tomt budsjett')
        self.assertNotContains(response, 'budget-disclosure" open')
        response = self.client.post('/budsjetter/?manage=1', {'action': 'create', 'name': '', 'kind': 'personal', 'sharing': 'private'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['create_form'].errors)
        self.assertContains(response, 'budget-disclosure" open')

    def test_pending_proposal_does_not_block_single_budget_entry(self):
        change = areas.propose_access_change(self.member, self.area.pk, [], [])
        self.assert_destination(self.client.get('/budsjetter/'))
        response = self.client.get('/budsjetter/?manage=1')
        self.assertEqual([item.pk for item in response.context['proposals']], [change.pk])
        self.assertContains(response, 'Se gjennom forslag')

    def test_multiple_budgets_stay_explicit_and_tabs_keep_separate_area_urls(self):
        second = areas.create_area(self.member, 'Second budget')
        response = self.client.get('/', follow=True)
        self.assertEqual(response.request['PATH_INFO'], '/budsjetter/')
        self.assertEqual(len(response.context['areas']), 2)
        for area in (self.area, second, self.area):
            response = self.client.get('/app/kategorier/', {'area': str(area.pk)})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.wsgi_request.financial_area.pk, area.pk)
        self.assertEqual(self.client.get('/budsjetter/').status_code, 200)

    def test_reader_auto_open_never_upgrades_write_access_and_no_grant_admin_sees_no_budget(self):
        self.client.force_login(self.reader_user)
        self.assert_destination(self.client.get('/budsjetter/'))
        response = self.client.get('/ny/category/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/budsjetter/')
        self.assertEqual(response.context['areas'], [])
        self.assertEqual(self.client.get('/ny/category/', {'area': self.area.pk}).status_code, 403)
        FinancialAreaGrant.objects.filter(area=self.area, member=self.reader).delete()
        self.reader.role = 'admin'
        self.reader.save()
        response = self.client.get('/budsjetter/')
        self.assertContains(response, 'Ingen tilgjengelige budsjetter ennå')
        self.assertNotContains(response, 'Husholdningens budsjett')

    def test_explicit_invalid_area_post_and_api_never_use_automatic_fallback(self):
        foreign, _, _ = setup_family('management-foreign@example.test')
        for area in ('', 'not-a-uuid', str(foreign.test_area.pk)):
            self.assertEqual(self.client.get('/app/oversikt/', {'area': area}).status_code, 403)
        self.assertEqual(self.client.get('/app/oversikt/?area=%s&area=%s' % (self.area.pk, self.area.pk)).status_code, 403)
        self.assertEqual(self.client.post('/ny/category/', {'name': 'Must not save'}).status_code, 403)
        self.assertEqual(self.client.get('/app/forbruk/data/').status_code, 403)
        self.assertEqual(self.client.get('/app/handlelister/').status_code, 200)
        self.assertIsNone(getattr(self.client.get('/app/handlelister/').wsgi_request, 'financial_area', None))

    def test_external_or_malformed_next_falls_back_to_own_overview(self):
        for destination in ('https://evil.test/app/poster/', '//evil.test/app/poster/', 'http://[', '/unknown/', '/utlogging/'):
            self.assert_destination(self.client.get('/budsjetter/', {'next': destination}))

    def test_legacy_unassigned_data_prevents_auto_open_without_changing_data(self):
        Category.all_objects.filter(pk=self.category.pk).update(financial_area=None)
        before = list(Category.all_objects.filter(household=self.house).values())
        response = self.client.get('/budsjetter/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fordel eksisterende budsjett')
        self.assertEqual(list(Category.all_objects.filter(household=self.house).values()), before)

    def test_stale_and_applied_proposals_are_collapsed_readonly_history(self):
        stale = areas.propose_access_change(self.member, self.area.pk, [], [])
        applied = areas.propose_access_change(self.member, self.area.pk, [self.reader.pk], [])
        areas.confirm_access_change(self.member, applied.pk, applied.digest)
        areas.confirm_access_change(self.reader, applied.pk, applied.digest)
        current = areas.propose_access_change(self.member, self.area.pk, [], [])
        before = list(AreaAccessChange.objects.order_by('pk').values())
        grants_before = list(FinancialAreaGrant.objects.order_by('pk').values())
        response = self.client.get('/budsjetter/?manage=1')
        self.assertEqual([item.pk for item in response.context['proposals']], [current.pk])
        self.assertEqual({item.pk for item in response.context['proposal_history']}, {stale.pk, applied.pk})
        content = response.content.decode()
        primary, history = content.split('<details class="work-surface budget-disclosure budget-proposal-history">')
        self.assertNotIn(reverse('financial_proposal', args=[stale.pk]), primary)
        self.assertNotIn(reverse('financial_proposal', args=[applied.pk]), primary)
        self.assertIn(reverse('financial_proposal', args=[stale.pk]), history)
        self.assertIn('Utdatert – kan ikke bekreftes', history)
        self.assertIn('Gjennomført', history)
        self.assertEqual(list(AreaAccessChange.objects.order_by('pk').values()), before)
        self.assertEqual(list(FinancialAreaGrant.objects.order_by('pk').values()), grants_before)
        self.assertEqual(self.client.get(reverse('financial_proposal', args=[stale.pk])).status_code, 200)

    def test_proposal_history_respects_existing_owner_participant_and_household_access(self):
        change = areas.propose_access_change(self.member, self.area.pk, [self.reader.pk], [])
        AreaAccessChange.objects.filter(pk=change.pk).update(expected_version=999)
        self.client.force_login(self.reader_user)
        response = self.client.get('/budsjetter/?manage=1')
        self.assertEqual([item.pk for item in response.context['proposal_history']], [change.pk])
        outsider = get_user_model().objects.create_user('management-outsider')
        Membership.objects.create(user=outsider, household=self.house, role='member')
        self.client.force_login(outsider)
        response = self.client.get('/budsjetter/?manage=1')
        self.assertEqual(response.context['proposal_history'], [])
        self.assertEqual(self.client.get(reverse('financial_proposal', args=[change.pk])).status_code, 403)
        foreign, _, _ = setup_family('management-history-foreign@example.test')
        self.client.force_login(foreign)
        response = self.client.get('/budsjetter/?manage=1')
        self.assertEqual(response.context['proposal_history'], [])
        self.assertEqual(self.client.get(reverse('financial_proposal', args=[change.pk])).status_code, 404)
