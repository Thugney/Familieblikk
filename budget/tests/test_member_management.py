"""Admins deactivate, reactivate and re-role members; nothing financial is deleted."""
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.utils import timezone
from budget import access
from budget.financial_test_helpers import AreaClient
from budget.models import Audit, Category, Entry, Membership
from budget.tests.test_member_access import family_fixture


class MemberManagementTests(TestCase):
    def setUp(self):
        family_fixture(self)
        self.url = f'/familie/medlem/{self.member.pk}/'
        self.admin_client = AreaClient(self.area); self.admin_client.force_login(self.admin)
        self.client.force_login(self.user)

    def change(self, action, version=None, member=None, client=None):
        target = member or self.member
        target.refresh_from_db()
        return (client or self.admin_client).post(f'/familie/medlem/{target.pk}/', {
            'action': action, 'version': target.access_version if version is None else version, 'confirm': 'on'})

    def sessions_for(self, user):
        return [s for s in Session.objects.all() if s.get_decoded().get('_auth_user_id') == str(user.pk)]

    def test_deactivate_logs_out_keeps_records_and_reactivate_restores_login(self):
        category = Category.objects.create(household=self.house, created_by=self.admin, name='Mat')
        entry = Entry.objects.create(household=self.house, created_by=self.user, kind='expense', amount_ore=1234,
                                     effective_date=timezone.localdate(), category=category)
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 200)
        self.assertEqual(self.change('deactivate').status_code, 302)
        self.user.refresh_from_db(); self.member.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.member.access_version, 2)
        self.assertEqual(self.sessions_for(self.user), [])
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 302)
        self.assertTrue(Entry.all_objects.filter(pk=entry.pk, active=True).exists())
        self.assertNotIn(self.member.pk, [m.pk for m in access.calendar_members(self.house)])
        self.assertContains(self.admin_client.get('/app/familie/'), 'Deaktivert')
        audit = Audit.all_objects.filter(operation='modultilgang').latest('at')
        self.assertEqual(audit.changes['action'], 'deactivate')
        self.assertIsNone(audit.financial_area_id)
        self.assertEqual(self.change('reactivate').status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_role_change_promotes_and_demotes(self):
        self.assertEqual(self.change('make_admin').status_code, 302)
        self.member.refresh_from_db(); self.assertEqual(self.member.role, 'admin')
        self.assertEqual(self.change('make_member').status_code, 302)
        self.member.refresh_from_db(); self.assertEqual(self.member.role, 'member')

    def test_guards_self_owner_stale_version_non_admin_and_foreign(self):
        self.assertEqual(self.admin_client.get(f'/familie/medlem/{self.admin_member.pk}/').status_code, 403)
        Membership.objects.filter(pk=self.peer_member.pk).update(identity_method='preregistered_owner', role='admin')
        response = self.change('deactivate', member=self.peer_member)
        self.assertEqual(response.status_code, 400)
        self.peer.refresh_from_db(); self.assertTrue(self.peer.is_active)
        self.assertEqual(self.change('deactivate', version=99).status_code, 409)
        self.user.refresh_from_db(); self.assertTrue(self.user.is_active)
        self.assertEqual(self.change('deactivate', client=self.client, member=self.peer_member).status_code, 403)
        foreign = AreaClient(self.area); foreign.force_login(self.foreign)
        self.assertEqual(foreign.get(self.url).status_code, 404)
        missing_confirm = self.admin_client.post(self.url, {'action': 'deactivate', 'version': self.member.access_version})
        self.assertEqual(missing_confirm.status_code, 400)
        self.user.refresh_from_db(); self.assertTrue(self.user.is_active)

    def test_family_page_links_every_other_member_to_management(self):
        page = self.admin_client.get('/app/familie/')
        self.assertContains(page, self.url)
        self.assertNotContains(page, f'/familie/medlem/{self.admin_member.pk}/')
        self.assertNotContains(page, 'Innsynsvalg for eget budsjett ved opprettelse')
