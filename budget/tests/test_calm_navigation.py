"""Navigation, switcher and access table of the Calm Ledger design must not widen anyone's access."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from budget.financial_areas import create_area
from budget.financial_models import FinancialAreaGrant
from budget.models import Membership
from budget.tests.test_domain import setup_family


class CalmNavigationTests(TestCase):
    def setUp(self):
        self.user, self.house, _ = setup_family('calm-owner@example.test')
        self.client = Client()
        self.client.force_login(self.user)
        self.area = self.user.test_area

    def get(self, path):
        return self.client.get(path, {'area': self.area.pk}).content.decode()

    def test_sidebar_is_grouped_and_dock_has_the_five_slots(self):
        html = self.get('/app/oversikt/')
        for title in ('>Daglig<', '>Planlegging<', '>Familie<'):
            self.assertIn(title, html)
        self.assertIn('Skann kvittering', html)
        self.assertIn('data-mobile-fab', html)
        self.assertIn('aria-label="Mobilmeny"', html)

    def test_member_without_documents_module_has_no_scan_link(self):
        user = get_user_model().objects.create_user(username='calm-member@example.test', email='calm-member@example.test')
        membership = Membership.objects.create(user=user, household=self.house, role='member', verified_at=timezone.now(),
                                               module_access={'documents': False})
        FinancialAreaGrant.objects.create(area=self.area, member=membership, role='editor')
        client = Client()
        client.force_login(user)
        html = client.get('/app/oversikt/', {'area': self.area.pk}).content.decode()
        self.assertNotIn('href="/app/dokumenter/', html)

    def test_access_table_never_lists_budgets_the_viewer_cannot_open(self):
        other = get_user_model().objects.create_user(username='calm-other@example.test', email='calm-other@example.test')
        other_member = Membership.objects.create(user=other, household=self.house, role='member', verified_at=timezone.now())
        create_area(other_member, 'Hemmelig budsjett', kind='personal')
        html = self.get('/app/familie/')
        self.assertIn('Budsjettilgang', html)
        self.assertNotIn('Hemmelig budsjett', html)

    def test_budget_switcher_still_marks_read_only_budgets(self):
        other = get_user_model().objects.create_user(username='calm-reader@example.test', email='calm-reader@example.test')
        other_member = Membership.objects.create(user=other, household=self.house, role='member', verified_at=timezone.now())
        shared = create_area(other_member, 'Innsynsbudsjett', reader_ids=[Membership.objects.get(user=self.user).pk], kind='personal')
        html = self.get('/app/oversikt/')
        self.assertIn('Innsynsbudsjett', html)
        self.assertIn('Kun innsyn', html)
        self.assertIn('class="fam-bar"', html)
        self.assertNotEqual(shared.pk, self.area.pk)
