import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings
from django.core.exceptions import ValidationError
from .models import Household, Membership, Category
from .financial_areas import create_area, area_scope
from .area_requests import financial_url
from . import identity

class AreaURLTests(SimpleTestCase):
    def test_query_fragment_and_foreign_links(self):
        area = uuid.uuid4()
        self.assertEqual(financial_url('/app/poster/?month=2026-10#rows', area), '/app/poster/?month=2026-10&area=' + str(area) + '#rows')
        self.assertEqual(financial_url('https://other.test/app/poster/', area), 'https://other.test/app/poster/')
        self.assertEqual(financial_url('/app/kalender/', area), '/app/kalender/')
        self.assertEqual(financial_url('/app/poster/?area=other', area), '/app/poster/?area=other')

@override_settings(ALLOWED_HOSTS=['testserver'], PREREGISTERED_LOGIN_ENABLED=True)
class FinancialUITests(TestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic family')
        self.owner = self.member('owner', 'member')
        self.reader = self.member('reader', 'admin')
        self.other = self.member('other', 'admin')
        self.area = create_area(self.owner, 'Private A', [self.reader.pk])
        self.second = create_area(self.owner, 'Private B')
        with area_scope(self.owner, self.area.pk):
            Category.objects.create(household=self.house, name='Only A', created_by=self.owner.user)
        with area_scope(self.owner, self.second.pk):
            Category.objects.create(household=self.house, name='Only B', created_by=self.owner.user)
    def member(self, name, role):
        user = get_user_model().objects.create_user(username=name, email=name+'@example.test', password='Fictional-password-234!')
        return Membership.objects.create(user=user, household=self.house, role=role)
    def test_explicit_selection_and_two_tabs(self):
        self.client.force_login(self.owner.user)
        self.assertEqual(self.client.get('/app/kategorier/')['Location'], '/budsjetter/?next=%2Fapp%2Fkategorier%2F')
        for area, yes, no in [(self.area, 'Only A', 'Only B'), (self.second, 'Only B', 'Only A'), (self.area, 'Only A', 'Only B')]:
            response = self.client.get('/app/kategorier/', {'area': area.pk})
            self.assertContains(response, yes)
            self.assertNotContains(response, no)
            self.assertContains(response, 'name="area" value="'+str(area.pk)+'"')
    def test_admin_without_grant_and_conflicting_target_denied(self):
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get('/app/kategorier/', {'area': self.area.pk}).status_code, 403)
        self.client.force_login(self.owner.user)
        self.assertEqual(self.client.post('/ny/category/?area='+str(self.area.pk), {'area': str(self.second.pk)}).status_code, 403)
        self.assertEqual(self.client.post('/ny/category/', {'name': 'Wrong'}).status_code, 403)
    def test_reader_can_read_but_not_write(self):
        self.client.force_login(self.reader.user)
        self.assertContains(self.client.get('/app/kategorier/', {'area': self.area.pk}), 'Only A')
        self.assertEqual(self.client.post('/ny/category/?area='+str(self.area.pk), {'name': 'No'}).status_code, 403)
        self.assertEqual(self.client.get('/ny/category/', {'area': self.area.pk}).status_code, 403)
        response = self.client.get('/app/oversikt/', {'area': self.area.pk})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '>Ny post</a>')
        self.assertNotContains(response, '>Merk som betalt</a>')
        self.assertContains(response, 'Kun innsyn')
    def test_metadata_and_chooser_without_area(self):
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get('/app/familie/').status_code, 200)
        self.assertEqual(self.client.get('/budsjetter/').status_code, 200)
        self.assertEqual(self.client.get('/app/kalender/').status_code, 200)
        self.assertEqual(self.client.get('/app/handlelister/').status_code, 200)
    def test_new_member_requires_choice_and_is_empty(self):
        with self.assertRaises(ValidationError):
            identity.register_family_account(self.other.user, 'new@example.test', 'Fictional-pass-234!')
        new = identity.register_family_account(self.other.user, 'new@example.test', 'Fictional-pass-234!', financial_sharing='private')
        area = new.financialareagrant_set.get().area
        with area_scope(new, area.pk):
            self.assertEqual(Category.objects.count(), 0)

    def test_single_account_legacy_bootstrap_keeps_two_confirmations(self):
        from .financial_areas import legacy_inventory, propose_legacy_setup, confirm_access_change
        from .financial_models import FinancialAreaGrant
        # A pre-migration row is quarantined, not assigned by account registration.
        Category.all_objects.filter(household=self.house, financial_area=self.area).update(financial_area=None)
        new = identity.register_family_account(self.other.user, 'second@example.test', 'Fictional-pass-234!', role='admin', financial_sharing='private')
        self.assertEqual(Category.all_objects.filter(household=self.house, financial_area=None).count(), 1)
        inventory = legacy_inventory(self.other)
        change = propose_legacy_setup(self.other, self.other.pk, [], [], inventory['fingerprint'])
        confirm_access_change(self.other, change.pk, change.digest)
        change.refresh_from_db()
        self.assertFalse(change.applied)
        confirm_access_change(new, change.pk, change.digest)
        change.refresh_from_db()
        self.assertTrue(change.applied)

    def test_missing_area_returns_to_requested_financial_route_safely(self):
        from urllib.parse import urlencode
        self.client.force_login(self.owner.user)
        self.assertEqual(self.client.get('/app/mer/').status_code, 200)
        response = self.client.get('/app/dokumenter/')
        self.assertEqual(response.status_code, 302)
        chooser = self.client.get(response['Location'])
        self.assertContains(chooser, '/app/dokumenter/?area=' + str(self.area.pk))
        self.assertEqual(self.client.get('/app/dokumenter/', {'area': self.area.pk}).status_code, 200)
        for unsafe in ('https://evil.test/', '//evil.test/', '/unknown/', '/utlogging/'):
            response = self.client.get('/budsjetter/', {'next': unsafe})
            self.assertContains(response, '/app/oversikt/?area=' + str(self.area.pk))
            self.assertNotContains(response, 'href="' + unsafe)

    def test_owner_controls_only_selected_area_preferences(self):
        self.client.force_login(self.owner.user)
        url = '/preferanser/?area=' + str(self.area.pk)
        response = self.client.post(url, {'version': self.area.access_version, 'debt': 'on', 'confirm': 'on'})
        self.assertEqual(response.status_code, 302)
        self.area.refresh_from_db()
        self.second.refresh_from_db()
        self.assertTrue(self.area.modules['debt'])
        self.assertNotIn('debt', self.second.modules)
        for member in (self.reader, self.other):
            self.client.force_login(member.user)
            self.assertEqual(self.client.post(url, {'version': self.area.access_version, 'confirm': 'on'}).status_code, 403)
