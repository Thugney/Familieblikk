"""Follow rendered URLs with a real Client, without implicit area injection."""
import uuid
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from budget import services, correction_services as corrections
from budget.financial_areas import area_scope, create_area
from budget.financial_models import FinancialAreaGrant
from budget.models import (Asset, BillOccurrence, BillTemplate, Category, Document, Entry,
                           Membership, ShoppingList, ShoppingTrip)
from budget.tests.test_domain import setup_family


class Links(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.urls = []
        self.feed(content.decode())

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(value for key, value in attrs if key == 'href')


class EntryLinkTests(TestCase):
    def setUp(self):
        self.owner, self.house, self.category = setup_family('entry-owner@example.test')
        self.area = self.owner.test_area
        self.member = Membership.objects.get(user=self.owner)
        self.other, self.other_house, _ = setup_family('entry-other@example.test')
        self.reader = get_user_model().objects.create_user('entry-reader', email='reader@example.test')
        self.reader_member = Membership.objects.create(user=self.reader, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=self.reader_member, role='reader')
        self.editor = get_user_model().objects.create_user('entry-editor', email='editor@example.test')
        editor_member = Membership.objects.create(user=self.editor, household=self.house, role='member')
        FinancialAreaGrant.objects.create(area=self.area, member=editor_member, role='editor')
        self.second_area = create_area(self.member, 'Another budget')
        self.day = date(2026, 9, 8)
        with area_scope(self.member, self.area.pk):
            self.expense = self.entry('expense', 'Exact expense')
            self.refund = self.entry('refund', 'Returned purchase', original=self.expense, active=False)
            template = BillTemplate.objects.create(household=self.house, created_by=self.owner,
                name='Exact bill', amount_ore=10000, category=self.category, first_due=self.day, monthly=False)
            services.materialize_template(template, self.day.replace(day=1))
            self.bill = BillOccurrence.objects.get(template=template)
            self.payment = services.pay_bill(self.owner, self.bill.pk, self.day, uuid.uuid4(), self.bill.version)
            self.asset_entries = []
            for kind, entry_kind in [('savings', 'deposit'), ('debt', 'debt'), ('fund', 'fund'), ('recipient', 'remittance')]:
                asset = Asset.objects.create(household=self.house, created_by=self.owner, kind=kind,
                    name='Exact ' + kind, opening_date=self.day, opening_ore=20000, archived=True)
                self.asset_entries.append(self.entry(entry_kind, 'Activity ' + kind, asset=asset))
            self.listing = ShoppingList.objects.create(household=self.house, created_by=self.owner, name='Shared list')
            self.scan = Document.objects.create(household=self.house, created_by=self.owner,
                transient=True, confirmed=True, supplier='Exact scan', amount_ore=10000,
                document_date=self.day, size=0, storage_key='synthetic-entry-link', entry=self.expense)
            self.trip = ShoppingTrip.objects.create(household=self.house, created_by=self.owner,
                shopping_list=self.listing, entry=self.expense, receipt=self.scan, store='Exact trip')
        self.client = Client()
        self.client.force_login(self.owner)

    def entry(self, kind, description, **extra):
        return Entry.objects.create(household=self.house, created_by=self.owner,
            kind=kind, description=description, amount_ore=1000,
            effective_date=self.day, category=self.category, **extra)

    def explicit(self, route, args=(), month='2026-09'):
        return reverse(route, args=args) + f'?area={self.area.pk}&month={month}'

    def find(self, response, path):
        found = [url for url in Links(response.content).urls if urlsplit(url).path == path]
        self.assertTrue(found, path)
        return found[0]

    def follow(self, response, route, args=(), month='2026-09', anchor=None):
        path = reverse(route, args=args)
        if anchor:
            found = [url for url in Links(response.content).urls if urlsplit(url).path == path and urlsplit(url).fragment == anchor]
            self.assertTrue(found, (path, anchor))
            url = found[0]
        else:
            url = self.find(response, path)
        parts = urlsplit(url)
        self.assertEqual(parse_qs(parts.query)['area'], [str(self.area.pk)])
        self.assertEqual(parse_qs(parts.query)['month'], [month])
        target = self.client.get(url)
        self.assertEqual(target.status_code, 200, url)
        if anchor:
            self.assertEqual(parts.fragment, anchor)
            self.assertContains(target, f'id="{anchor}"')
        return target

    def test_generated_list_and_spending_links_open_exact_readable_record_for_owner_and_reader(self):
        for actor in (self.owner, self.editor, self.reader):
            self.client.force_login(actor)
            listing = self.client.get(self.explicit('page', ['poster']))
            target = self.follow(listing, 'correction_history', ['entry', self.expense.pk])
            self.assertContains(target, 'Exact expense')
            self.assertContains(target, '08.09.2026')
            data = self.client.get(self.explicit('spending_data')).json()
            row = next(item for item in data['entries'] if item['id'] == str(self.expense.pk))
            self.assertEqual(self.client.get(row['detail_url']).status_code, 200)
            self.assertEqual(urlsplit(row['detail_url']).path, reverse('correction_history', args=['entry', self.expense.pk]))
            self.assertEqual(parse_qs(urlsplit(row['detail_url']).query), {'area': [str(self.area.pk)], 'month': ['2026-09']})
            if actor == self.reader:
                for url in Links(target.content).urls:
                    self.assertFalse(urlsplit(url).path.startswith(('/endre/', '/retting/', '/slett/')), url)
                self.assertEqual(self.client.get(self.explicit('edit', ['entry', self.expense.pk])).status_code, 403)

    def test_payment_links_to_bill_and_back_without_invalid_edit_action(self):
        page = self.client.get(self.explicit('correction_history', ['entry', self.payment.pk]))
        self.assertNotContains(page, reverse('edit', args=['entry', self.payment.pk]))
        bill = self.follow(page, 'correction_history', ['bill', self.bill.pk])
        self.assertContains(bill, 'Exact bill')
        payment = self.follow(bill, 'correction_history', ['entry', self.payment.pk])
        self.assertContains(payment, 'Angre feilregistrert betaling')
        self.follow(bill, 'correction_history', ['series', self.bill.template_id])
        self.client.force_login(self.reader)
        readonly = self.client.get(self.explicit('correction_history', ['entry', self.payment.pk]))
        self.assertNotContains(readonly, reverse('correction', args=['entry', self.payment.pk]))
        self.follow(readonly, 'correction_history', ['bill', self.bill.pk])

    def test_later_bill_opens_series_in_the_bills_month(self):
        with area_scope(self.member, self.area.pk):
            template = self.bill.template
            template.monthly = True
            template.save()
            services.materialize_template(template, date(2026, 10, 1))
            later = BillOccurrence.objects.get(template=template, due_date__month=10)
        detail = self.client.get(self.explicit('correction_history', ['bill', later.pk], month='2026-10'))
        series = self.follow(detail, 'correction_history', ['series', template.pk], month='2026-10')
        self.assertContains(series, '01.10.2026')

    def test_refund_and_original_link_each_way_with_undone_status(self):
        page = self.client.get(self.explicit('correction_history', ['entry', self.expense.pk]))
        refund = self.follow(page, 'correction_history', ['entry', self.refund.pk])
        self.assertContains(refund, 'Penger tilbake')
        self.assertContains(refund, 'Angret – teller ikke i budsjettet')
        self.assertNotContains(refund, reverse('edit', args=['entry', self.refund.pk]))
        self.follow(refund, 'correction_history', ['entry', self.expense.pk])

    def test_actual_asset_links_preserve_record_month_and_anchors_for_reader(self):
        self.client.force_login(self.reader)
        for entry in self.asset_entries:
            detail = self.client.get(self.explicit('correction_history', ['entry', entry.pk], month='2026-10'))
            page = {'deposit': 'sparing', 'debt': 'gjeld', 'fund': 'arsutgifter', 'remittance': 'utland'}[entry.kind]
            anchor = ('debt-' if entry.kind == 'debt' else 'asset-') + str(entry.asset_id)
            target = self.follow(detail, 'page', [page], anchor=anchor)
            self.assertNotContains(target, reverse('edit', args=['asset', entry.asset_id]))

    def test_trip_anchor_scan_and_backlinks_are_exact_and_permission_filtered(self):
        detail = self.client.get(self.explicit('correction_history', ['entry', self.expense.pk]))
        trip = self.follow(detail, 'shopping_detail', [self.listing.pk], anchor='trip-' + str(self.trip.pk))
        self.follow(trip, 'correction_history', ['entry', self.expense.pk])
        self.follow(detail, 'document_detail', [self.scan.pk])
        self.client.force_login(self.reader)
        readonly = self.client.get(self.explicit('correction_history', ['entry', self.expense.pk]))
        self.follow(readonly, 'document_detail', [self.scan.pk])
        self.follow(readonly, 'shopping_detail', [self.listing.pk], anchor='trip-' + str(self.trip.pk))
        self.reader_member.module_access = {'documents': False, 'shopping': False}
        self.reader_member.save()
        self.client.force_login(self.reader)
        restricted = self.client.get(self.explicit('correction_history', ['entry', self.expense.pk]))
        self.assertEqual(restricted.status_code, 200)
        self.assertNotContains(restricted, 'Exact scan')
        self.assertNotContains(restricted, 'Exact trip')
        self.assertEqual(self.client.get(self.explicit('shopping_detail', [self.listing.pk])).status_code, 403)
        self.assertIn(self.client.get(self.explicit('document_detail', [self.scan.pk])).status_code, (403, 404))

    def test_tampered_area_foreign_family_and_shared_list_never_grant_financial_access(self):
        detail = self.client.get(self.explicit('page', ['poster']))
        url = self.find(detail, reverse('correction_history', args=['entry', self.expense.pk]))
        changed = url.replace(str(self.area.pk), str(self.second_area.pk))
        self.assertIn(self.client.get(changed).status_code, (403, 404))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertIn(self.client.get(url.replace(str(self.area.pk), str(self.other.test_area.pk))).status_code, (403, 404))
        self.client.force_login(self.reader)
        FinancialAreaGrant.objects.filter(area=self.area, member=self.reader_member).delete()
        self.assertEqual(self.client.get(url).status_code, 403)
        shared = self.client.get(reverse('shopping_detail', args=[self.listing.pk]))
        self.assertEqual(shared.status_code, 200)
        self.assertNotContains(shared, reverse('correction_history', args=['entry', self.expense.pk]))
        self.assertNotContains(shared, reverse('document_detail', args=[self.scan.pk]))

    def test_forms_use_readable_labels_and_unchanged_values(self):
        bill = self.client.get(self.explicit('create', ['bill']))
        self.assertContains(bill, 'Hva gjelder regningen?')
        self.assertContains(bill, 'value="ordinary"')
        self.assertContains(bill, 'value="fund"')
        entry = self.client.get(self.explicit('create', ['entry']))
        self.assertContains(entry, 'Penger tilbake')
        self.assertContains(entry, 'value="refund"')

    def test_series_summary_resolves_selected_date_before_future_revision_archive_and_resume(self):
        with patch('budget.correction_services.timezone.localdate', return_value=date(2026, 9, 9)):
            with area_scope(self.member, self.area.pk):
                category = Category.objects.create(household=self.house, created_by=self.owner, name='Later category')
                template = BillTemplate.objects.create(household=self.house, created_by=self.owner,
                    name='Original series', amount_ore=12000, category=self.category, first_due=self.day, monthly=True)
                for operation, start, changes in [
                    ('revise', date(2026, 10, 15), {'name': 'Later series', 'amount_ore': 45000, 'category_id': str(category.pk)}),
                    ('archive', date(2026, 11, 1), {}),
                    ('resume', date(2026, 12, 1), {}),
                ]:
                    template = corrections.revise_series(self.owner, template.pk, operation,
                        template.version, uuid.uuid4(), start, changes, [])
            for actor in (self.owner, self.reader):
                self.client.force_login(actor)
                for month, name, amount, expected_category, enabled in [
                    ('2026-09', 'Original series', 12000, self.category, True),
                    ('2026-10', 'Original series', 12000, self.category, True),
                    ('2026-11', 'Later series', 45000, category, False),
                    ('2026-12', 'Later series', 45000, category, True),
                ]:
                    response = self.client.get(self.explicit('correction_history', ['series', template.pk], month=month))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f'<h2>{name}</h2>', html=True)
                    summary = response.context['series_summary']
                    self.assertEqual(summary['amount_ore'], amount)
                    self.assertEqual(summary['category'], expected_category)
                    self.assertEqual(summary['enabled'], enabled)
                    self.assertEqual(summary['as_of'], date.fromisoformat(month + '-01'))
                    html = response.content.decode().split('<dl id="activity-summary">', 1)[1].split('</dl>', 1)[0]
                    self.assertIn('Oppsett per', html)
                    self.assertNotIn('Forfallsdato', html)
                    self.assertIn(('Aktiv' if enabled else 'Stoppet') + ' per 01.' + month[5:] + '.2026', html)
                    self.assertContains(response, 'Tilbake til regninger for')
                    back = self.find(response, reverse('page', args=['regninger']))
                    self.assertEqual(parse_qs(urlsplit(back).query), {'month': [month], 'area': [str(self.area.pk)]})
                self.assertEqual(self.client.get(self.explicit('correction_history', ['series', template.pk], month='invalid')).status_code, 404)

    def test_income_details_distinguish_attribution_from_creator(self):
        with area_scope(self.member, self.area.pk):
            income = self.entry('income', 'Attributed income', income_attribution='Synthetic income owner')
            unspecified = self.entry('income', 'Unspecified income')
        for actor in (self.owner, self.reader):
            self.client.force_login(actor)
            response = self.client.get(self.explicit('correction_history', ['entry', income.pk]))
            self.assertContains(response, '<dt>Inntekten tilhører</dt><dd>Synthetic income owner</dd>', html=True)
            self.assertContains(response, f'<dt>Registrert av</dt><dd>{self.owner.email}</dd>', html=True)
            response = self.client.get(self.explicit('correction_history', ['entry', unspecified.pk]))
            self.assertContains(response, '<dt>Inntekten tilhører</dt><dd>Ikke oppgitt</dd>', html=True)

    def test_payment_opens_bill_only_scan_for_owner_reader_and_filters_revoked_modules(self):
        with area_scope(self.member, self.area.pk):
            scan = Document.objects.create(household=self.house, created_by=self.owner,
                transient=True, confirmed=True, supplier='Bill-only scan', amount_ore=10000,
                document_date=self.day, size=0, storage_key='synthetic-bill-only-link', bill=self.bill)
        self.assertIsNone(scan.entry_id)
        for actor in (self.owner, self.reader):
            self.client.force_login(actor)
            payment = self.client.get(self.explicit('correction_history', ['entry', self.payment.pk]))
            document = self.follow(payment, 'document_detail', [scan.pk])
            self.assertContains(document, 'Bill-only scan')
            bill = self.follow(document, 'correction_history', ['bill', self.bill.pk])
            self.assertContains(bill, 'Tilbake til regninger for')
            self.follow(bill, 'page', ['regninger'])
        self.reader_member.module_access = {'documents': False}
        self.reader_member.save()
        payment = self.client.get(self.explicit('correction_history', ['entry', self.payment.pk]))
        self.assertEqual(payment.status_code, 200)
        self.assertNotContains(payment, 'Bill-only scan')
        self.assertIn(self.client.get(self.explicit('document_detail', [scan.pk])).status_code, (403, 404))
        self.reader_member.module_access = {'bills': False}
        self.reader_member.save()
        self.assertEqual(self.client.get(self.explicit('correction_history', ['entry', self.payment.pk])).status_code, 403)
        self.assertIn(self.client.get(self.explicit('document_detail', [scan.pk])).status_code, (403, 404))
