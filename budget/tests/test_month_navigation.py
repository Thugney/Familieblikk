from datetime import date
from django.test import TestCase
from django.utils import timezone
from budget.models import Membership
from budget.tests.test_domain import setup_family


class MonthNavigationTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('month-navigation@example.test')
        self.client.force_login(self.user)

    def test_missing_empty_and_whitespace_month_use_current_oslo_month(self):
        expected = timezone.localdate().replace(day=1)
        for query in [{}, {'month': ''}, {'month': '   '}, {'month': '\t\n'}]:
            with self.subTest(query=query):
                response = self.client.get('/app/oversikt/', query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['month'], expected)

    def test_valid_archived_month_preserved_and_invalid_nonempty_rejected(self):
        response = self.client.get('/app/oversikt/', {'month': '2026-09'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['month'], date(2026, 9, 1))
        self.assertContains(response, 'value="2026-09"')
        self.assertContains(response, 'href="/app/oversikt/?month=2026-09"')
        for value in ['invalid', '2026-13', '2026-09garbage', '2026-09-01']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get('/app/oversikt/', {'month': value}).status_code, 404)

    def test_subpage_navigation_and_selector_never_have_empty_month(self):
        member = Membership.objects.get(user=self.user)
        member.identity_method = 'preregistered_admin'
        member.save(update_fields=['identity_method'])
        current = timezone.localdate().strftime('%Y-%m')
        overview = f'/app/oversikt/?month={current}'
        for path in ['/registrer/medlem/', f'/endre/category/{self.category.pk}/', '/ny/entry/', '/passord/endre/']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'href="{overview}"')
                self.assertContains(response, f'id="month" name="month" type="month" value="{current}"')
                self.assertNotContains(response, '?month="')
                self.assertEqual(self.client.get(overview).status_code, 200)
