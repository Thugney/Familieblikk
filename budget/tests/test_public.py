from pathlib import Path
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from django.template.loader import get_template
from django.test import SimpleTestCase
from budget.services import debt_projection, month_end, next_month


class PublicContractTests(SimpleTestCase):
    def test_password_page_only_offers_email_code_with_configured_smtp(self):
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend', EMAIL_HOST=''):
            response = self.client.get('/passord/')
            self.assertContains(response, 'Bruk e-postadressen og passordet du har fått fra administratoren.')
            self.assertNotContains(response, 'href="/innlogging/"')
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.test'):
            self.assertContains(self.client.get('/passord/'), 'href="/innlogging/"')

    def test_public_routes_and_no_arbitrary_file_access(self):
        for path in ['/offline/', '/manifest.webmanifest', '/static/budget/icon.svg', '/static/budget/app.css', '/sw.js']:
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ['/private-data/family-budget/profile-target.json', '/work/source-receipt.json', '/static/budget/../../settings.py']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_all_templates_compile(self):
        for file in Path('budget/templates/budget').glob('*.html'):
            get_template('budget/' + file.name)

    def test_worker_only_caches_public_allowlist(self):
        source = Path('budget/static/budget/sw.js').read_text(encoding='utf-8')
        self.assertIn("PUBLIC.includes(url.pathname)", source)
        self.assertIn("fetch(event.request, {cache: 'no-store'})", source)
        self.assertIn("credentials: 'omit'", source)

    def test_worker_deploy_version_changes_with_public_content(self):
        from unittest.mock import patch
        first = self.client.get('/sw.js').content
        original = Path.read_bytes
        def changed(path):
            return original(path) + b'changed' if path.name == 'app.css' else original(path)
        with patch.object(Path, 'read_bytes', changed):
            second = self.client.get('/sw.js').content
        self.assertNotEqual(first, second)
        self.assertNotIn(b'__PUBLIC_VERSION__', first)

    def test_worker_version_includes_push_and_loader_assets(self):
        from unittest.mock import patch
        first = self.client.get('/sw.js').content
        original = Path.read_bytes
        for name in ['push.js', 'loader.js', 'loader.css', 'loader-logo.png', 'loader-icon.png']:
            with self.subTest(name=name):
                def changed(path): return original(path) + b'new-deploy' if path.name == name else original(path)
                with patch.object(Path, 'read_bytes', changed):
                    self.assertNotEqual(first, self.client.get('/sw.js').content)

    def test_loader_update_changes_the_asset_urls_in_the_page(self):
        from unittest.mock import patch
        from budget.templatetags.budget_tags import loader_static
        original = Path.read_bytes
        for name in ('loader.css', 'loader.js'):
            with self.subTest(name=name):
                before = loader_static(name)
                self.assertContains(self.client.get('/passord/'), before)
                self.assertEqual(self.client.get(before).status_code, 200)
                def changed(path):
                    return original(path) + b'new-release' if path.name == name else original(path)
                with patch.object(Path, 'read_bytes', changed):
                    after = loader_static(name)
                    self.assertNotEqual(before, after)
                    self.assertContains(self.client.get('/passord/'), after)
                    self.assertNotContains(self.client.get('/passord/'), before)

    def test_calendar_and_projection(self):
        self.assertEqual(month_end(date(2028, 2, 1)), date(2028, 2, 29))
        self.assertEqual(next_month(date(2026, 12, 1)), date(2027, 1, 1))
        asset = SimpleNamespace(pk='a', opening_ore=10000, annual_rate=Decimal(0), minimum_ore=1000)
        self.assertEqual(debt_projection([asset])['months'], 10)
        asset.annual_rate = None
        self.assertIn('error', debt_projection([asset]))
