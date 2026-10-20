"""Public HTTPS through the existing tunnel, with plain HTTP to Gunicorn."""
from django.conf import settings
from django.test import Client, TestCase, override_settings
from budget import identity


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['blikk.betilab.com'],
    CSRF_TRUSTED_ORIGINS=['https://blikk.betilab.com'],
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    PREREGISTERED_LOGIN_ENABLED=True,
)
class CloudflareHostingTests(TestCase):
    headers = {'HTTP_HOST': 'blikk.betilab.com', 'HTTP_X_FORWARDED_PROTO': 'https'}

    def setUp(self):
        self.password = 'Synthetic-Tunnel!26-Test'
        self.member, _ = identity.provision_owner(
            {'owner_email': 'tunnel@example.test', 'source_sha256': 'a' * 64,
             'import_series': 'synthetic-tunnel', 'household_id': None},
            self.password, 'Tunnelfamilie',
        )

    def test_plain_http_origin_recognizes_public_https_and_login_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get('/passord/', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.is_secure())
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post('/passord/', {
            'email': self.member.user.email, 'password': self.password,
            'csrfmiddlewaretoken': token,
        }, HTTP_ORIGIN='https://blikk.betilab.com', **self.headers)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
        self.assertEqual(int(client.session['_auth_user_id']), self.member.user_id)
        response = client.get(response.url, follow=True, **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.is_secure())

    def test_wrong_origin_and_host_are_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/passord/', **self.headers)
        response = client.post('/passord/', {
            'email': self.member.user.email, 'password': self.password,
            'csrfmiddlewaretoken': client.cookies[settings.CSRF_COOKIE_NAME].value,
        }, HTTP_ORIGIN='https://unrelated.example.test', **self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', client.session)
        self.assertEqual(client.get('/passord/', HTTP_HOST='unrelated.example.test',
                                    HTTP_X_FORWARDED_PROTO='https').status_code, 400)
