from datetime import date
from html.parser import HTMLParser
from types import SimpleNamespace
from uuid import uuid4

from django.forms import ModelChoiceField
from django.forms.utils import ErrorDict
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from budget.forms import EntryForm
from budget.models import Entry, Household
from budget.templatetags.ui_tags import budget_distribution


class BudgetDistributionTests(SimpleTestCase):
    def test_parts_reconcile_without_recalculating_finances(self):
        result = budget_distribution(dict(ordinary=200, bills=100, savings=50, debt=25, funds=25, available=600))
        self.assertTrue(result['chartable'])
        self.assertEqual([part['amount'] for part in result['parts']], [200, 200, 600])
        self.assertEqual([part['weight'] for part in result['parts']], [200, 200, 600])
        self.assertEqual(result['total'], 1000)

    def test_negative_empty_and_unknown_values_are_not_charted(self):
        for values in [dict(ordinary=200, bills=0, savings=0, debt=0, funds=0, available=-100),
                       dict(ordinary=-200, bills=0, savings=0, debt=0, funds=0, available=300),
                       dict(ordinary=0, bills=0, savings=0, debt=0, funds=0, available=0),
                       dict(ordinary=100, available=100)]:
            with self.subTest(values=values):
                result = budget_distribution(values)
                self.assertFalse(result['chartable'])
                self.assertEqual(result['parts'][0]['amount'], values['ordinary'])
                self.assertEqual(result['parts'][2]['amount'], values['available'])
                self.assertEqual([part['weight'] for part in result['parts']], [0, 0, 0])


class FormMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = {}
        self.advanced_open = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and 'name' in attrs:
            self.inputs[attrs['name']] = attrs
        if tag == 'details' and attrs.get('class') == 'entry-form-advanced':
            self.advanced_open = 'open' in attrs


class EntryPresentationTests(SimpleTestCase):
    def make_form(self):
        house = Household(pk=uuid4())
        row = Entry(pk=uuid4(), household=house, kind='expense', description='Bevar redigert tekst',
                    amount_ore=12345, version=8, effective_date=date(2026, 10, 12),
                    currency='EUR', original_amount='12.34', exchange_rate='11.25',
                    income_attribution='Opprinnelig eier')
        row._state.adding = False
        form = EntryForm(household=house, instance=row, initial={'idempotency_key': uuid4()})
        for field in form.fields.values():
            if isinstance(field, ModelChoiceField):
                field.queryset = field.queryset.none()
        return form

    def test_hidden_identity_and_edit_values_survive_disclosure(self):
        form = self.make_form()
        html = render_to_string('budget/entry_form_refresh.html', {'form': form})
        markup = FormMarkup(html)
        self.assertEqual(markup.inputs['version']['type'], 'hidden')
        self.assertEqual(markup.inputs['version']['value'], '8')
        self.assertEqual(markup.inputs['idempotency_key']['type'], 'hidden')
        self.assertEqual(markup.inputs['idempotency_key']['value'], str(form['idempotency_key'].value()))
        self.assertEqual(markup.inputs['description']['value'], 'Bevar redigert tekst')
        self.assertEqual(markup.inputs['effective_date']['value'], '2026-10-12')
        self.assertEqual(markup.inputs['currency']['value'], 'EUR')
        self.assertEqual(markup.inputs['income_attribution']['value'], 'Opprinnelig eier')
        self.assertIn(markup.inputs['amount']['value'], ('123,45', '123.45'))
        self.assertFalse(markup.advanced_open)
        self.assertEqual(set(markup.inputs) | {'kind', 'category', 'asset', 'original'}, set(form.fields))

    def test_advanced_errors_open_details_and_remain_visible(self):
        form = self.make_form()
        form._errors = ErrorDict()
        form.cleaned_data = {}
        form.add_error('currency', 'Kontroller valutakoden')
        html = render_to_string('budget/entry_form_refresh.html', {'form': form})
        self.assertTrue(FormMarkup(html).advanced_open)
        self.assertIn('Kontroller valutakoden', html)
        self.assertEqual(FormMarkup(html).inputs['currency']['value'], 'EUR')


class OverviewPresentationTests(SimpleTestCase):
    def context(self, savings=True):
        today = date(2026, 10, 21)
        return {'totals': dict(ordinary=200, bills=100, savings=50, debt=25, funds=25, available=600,
                               income=1000, expected=100, released=0, daily=None, gross_deposits=50, planned_savings=50),
                'household': SimpleNamespace(modules={'savings_dashboard': savings}),
                'member': SimpleNamespace(role='admin', module_access={}), 'page': 'oversikt', 'today': today,
                'request': SimpleNamespace(financial_area=SimpleNamespace(name='Testbudsjett', modules={'savings_dashboard': savings}), financial_can_write=True),
                'bills': [SimpleNamespace(name=f'Regning {i}', due_date=today, payment=None,
                                         amount_ore=100, accounting_class='ordinary', pk=uuid4()) for i in range(5)],
                'assets': [{'row': SimpleNamespace(kind='debt', name='Ikke et sparemål')}],
                'month': today}

    def test_attention_is_bounded_and_precedes_totals_in_reading_order(self):
        html = render_to_string('budget/overview_refresh.html', self.context())
        self.assertEqual(html.count('class="row bill-row"'), 3)
        self.assertIn('Se alle regninger', html)
        self.assertIn('/app/regninger/?month=2026-10', html)
        self.assertNotIn('Regning 3', html)
        self.assertIn('Ingen sparemål ennå.', html)
        self.assertNotIn('Ikke et sparemål', html)
        self.assertLess(html.index('overview-priorities'), html.index('dashboard-stats'))

    def test_disabled_savings_omits_complete_overview_panel(self):
        html = render_to_string('budget/overview_refresh.html', self.context(savings=False))
        self.assertNotIn('<h2>Sparemål</h2>', html)
        self.assertNotIn('Planer for fremtiden', html)
        self.assertNotIn('>Se sparing</a>', html)


@override_settings(DEBUG=False)
class UiAssetTests(SimpleTestCase):
    def test_disclosure_script_is_public_and_in_shell(self):
        response = self.client.get('/static/budget/ui-refresh.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        response.close()
        html = render_to_string('budget/base.html')
        self.assertIn('/static/budget/ui-refresh.js', html)
