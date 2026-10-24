"""UI-ressurser må også virke uten Djangos utviklingsserver."""
from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class UiAssetTests(SimpleTestCase):
    def test_stylesheet_and_bundled_font_are_public_in_production(self):
        for name, mime, signature in (
            ('ui-refresh.css', 'text/css', b'@font-face'),
            ('calm.css', 'text/css', b'Calm Ledger'),
            ('ui-refresh.js', 'application/javascript', b'entry-form-advanced'),
            ('figtree-latin.woff2', 'font/woff2', b'wOF2'),
        ):
            with self.subTest(asset=name):
                response = self.client.get('/static/budget/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], mime)
                body = b''.join(response.streaming_content)
                self.assertIn(signature, body)
                self.assertIn('must-revalidate', response['Cache-Control'])
