"""Response-policy and password-change regressions with synthetic data."""
from html.parser import HTMLParser
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from budget import document_storage, identity
from budget.financial_test_helpers import install_area
from budget.models import Document
from budget.tests.test_preregistered_auth import PASSWORD, binding


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))
        self.inline_handlers.extend(name for name, _ in attrs if name.startswith('on'))


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
class ResponsePolicyRegressionTests(TestCase):
    def test_retained_original_keeps_sandbox_and_private_download_headers(self):
        member, _ = identity.provision_owner(binding(), PASSWORD, 'Synthetic household')
        install_area(self, member, area=member.financialareagrant_set.get(role='owner').area)
        self.client.force_login(member.user)
        original = b'%PDF-1.7\nSynthetic retained original\n%%EOF'
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_DOCUMENT_ROOT=directory):
            key = document_storage.store(member.household_id, original)
            document = Document.objects.create(household=member.household, created_by=member.user,
                content_type='application/pdf', storage_key=key, size=len(original), filename='synthetic.pdf')
            url = reverse('document_original', args=[document.pk])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Security-Policy'], "default-src 'none'; sandbox")
            self.assertEqual(response['X-Frame-Options'], 'DENY')
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertIn('Cookie', response['Vary'])
            self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(b''.join(response.streaming_content), original)
            response.close()
            denied = Client().get(url)
            self.assertEqual(denied.status_code, 302)
            self.assertIn('no-store', denied['Cache-Control'])
            self.assertEqual(denied['X-Frame-Options'], 'DENY')

    def test_application_and_error_responses_get_default_policy_and_link_retry(self):
        for url, expected in [('/passord/', 200), ('/missing-security-test/?retry=1', 404)]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, expected)
                self.assertIn("script-src 'self';", response['Content-Security-Policy'])
                self.assertIn("script-src-attr 'none';", response['Content-Security-Policy'])
                self.assertIn('no-store', response['Cache-Control'])
        parsed = Links()
        parsed.feed(response.content.decode())
        self.assertIn({'class': 'secondary', 'href': ''}, parsed.links)
        self.assertEqual(parsed.inline_handlers, [])


class PasswordChangeLimitTests(TestCase):
    def setUp(self):
        self.member, _ = identity.provision_owner(binding(), PASSWORD, 'Synthetic household')
        install_area(self, self.member, area=self.member.financialareagrant_set.get(role='owner').area)
        self.client.force_login(self.member.user)
        self.original_hash = self.member.user.password

    def test_oversized_old_password_is_rejected_before_password_verification(self):
        with patch.object(get_user_model(), 'check_password') as check:
            response = self.client.post('/passord/endre/', {
                'old_password': 'x' * (identity.MAX_PASSWORD_LENGTH + 1),
                'new_password1': 'Another-safe!river-83', 'new_password2': 'Another-safe!river-83'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('old_password', response.context['form'].errors)
            check.assert_not_called()
        self.member.user.refresh_from_db()
        self.assertEqual(self.member.user.password, self.original_hash)

    def test_oversized_new_password_preserves_existing_hash(self):
        oversized = 'Different!safe-72-' * 70
        self.assertGreater(len(oversized), identity.MAX_PASSWORD_LENGTH)
        response = self.client.post('/passord/endre/', {
            'old_password': PASSWORD, 'new_password1': oversized, 'new_password2': oversized})
        self.assertEqual(response.status_code, 200)
        self.assertIn('new_password1', response.context['form'].errors)
        self.assertIn('new_password2', response.context['form'].errors)
        self.member.user.refresh_from_db()
        self.assertEqual(self.member.user.password, self.original_hash)
        self.assertTrue(self.member.user.check_password(PASSWORD))
