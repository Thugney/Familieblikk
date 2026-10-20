import io
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone
from budget import identity, importing
from budget.models import Category, Entry, Household, LoginCode, Membership, PasswordAttempt
from budget.tests.test_domain import setup_family

PASSWORD = 'Synthetic-river!72-Safe'


def binding(email='owner@example.test'):
    return {'owner_email': email, 'source_sha256': 'a' * 64, 'import_series': 'synthetic-owner', 'household_id': None}


class PreregisteredAuthTests(TestCase):
    def setUp(self):
        self.binding = binding()
        self.member, _ = identity.provision_owner(self.binding, PASSWORD, 'Privat testfamilie')

    def test_provision_idempotent_no_email_verification_no_takeover(self):
        same, created = identity.provision_owner(self.binding, 'must-not-reset', 'Other')
        self.assertFalse(created)
        self.assertEqual(same.pk, self.member.pk)
        self.assertEqual(Household.objects.count(), 1)
        self.assertTrue(same.user.check_password(PASSWORD))
        self.assertIsNone(same.verified_at)
        self.assertTrue(same.can_register_households)
        self.assertFalse(Entry.objects.exists())
        user, house, category = setup_family('existing@example.test')
        with self.assertRaises(ValidationError): identity.provision_owner(binding(user.email), PASSWORD, 'Takeover')
        self.assertEqual(Membership.objects.get(user=user).household, house)

    def test_actual_password_session_rotation_owner_import_and_other_denial(self):
        session = self.client.session
        session['verified_email'] = self.member.user.email
        session['verified_at'] = 'not-real'
        session.save()
        old_session = session.session_key
        response = self.client.post('/passord/', {'email': self.member.user.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertNotEqual(old_session, session.session_key)
        self.assertNotIn('verified_email', session)
        self.assertNotIn('verified_at', session)
        self.assertEqual(session['identity_method'], 'preregistered_owner')
        self.assertEqual(importing.owner_membership(self.member.user, None, self.binding, session).pk, self.member.pk)
        source = {'source': {'sha256': 'a' * 64}, 'import_series': 'synthetic-owner', 'source_selected_month': '2026-09'}
        first = importing.apply_import(self.member.user, None, source, self.binding, session)
        self.assertEqual(importing.apply_import(self.member.user, None, source, self.binding, session).pk, first.pk)
        other, _, _ = setup_family('other@example.test')
        with self.assertRaises(PermissionDenied): importing.apply_import(other, None, source, self.binding, session)
        self.assertIn('?month=2026-09', self.client.post('/passord/', {'email': self.member.user.email, 'password': PASSWORD}).url)

    def test_wrong_password_rate_disabled_and_otp_account_denied(self):
        for _ in range(5):
            response = self.client.post('/passord/', {'email': self.member.user.email, 'password': 'wrong'})
            self.assertContains(response, 'Innloggingen kunne ikke bekreftes')
        self.assertContains(self.client.post('/passord/', {'email': self.member.user.email, 'password': PASSWORD}), 'Innloggingen kunne ikke bekreftes')
        self.assertNotIn('_auth_user_id', self.client.session)
        PasswordAttempt.objects.all().delete()
        with self.settings(PREREGISTERED_LOGIN_ENABLED=False):
            self.assertContains(Client().post('/passord/', {'email': self.member.user.email, 'password': PASSWORD}), 'Innloggingen kunne ikke bekreftes')
        otp, _, _ = setup_family('otp@example.test')
        otp.set_password(PASSWORD)
        otp.save()
        self.assertContains(Client().post('/passord/', {'email': otp.email, 'password': PASSWORD}), 'Innloggingen kunne ikke bekreftes')
        PasswordAttempt.objects.all().delete()
        self.member.user.is_active = False
        self.member.user.save()
        self.assertContains(Client().post('/passord/', {'email': self.member.user.email, 'password': PASSWORD}), 'Innloggingen kunne ikke bekreftes')
        self.assertEqual(Client(enforce_csrf_checks=True).post('/passord/', {'email': self.member.user.email, 'password': PASSWORD}).status_code, 403)

    def test_provision_command_confirmation_stdin_and_private_binding(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError): call_command('provision_owner', stdout=io.StringIO())
        with patch('budget.management.commands.provision_owner.load_private_source', return_value=({'import_series': self.binding['import_series']}, self.binding)), patch('sys.stdin', io.StringIO('different-not-used\n')):
            output = io.StringIO()
            call_command('provision_owner', confirm=True, password_stdin=True, stdout=output)
            self.assertIn('uendret', output.getvalue())
            self.assertNotIn(PASSWORD, output.getvalue())
        with patch('budget.management.commands.import_family_budget.importing.load_private_source', return_value=({'import_series': self.binding['import_series'], 'source': {'sha256': 'a' * 64}}, self.binding)):
            call_command('import_family_budget', owner_email=self.member.user.email, household_id=str(self.member.household_id), confirm=True, stdout=io.StringIO())
        self.member.provisioning_digest = 'invalid'
        self.member.save()
        with patch('budget.management.commands.import_family_budget.importing.load_private_source', return_value=({'import_series': self.binding['import_series'], 'source': {'sha256': 'a' * 64}}, self.binding)):
            with self.assertRaises(CommandError): call_command('import_family_budget', owner_email=self.member.user.email, household_id=str(self.member.household_id), confirm=True, stdout=io.StringIO())

    def test_admin_registration_separate_families_roles_and_no_budget_access(self):
        child = identity.register_family_account(self.member.user, 'member@example.test', PASSWORD)
        self.assertEqual(child.household, self.member.household)
        self.assertIsNone(child.verified_at)
        self.assertEqual(child.identity_method, 'preregistered_member')
        separate = identity.register_family_account(self.member.user, 'newadmin@example.test', PASSWORD, family_name='Annen familie')
        self.assertNotEqual(separate.household, self.member.household)
        self.assertFalse(separate.can_register_households)
        self.assertEqual(separate.role, 'admin')
        category = Category.objects.create(household=separate.household, created_by=separate.user, name='Fremmed privat kategori')
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.get(f'/endre/category/{category.pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/app/budsjett/'), 'Fremmed privat kategori')
        self.client.force_login(child.user)
        self.assertEqual(self.client.get('/registrer/medlem/').status_code, 403)
        self.assertEqual(self.client.get('/registrer/familie/').status_code, 403)
        self.client.force_login(separate.user)
        self.assertEqual(self.client.get('/registrer/familie/').status_code, 403)
        self.assertEqual(self.client.get('/registrer/medlem/').status_code, 200)
        self.assertEqual(Client().get('/registrer/medlem/').status_code, 302)
        self.assertEqual(Client(enforce_csrf_checks=True).post('/registrer/medlem/', {}).status_code, 403)
        with self.assertRaises(PermissionDenied): identity.register_family_account(separate.user, 'denied@example.test', PASSWORD, family_name='Forbidden')
        with self.assertRaises(ValidationError): identity.register_family_account(self.member.user, child.user.email, PASSWORD)
        foreign_context = {'identity_method': separate.identity_method, 'preregistered_membership_id': separate.pk, 'provisioning_digest': separate.provisioning_digest}
        with self.assertRaises(PermissionDenied): importing.owner_membership(separate.user, None, self.binding, foreign_context)
        response = Client().post('/passord/', {'email': child.user.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_password_change_keeps_session_and_invalidates_old_password(self):
        self.client.post('/passord/', {'email': self.member.user.email, 'password': PASSWORD})
        new_password = 'Another-safe!river-83'
        response = self.client.post('/passord/endre/', {'old_password': PASSWORD, 'new_password1': new_password, 'new_password2': new_password})
        self.assertEqual(response.status_code, 302)
        self.member.user.refresh_from_db()
        self.assertFalse(self.member.user.check_password(PASSWORD))
        self.assertTrue(self.member.user.check_password(new_password))
        self.assertEqual(self.client.get('/app/oversikt/').status_code, 200)

    def test_successful_registration_http_posts_and_new_admin_isolation(self):
        creator_category = Category.objects.create(household=self.member.household, created_by=self.member.user, name='Kun oppretterens familie')
        self.client.post('/passord/', {'email': self.member.user.email, 'password': PASSWORD})
        response = self.client.post('/registrer/medlem/', {'email': 'http-member@example.test', 'role': 'member', 'password1': PASSWORD, 'password2': PASSWORD, 'confirm': 'on'})
        self.assertEqual(response.status_code, 302, response.content.decode())
        member = Membership.objects.get(user__email='http-member@example.test')
        self.assertEqual(member.household_id, self.member.household_id)
        self.assertEqual(member.identity_method, 'preregistered_member')
        response = self.client.post('/registrer/familie/', {'email': 'http-admin@example.test', 'family_name': 'Helt egen familie', 'password1': PASSWORD, 'password2': PASSWORD, 'confirm': 'on'})
        self.assertEqual(response.status_code, 302, response.content.decode())
        admin = Membership.objects.get(user__email='http-admin@example.test')
        self.assertNotEqual(admin.household_id, self.member.household_id)
        self.assertEqual(admin.role, 'admin')
        self.assertEqual(admin.identity_method, 'preregistered_admin')
        self.assertFalse(admin.can_register_households)
        self.assertIsNone(admin.verified_at)
        other_client = Client()
        response = other_client.post('/passord/', {'email': admin.user.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('verified_email', other_client.session)
        response = other_client.get('/app/budsjett/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ingen kategorier ennå')
        self.assertNotContains(response, creator_category.name)
        self.assertEqual(other_client.get(f'/endre/category/{creator_category.pk}/').status_code, 404)
        self.assertEqual(other_client.get('/registrer/familie/').status_code, 403)
        self.assertFalse(Entry.objects.filter(household=admin.household).exists())

    def test_invitation_ui_requires_configured_smtp(self):
        self.client.force_login(self.member.user)
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend', EMAIL_HOST=''):
            response = self.client.get('/app/familie/')
            self.assertContains(response, 'Medlemmer registreres med passord.')
            self.assertContains(response, 'Legg til familiemedlem')
            self.assertContains(response, 'Opprett en ny familie')
            self.assertNotContains(response, 'Send invitasjon')
            self.assertNotContains(response, 'action="/inviter/"')
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.test'):
            response = self.client.get('/app/familie/')
            self.assertContains(response, 'Send invitasjon')
            self.assertContains(response, 'action="/inviter/"')


class RegistrationRaceTests(TransactionTestCase):
    def test_duplicate_registration_race_creates_one_membership(self):
        owner, _ = identity.provision_owner(binding(), PASSWORD, 'Race family')
        def register(_):
            close_old_connections()
            actor = get_user_model().objects.get(pk=owner.user_id)
            try:
                identity.register_family_account(actor, 'race@example.test', PASSWORD)
                return True
            except ValidationError:
                return False
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(register, [1, 2]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Membership.objects.filter(user__email='race@example.test').count(), 1)

    def test_otp_consumption_and_registration_share_email_lock(self):
        owner, _ = identity.provision_owner(binding(), PASSWORD, 'Race family')
        email, code = 'otp-race@example.test', '123456'
        LoginCode.objects.create(email=email, digest=identity.digest(email + ':' + code), sent_at=timezone.now(), expires_at=timezone.now() + timedelta(minutes=10), ip_digest='synthetic')
        def operation(mode):
            close_old_connections()
            try:
                if mode == 'otp':
                    request = RequestFactory().get('/kode/')
                    SessionMiddleware(lambda req: None).process_request(request)
                    return identity.verify_code(request, email, code).pk
                actor = get_user_model().objects.get(pk=owner.user_id)
                try: return identity.register_family_account(actor, email, PASSWORD).user_id
                except ValidationError: return None
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(operation, ['otp', 'register']))
        user = get_user_model().objects.get(email=email)
        self.assertEqual(results[0], user.pk)
        self.assertTrue(results[1] is None or results[1] == user.pk)
        self.assertLessEqual(Membership.objects.filter(user=user).count(), 1)
