"""Debt-bill links and visible balances use the existing repayment accounting."""
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from budget import services
from budget.models import Asset, BillOccurrence, BillTemplate, Entry, FinancialAreaGrant, Membership, MonthPlan
from budget.tests.financial_support import enter_fixture_area
from budget.tests.test_domain import setup_family


@override_settings(ALLOWED_HOSTS=['testserver'])
class DebtPaymentLinkTests(TestCase):
    def setUp(self):
        self.user, self.house, self.category = setup_family('debt-link@example.test')
        enter_fixture_area(self, self.user)
        self.today = timezone.localdate()
        self.month = services.month_start(self.today)
        self.key = self.month.strftime('%Y-%m')
        self.debt = Asset.objects.create(household=self.house, created_by=self.user,
            kind='debt', name='Synthetic family loan', opening_date=self.month,
            opening_ore=100000, annual_rate=0, minimum_ore=10000)
        MonthPlan.objects.create(household=self.house, created_by=self.user,
            asset=self.debt, month=self.month, amount_ore=30000)
        template = BillTemplate.objects.create(household=self.house, created_by=self.user,
            name='Synthetic loan payment', amount_ore=25000, first_due=self.today,
            monthly=False, accounting_class='debt', asset=self.debt)
        services.materialize_template(template, self.month)
        self.bill = BillOccurrence.objects.get(template=template)
        self.client.force_login(self.user)

    def pay(self):
        self.payment_payload = {'version': self.bill.version, 'date': self.today.isoformat(),
                                'key': str(uuid.uuid4())}
        response = self.client.post(f'/betal/{self.bill.pk}/?month={self.key}', self.payment_payload)
        self.assertEqual(response.status_code, 302)
        return Entry.objects.get(occurrence=self.bill, active=True)

    def test_bill_payment_links_to_original_debt_and_updates_estimate_and_strategy(self):
        editor = get_user_model().objects.create_user(username='debt-link-spouse')
        member = Membership.objects.create(user=editor, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=member, role='editor')
        self.client.force_login(editor)
        before = self.client.get(f'/app/gjeld/?month={self.key}')
        self.assertEqual(before.context['projection']['months'], 10)
        payment = self.pay()
        self.assertEqual(payment.created_by_id, editor.pk)
        repeated = self.client.post(f'/betal/{self.bill.pk}/?month={self.key}', self.payment_payload)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(Entry.objects.filter(occurrence=self.bill).count(), 1)
        self.debt.refresh_from_db()
        self.assertEqual((payment.kind, payment.asset_id), ('debt', self.debt.pk))
        self.assertEqual(self.debt.opening_ore, 100000)
        self.assertEqual(Asset.objects.filter(kind='debt').count(), 1)
        totals = services.calculate(self.house, self.month)
        self.assertEqual((totals['ordinary'], totals['bills'], totals['debt'], totals['cash']),
                         (0, 0, 30000, -25000))
        response = self.client.get(f'/app/regninger/?month={self.key}')
        self.assertContains(response, f'href="/app/gjeld/?month={self.key}&amp;area={self.area.pk}#debt-{self.debt.pk}"')
        self.assertContains(response, f'>{self.debt.name}</a>')
        response = self.client.get(f'/app/gjeld/?month={self.key}')
        card = response.context['assets'][0]
        self.assertEqual((card['row'].pk, card['balance'], card['debt_estimate'], card['paid']),
                         (self.debt.pk, 100000, 75000, 25000))
        self.assertEqual(response.context['projection']['months'], 8)
        self.assertContains(response, f'id="debt-{self.debt.pk}"')
        self.assertContains(response, f'Anslått restgjeld per {self.today:%d.%m.%Y}')
        self.assertContains(response, '750,00 kr')
        self.assertContains(response, 'Referansesaldo')

    def test_actual_refund_restores_linked_debt_estimate_without_duplicate_expense(self):
        payment = self.pay()
        refund = services.save_entry(self.user, Entry(kind='refund', original=payment,
            amount_ore=5000, effective_date=self.today, description='Synthetic repayment refund'))
        self.assertEqual(refund.asset_id, self.debt.pk)
        self.assertEqual(services.estimated_debt_balance(self.debt, self.today), 80000)
        totals = services.calculate(self.house, self.month)
        self.assertEqual((totals['ordinary'], totals['bills'], totals['debt'], totals['cash']),
                         (0, 0, 30000, -20000))
        response = self.client.get(f'/app/gjeld/?month={self.key}')
        self.assertEqual(response.context['assets'][0]['debt_estimate'], 80000)
        self.assertContains(response, '800,00 kr')

    def test_estimate_is_not_calculated_or_exposed_without_bill_access(self):
        self.pay()
        user = get_user_model().objects.create_user(username='debt-link-restricted')
        member = Membership.objects.create(user=user, household=self.house, role='member',
                                           module_access={'bills': False})
        FinancialAreaGrant.objects.create(area=self.area, member=member, role='reader')
        self.client.force_login(user)
        with patch('budget.services.estimated_debt_balance', return_value=876543219) as estimate:
            response = self.client.get(f'/app/gjeld/?month={self.key}')
        self.assertEqual(response.status_code, 200)
        estimate.assert_not_called()
        self.assertIsNone(response.context['assets'][0]['debt_estimate'])
        self.assertEqual(response.context['assets'][0]['paid'], 0)
        self.assertContains(response, 'Krever regningstilgang')
        self.assertContains(response, 'Nedbetalingsanslag krever også regningstilgang')
        self.assertNotContains(response, '8\u00a0765\u00a0432,19')
        self.assertNotContains(response, '750,00 kr')

    def test_missing_rate_keeps_estimate_unknown_and_reference_intact(self):
        self.debt.annual_rate = None
        self.debt.save()
        response = self.client.get(f'/app/gjeld/?month={self.key}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['assets'][0]['balance'], 100000)
        self.assertIsNone(response.context['assets'][0]['debt_estimate'])
        self.assertContains(response, 'Ukjent – mangler rente eller gyldig saldodato')
