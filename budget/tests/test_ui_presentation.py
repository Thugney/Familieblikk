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
        bills = [SimpleNamespace(name=f'Regning {i}', due_date=today, payment=None,
                                 amount_ore=100, accounting_class='ordinary', pk=uuid4()) for i in range(5)]
        return {'totals': dict(ordinary=200, bills=100, savings=50, debt=25, funds=25, available=600,
                               income=1000, expected=100, released=0, daily=None, gross_deposits=50, planned_savings=50),
                'household': SimpleNamespace(modules={'savings_dashboard': savings}),
                'member': SimpleNamespace(role='admin', module_access={}), 'page': 'oversikt', 'today': today,
                'request': SimpleNamespace(financial_area=SimpleNamespace(name='Testbudsjett', modules={'savings_dashboard': savings}), financial_can_write=True),
                'bills': bills,
                'overview_filter': 'alle', 'overview_bills': bills[:3], 'overview_entries': [],
                'assets': [{'row': SimpleNamespace(kind='debt', name='Ikke et sparemål')}],
                'month': today,
                'weekly_total': 0, 'weekly_bars': [], 'pace': None,
                'categories': [], 'category_count_total': 0, 'chart': []}

    def test_attention_is_bounded_and_analytics_precede_priorities(self):
        html = render_to_string('budget/overview_refresh.html', self.context())
        self.assertEqual(html.count('class="row bill-row"'), 3)
        self.assertIn('Se alle regninger', html)
        self.assertIn('/app/regninger/?month=2026-10', html)
        self.assertNotIn('Regning 3', html)
        self.assertIn('Ingen sparemål ennå.', html)
        self.assertNotIn('Ikke et sparemål', html)
        self.assertIn('class="bento-grid"', html)
        self.assertLess(html.index('bento-grid'), html.index('overview-priorities'))

    def test_disabled_savings_omits_complete_overview_panel(self):
        html = render_to_string('budget/overview_refresh.html', self.context(savings=False))
        self.assertNotIn('<h2>Sparemål</h2>', html)
        self.assertNotIn('Planer for fremtiden', html)
        self.assertNotIn('>Se sparing</a>', html)

    def test_hero_distribution_toggle_and_camera_scan_shortcuts(self):
        from budget.views import NAV
        ctx = self.context()
        ctx['nav'] = NAV
        ctx['title'] = 'Oversikt'
        ctx['household'].name = 'Testfamilien'
        ctx['member'] = SimpleNamespace(
            pk=uuid4(), role='member', module_access={'calendar': False},
            household=ctx['household'], get_role_display='Medlem'
        )
        ctx['request'].user = SimpleNamespace(
            is_authenticated=False, email='owner@example.test', get_full_name=lambda: 'Marte'
        )
        ctx['request'].GET = {}
        ctx['request']._accessible_financial_areas = [
            {'pk': uuid4(), 'name': 'Felles budsjett', 'kind': 'shared', 'kind_label': 'Felles',
             'can_write': True, 'is_current': True, 'open_url': '/app/oversikt/?area=1', 'dot_color': '#34D399'},
            {'pk': uuid4(), 'name': 'Jonas', 'kind': 'personal', 'kind_label': 'Personlig',
             'can_write': False, 'is_current': False, 'open_url': '/app/oversikt/?area=2', 'dot_color': '#60A5FA'},
        ]
        overview_html = render_to_string('budget/page.html', {**ctx, 'page': 'oversikt'})
        self.assertIn('data-hero-distribution', overview_html)
        self.assertIn('data-hero-mode="bar"', overview_html)
        self.assertIn('data-hero-mode="breakdown"', overview_html)
        self.assertIn('class="fam-bar"', overview_html)
        self.assertIn('Felles budsjett', overview_html)
        self.assertIn('Kun innsyn', overview_html)
        self.assertIn('href="/app/handlelister/?month=2026-10"', overview_html)
        self.assertNotIn('href="/app/dokumenter/?month=2026-10"', overview_html)
        self.assertIn('data-mobile-quick-actions', overview_html)
        self.assertIn('data-mobile-fab', overview_html)
        self.assertIn('Utgift / ny post', overview_html)
        self.assertIn('Handleliste', overview_html)

        mer_html = render_to_string('budget/page.html', {**ctx, 'page': 'mer', 'title': 'Mer'})
        self.assertIn('href="/app/mer/?month=2026-10" aria-current="page"', mer_html)
        self.assertNotIn('href="/app/regninger/?month=2026-10" aria-current="page"', mer_html)

        bills_html = render_to_string('budget/page.html', {**ctx, 'page': 'regninger', 'title': 'Regninger'})
        self.assertIn('href="/app/regninger/?month=2026-10" aria-current="page"', bills_html)
        self.assertNotIn('href="/app/mer/?month=2026-10" aria-current="page"', bills_html)

        shop_html = render_to_string('budget/base.html', {**ctx, 'page': 'handlelister', 'title': 'Handlelister'})
        self.assertIn('href="/app/handlelister/?month=2026-10" aria-current="page"', shop_html)
        self.assertNotIn('href="/app/mer/?month=2026-10" aria-current="page"', shop_html)

        house = Household(pk=uuid4())
        entry_form = EntryForm(household=house, initial={'idempotency_key': uuid4()})
        for field in entry_form.fields.values():
            if isinstance(field, ModelChoiceField):
                field.queryset = field.queryset.none()
        create_html = render_to_string('budget/form.html', {**ctx, 'form': entry_form, 'title': 'Ny registrering'})
        self.assertIn('data-capture-mode="manual"', create_html)
        self.assertIn('data-capture-mode="camera"', create_html)
        self.assertIn('id="camera-scan-form"', create_html)


@override_settings(DEBUG=False)
class UiAssetTests(SimpleTestCase):
    def test_disclosure_script_is_public_and_in_shell(self):
        response = self.client.get('/static/budget/ui-refresh.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        response.close()
        html = render_to_string('budget/base.html')
        self.assertIn('/static/budget/ui-refresh.js', html)
