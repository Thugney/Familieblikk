"""Module grants never replace tenant/owner checks or authoritative accounting."""
import json
import threading
import uuid
from itertools import product
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from budget import access, calendar_services as cal, push_services as push, services, forms
from budget.models import (Asset, Audit, BillOccurrence, BillTemplate, CalendarEvent, CalendarException,
                           CalendarNotification, CalendarResponse, Category, Entry, Household, Membership,
                           MonthPlan, FundTopUp, PushDelivery, PushSubscription)
from budget.spending_services import spending, planning


def family_fixture(owner):
    owner.house = Household.objects.create(name='Tilgangsfamilie', modules={'debt': True, 'fund': True, 'remittance': True})
    owner.foreign_house = Household.objects.create(name='Separat familie')
    owner.admin = get_user_model().objects.create_user(username='access-admin', email='admin@example.test')
    owner.user = get_user_model().objects.create_user(username='access-member', email='member@example.test')
    owner.peer = get_user_model().objects.create_user(username='access-peer', email='peer@example.test')
    owner.foreign = get_user_model().objects.create_user(username='access-foreign')
    owner.admin_member = Membership.objects.create(household=owner.house, user=owner.admin, role='admin')
    owner.member = Membership.objects.create(household=owner.house, user=owner.user, role='member')
    owner.peer_member = Membership.objects.create(household=owner.house, user=owner.peer, role='member')
    owner.foreign_member = Membership.objects.create(household=owner.foreign_house, user=owner.foreign, role='admin')


class MemberAccessTests(TestCase):
    def setUp(self):
        family_fixture(self)
        self.day = timezone.localdate()
        self.month = self.day.replace(day=1)
        self.category = Category.objects.create(household=self.house, created_by=self.admin, name='Dagligvarer')
        self.assets = {kind: Asset.objects.create(household=self.house, created_by=self.admin, kind=kind,
                                                name='Privat '+kind, opening_date=self.month, opening_ore=100000,
                                                annual_rate=0) for kind in access.ASSETS}
        self.client.force_login(self.user)

    def revoke(self, *modules):
        self.member.refresh_from_db()
        self.member = access.update_member_access(self.admin, self.member.pk, {m: False for m in modules}, self.member.access_version)

    def entry(self, kind='expense', **kwargs):
        defaults = dict(household=self.house, created_by=self.user, kind=kind, amount_ore=12345,
                        effective_date=self.day, description='Synlig vanlig post', category=self.category)
        defaults.update(kwargs)
        return Entry.objects.create(**defaults)

    def bill(self, kind='ordinary'):
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Hemmelig regning',
                                              amount_ore=21300, first_due=self.day, monthly=False,
                                              accounting_class=kind, category=self.category if kind == 'ordinary' else None,
                                              asset=self.assets[kind] if kind in ('debt', 'fund') else None)
        return BillOccurrence.objects.create(household=self.house, created_by=self.user, template=template,
                                             name=template.name, amount_ore=template.amount_ore, due_date=self.day,
                                             accounting_class=kind, category=template.category, asset=template.asset)

    def payload(self, **changes):
        return dict(title='Privat kalenderavtale', start=self.day.isoformat(), end=self.day.isoformat(),
                    all_day=True, start_time=None, end_time=None, place='', note='', scope='shared',
                    participants=[], recurrence='none', until=None, fold=None, **changes)

    def test_legacy_and_new_members_keep_all_access_admin_cannot_be_limited(self):
        self.assertEqual(self.member.module_access, {})
        self.assertTrue(all(access.allows(self.member, m) for m in access.MODULES))
        Membership.objects.filter(pk=self.admin_member.pk).update(module_access={m: False for m in access.MODULES})
        self.admin_member.refresh_from_db()
        self.assertTrue(all(access.allows(self.admin_member, m) for m in access.MODULES))
        with self.assertRaises(PermissionDenied):
            access.update_member_access(self.admin, self.admin_member.pk, {}, 1)

    def test_lazy_selection_rechecks_reclassified_rows_and_relations_in_sql(self):
        original = self.entry()
        self.revoke('debt')
        # Construct before the supported reclassification; no rows are read.
        with self.assertNumQueries(0):
            rows = access.safe_rows(self.member, Entry.objects.all())
        original.kind, original.asset = 'debt', self.assets['debt']
        services.save_entry(self.admin, original, original.version)
        with self.assertNumQueries(1):
            self.assertEqual(list(rows.values_list('pk', flat=True)), [])
        refund = self.entry('refund', original=original, asset=self.assets['debt'])
        self.assertNotIn(refund.pk, access.safe_rows(self.member, Entry.objects.all()).values_list('pk', flat=True))
        self.assertNotIn(refund.pk, access.safe_rows(self.member, Entry.objects.filter(pk=refund.pk)).values_list('pk', flat=True))

    def test_sql_policy_matches_object_classification_for_every_financial_module_combination(self):
        entries, bills, templates, topups, plans = [], [], [], [], []
        for kind in access.KINDS:
            asset_kind = {'deposit': 'savings', 'withdrawal': 'savings', 'debt': 'debt', 'fund': 'fund', 'remittance': 'recipient'}.get(kind)
            entries.append(self.entry(kind, asset=self.assets.get(asset_kind)))
        for kind in ('ordinary', 'debt', 'fund'):
            bill = self.bill(kind); bills.append(bill); templates.append(bill.template)
            payment = self.entry({'ordinary': 'expense', 'debt': 'debt', 'fund': 'fund'}[kind], occurrence=bill, asset=bill.asset)
            entries.extend([payment, self.entry('refund', original=payment, asset=payment.asset)])
            if kind == 'fund':
                topups.append(FundTopUp.objects.create(household=self.house, created_by=self.admin, occurrence=bill,
                                                       effective_month=self.month, amount_ore=100))
        for kind in ('savings', 'debt', 'fund'):
            plans.append(MonthPlan.objects.create(household=self.house, created_by=self.admin, month=self.month,
                                                   asset=self.assets[kind], amount_ore=100))
        plans.append(MonthPlan.objects.create(household=self.house, created_by=self.admin, month=self.month,
                                               category=self.category, amount_ore=100))
        modules = sorted(access.FINANCE)
        rows_by_model = {Entry: entries, Asset: list(self.assets.values()), BillTemplate: templates,
                         BillOccurrence: bills, MonthPlan: plans, FundTopUp: topups}
        requirements = {model: [(row.pk, access.row_modules(row, self.house.pk)) for row in rows]
                        for model, rows in rows_by_model.items()}
        for flags in product((True, False), repeat=len(modules)):
            self.member.module_access = dict(zip(modules, flags))
            for model, rows in requirements.items():
                expected = {pk for pk, required in rows if all(access.allows(self.member, module) for module in required)}
                with self.subTest(permissions=self.member.module_access, model=model.__name__), CaptureQueriesContext(connection) as queries:
                    actual = set(access.safe_rows(self.member, model.objects.all()).values_list('pk', flat=True))
                    self.assertEqual(actual, expected)
                self.assertLessEqual(len(queries), 1)  # SQL may optimize a denied selection to no query.

    def test_lazy_bill_plan_and_refund_queries_follow_current_asset_classification(self):
        bill = self.bill('debt')
        payment = self.entry('debt', asset=bill.asset, occurrence=bill)
        refund = self.entry('refund', original=payment, asset=bill.asset)
        plan = MonthPlan.objects.create(household=self.house, created_by=self.admin, month=self.month, asset=bill.asset, amount_ore=100)
        self.revoke('fund')
        queries = {model: access.safe_rows(self.member, model.objects.all()) for model in (Entry, BillOccurrence, BillTemplate, MonthPlan)}
        # SQL must inspect current related rows even if a previous object/form
        # carried a different classification. No PK list may survive evaluation.
        Asset.objects.filter(pk=bill.asset_id).update(kind='fund')
        for model, ids in ((Entry, [payment.pk, refund.pk]), (BillOccurrence, [bill.pk]),
                           (BillTemplate, [bill.template_id]), (MonthPlan, [plan.pk])):
            with self.subTest(model=model.__name__):
                self.assertFalse(queries[model].filter(pk__in=ids).exists())

    def test_refund_reloads_original_after_form_validation_before_save(self):
        original = self.entry()
        self.revoke('debt')
        form = forms.EntryForm({
            'kind': 'refund', 'description': 'Refund', 'amount': '10',
            'effective_date': self.day.isoformat(), 'original': str(original.pk),
            'idempotency_key': str(uuid.uuid4()), 'fee_ore': '0',
        }, household=self.house, instance=Entry(household=self.house, created_by=self.user))
        access.restrict_form(self.member, form)
        self.assertTrue(form.is_valid(), form.errors)
        candidate = form.save(commit=False)
        self.assertEqual(candidate.original.kind, 'expense')
        original.kind, original.asset = 'debt', self.assets['debt']
        services.save_entry(self.admin, original, original.version)
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, candidate)
        self.assertFalse(Entry.objects.filter(kind='refund').exists())
        self.assertEqual(candidate.original.kind, 'debt')
        self.assertEqual(candidate.original.asset_id, self.assets['debt'].pk)

    def test_save_row_refreshes_previously_selected_asset_under_lock(self):
        self.revoke('debt')
        asset = self.assets['savings']
        candidate = MonthPlan(household=self.house, created_by=self.user, month=self.month, asset=asset, amount_ore=100)
        replacement = Asset.objects.get(pk=asset.pk)
        replacement.kind = 'debt'
        services.save_row(self.admin, replacement, replacement.version)
        with self.assertRaises(PermissionDenied): services.save_row(self.user, candidate)
        self.assertEqual(candidate.asset.kind, 'debt')
        self.assertFalse(MonthPlan.objects.filter(asset=asset).exists())

    def test_categories_in_forms_and_remittance_filter_use_only_permitted_records(self):
        hidden = Category.objects.create(household=self.house, created_by=self.admin, name='Skjult budsjettkategori')
        allowed = Category.objects.create(household=self.house, created_by=self.admin, name='Tillatt overføringskategori')
        self.entry(category=hidden)
        self.entry('remittance', category=allowed, asset=self.assets['recipient'])
        self.member.module_access = {module: module == 'savings' for module in access.MODULES}
        self.member.save(update_fields=['module_access'])
        form = access.restrict_form(self.member, forms.EntryForm(household=self.house))
        self.assertEqual(list(form.fields['category'].queryset), [])
        response = self.client.get('/ny/entry/?entry_kind=deposit')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, hidden.name)
        self.assertNotContains(response, allowed.name)
        self.member.module_access['remittance'] = True
        self.member.save(update_fields=['module_access'])
        response = self.client.get('/app/utland/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['filter_form'].fields['category'].queryset), [allowed])
        self.assertNotContains(response, hidden.name)
        form = access.restrict_form(self.member, forms.EntryForm(household=self.house))
        self.assertEqual(list(form.fields['category'].queryset), [allowed])

    def test_category_spending_is_marked_as_selection_when_bills_are_denied(self):
        ordinary = self.entry(description='Tillatt forbruk', amount_ore=100)
        self.entry(occurrence=self.bill(), amount_ore=99900)
        self.revoke('bills')
        response = self.client.get('/app/kategorier/', {'month': self.month.strftime('%Y-%m')})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Utvalg: bare poster fra tillatte moduler vises.')
        self.assertEqual(response.context['categories'][0]['spent'], ordinary.amount_ore)

    def test_bills_only_history_offers_expense_filter_and_explains_obsolete_type(self):
        payment = self.entry(occurrence=self.bill(), description='Tillatt regningsbetaling')
        self.entry(description='Skjult frittstående utgift')
        self.revoke('budget', 'savings', 'debt', 'fund', 'remittance')
        period = self.month.strftime('%Y-%m')
        response = self.client.get('/app/regninger/', {'month': period, 'kind': 'expense'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['filter_form'].is_valid())
        self.assertIn('expense', dict(response.context['filter_form'].fields['kind'].choices))
        self.assertEqual(list(response.context['entries']), [payment])
        self.assertNotContains(response, 'Skjult frittstående utgift')
        for kind in ('debt', 'obsolete'):
            response = self.client.get('/app/regninger/', {'month': period, 'kind': kind})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['filter_form'].errors.as_data()['kind'][0].code, 'invalid_choice')
            self.assertContains(response, '<ul class="errorlist"', html=False)
            self.assertContains(response, 'Ingen poster matcher valget denne måneden.')
            self.assertContains(response, f'href="/app/regninger/?month={period}">Nullstill filtrene')
            self.assertEqual(list(response.context['entries']), [])

    def test_remittance_only_empty_category_choice_explains_real_first_transfer_preparation(self):
        hidden = Category.objects.create(household=self.house, created_by=self.admin, name='Uvedkommende kategorinavn')
        self.entry(category=hidden)
        self.revoke('budget', 'bills', 'savings', 'debt', 'fund', 'annual', 'calendar')
        response = self.client.get('/ny/entry/', {'entry_kind': 'remittance', 'asset': str(self.assets['recipient'].pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['form'].fields['category'].queryset), [])
        self.assertContains(response, 'Familieadministratoren må registrere den første faktiske overføringen med riktig kategori, eller gi deg tilgang til Budsjett og poster.')
        self.assertNotContains(response, hidden.name)
        self.assertNotContains(response, self.category.name)
        self.assertFalse(Entry.objects.filter(kind='remittance').exists())
        # A real administrator-recorded transfer makes its own category usable.
        self.entry('remittance', category=self.category, asset=self.assets['recipient'])
        response = self.client.get('/ny/entry/', {'entry_kind': 'remittance'})
        self.assertEqual(list(response.context['form'].fields['category'].queryset), [self.category])
        self.assertNotContains(response, 'Familieadministratoren må registrere den første faktiske overføringen')
        self.assertNotContains(response, hidden.name)

    def test_calendar_edit_preserves_revoked_selected_participant_and_response(self):
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.member.pk), str(self.peer_member.pk)])
        result = cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)
        event = CalendarEvent.objects.get(pk=result['id'])
        cal.mutate(self.peer, 'respond', uuid.uuid4(), event_id=event.pk, original=self.day,
                   revision=event.revision, status='yes', response_revision=0)
        reply = CalendarResponse.objects.get(event=event, member=self.peer_member)
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': False}, 1)
        notices_before = CalendarNotification.objects.filter(recipient=self.peer).count()
        # A real editor only submits the remaining visible checkbox.
        displayed = cal.listing(self.user, self.day, self.day)[0]
        self.assertNotIn(self.peer_member.pk, [p['id'] for p in displayed['people']])
        payload.update(title='Redigert med bevart historikk', participants=[str(self.member.pk)])
        response = self.client.post('/app/kalender/api/', json.dumps({
            'action': 'edit', 'key': str(uuid.uuid4()), 'event_id': str(event.pk),
            'original': self.day.isoformat(), 'revision': event.revision, 'scope': 'one', 'payload': payload,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        event.refresh_from_db()
        current = cal.occurrence(event, self.day)
        self.assertIn(str(self.peer_member.pk), current['participants'])
        reply.refresh_from_db(); self.assertEqual(reply.status, 'yes'); self.assertEqual(reply.revision, 1)
        self.assertEqual(CalendarNotification.objects.filter(recipient=self.peer).count(), notices_before)

    def test_calendar_new_revoked_participants_still_rejected_and_visible_changes_reset(self):
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.member.pk)])
        event = CalendarEvent.objects.get(pk=cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)['id'])
        cal.mutate(self.user, 'respond', uuid.uuid4(), event_id=event.pk, original=self.day, revision=event.revision, status='yes', response_revision=0)
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': False}, 1)
        with self.assertRaises(ValidationError):
            cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=self.day, revision=event.revision,
                       payload={**payload, 'participants': [str(self.member.pk), str(self.peer_member.pk)]})
        cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=self.day, revision=event.revision,
                   payload={**payload, 'participants': [str(self.admin_member.pk), str(self.member.pk)]})
        self.assertFalse(CalendarResponse.objects.filter(event=event, member=self.member).exists())

    def test_restricted_bill_list_and_access_dependency_help_are_explicit(self):
        self.revoke('debt')
        self.assertContains(self.client.get('/app/regninger/'), 'Utvalg: bare regninger fra tillatte moduler')
        self.client.force_login(self.admin)
        response = self.client.get(f'/familie/modultilgang/{self.member.pk}/')
        self.assertContains(response, 'Årsoversikt krever også Budsjett og poster')
        self.assertContains(response, 'Gjeldsregninger krever både Regninger')

    def test_unknown_keys_and_non_boolean_values_are_rejected(self):
        for value in ({'typo': False}, {'budget': 0}, {'calendar': 'false'}, [], None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                access.update_member_access(self.admin, self.member.pk, value, 1)

    def test_admin_save_audit_and_existing_session_revocation_and_regrant(self):
        url = f'/familie/modultilgang/{self.member.pk}/'
        admin = Client(); admin.force_login(self.admin)
        self.assertContains(admin.get('/app/familie/'), url)
        selected = [key for key in access.MODULES if key != 'debt']
        self.assertEqual(admin.post(url, {'version': 1, 'modules': selected}).status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.module_access['debt'])
        self.assertEqual(self.member.access_version, 2)
        self.assertEqual(self.client.get('/app/gjeld/').status_code, 403)
        audit = Audit.objects.get(operation='modultilgang')
        self.assertEqual(audit.object_id, self.house.pk)
        self.assertEqual(audit.changes['membership_id'], self.member.pk)
        self.assertEqual(admin.post(url, {'version': 2, 'modules': list(access.MODULES)}).status_code, 302)
        self.assertEqual(self.client.get('/app/gjeld/').status_code, 200)

    def test_version_conflict_shows_latest_without_overwriting(self):
        self.revoke('calendar')
        admin = Client(); admin.force_login(self.admin)
        response = admin.post(f'/familie/modultilgang/{self.member.pk}/', {'version': 1, 'modules': ['calendar']})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('calendar', response.context['form'].initial['modules'])
        self.assertEqual(response.context['form'].initial['version'], 2)
        self.member.refresh_from_db(); self.assertFalse(self.member.module_access['calendar'])

    def test_access_editor_tenant_admin_csrf_and_unknown_choices(self):
        url = f'/familie/modultilgang/{self.member.pk}/'
        self.assertEqual(self.client.post(url, {'version': 1}).status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(url).status_code, 404)
        admin = Client(); admin.force_login(self.admin)
        self.assertEqual(admin.post(url, {'version': 1, 'modules': ['typo']}).status_code, 400)
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {'version': 1}).status_code, 403)
        self.assertEqual(Audit.objects.count(), 0)

    def test_pages_blocked_but_home_account_password_and_logout_remain(self):
        self.revoke(*access.MODULES)
        for page in access.PAGES:
            with self.subTest(page=page): self.assertEqual(self.client.get(f'/app/{page}/').status_code, 403)
        home = self.client.get('/app/oversikt/')
        self.assertContains(home, 'Din startside')
        self.assertNotContains(home, 'Igjen å bruke')
        self.assertNotContains(home, 'notification-bell')
        for page in ['familie', 'mer']:
            response = self.client.get(f'/app/{page}/')
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '/app/kalender/')
            self.assertNotContains(response, '/app/regninger/')
        self.assertEqual(self.client.post('/utlogging/').status_code, 302)

    def test_classification_standalone_bill_refund_plan_and_mixed_grants(self):
        bill = self.bill('debt')
        standalone = self.entry('debt', asset=self.assets['debt'], category=None)
        payment = self.entry('debt', asset=self.assets['debt'], category=None, occurrence=bill)
        refund = self.entry('refund', original=payment, category=None, asset=self.assets['debt'])
        plan = MonthPlan.objects.create(household=self.house, created_by=self.admin, month=self.month,
                                        asset=self.assets['debt'], amount_ore=100)
        self.revoke('bills')
        access.require_row(self.member, standalone)
        access.require_row(self.member, plan)
        for row in [bill, bill.template, payment, refund]:
            with self.subTest(row=type(row).__name__), self.assertRaises(PermissionDenied): access.require_row(self.member, row)
        self.revoke('debt')
        for row in [standalone, plan, bill]:
            with self.assertRaises(PermissionDenied): access.require_row(self.member, row)
        self.revoke('budget')
        access.require_row(self.member, bill)  # Ordinary bills remain independent of budget.
        access.require_row(self.member, standalone)

    def test_budget_denial_does_not_block_savings_or_ordinary_bill(self):
        bill = self.bill()
        self.revoke('budget')
        access.require_row(self.member, bill)
        self.assertEqual(self.client.get(f'/betal/{bill.pk}/').status_code, 200)
        self.assertEqual(self.client.get('/ny/entry/?entry_kind=deposit&asset='+str(self.assets['savings'].pk)).status_code, 200)
        self.assertEqual(self.client.post('/ny/entry/', {'kind': 'income'}).status_code, 403)
        self.assertEqual(self.client.get('/app/forbruk/data/').status_code, 403)

    def test_forms_and_reads_never_expose_denied_relations(self):
        hidden = self.entry('debt', description='Hemmelig gjeldspost', asset=self.assets['debt'], category=None)
        refund = self.entry('refund', description='Hemmelig gjeldsrefusjon', original=hidden, asset=self.assets['debt'], category=None)
        self.entry()
        self.revoke('debt')
        response = self.client.get('/ny/entry/')
        self.assertNotContains(response, 'Privat debt')
        self.assertNotContains(response, str(hidden.pk))
        self.assertEqual(self.client.get(f'/endre/entry/{hidden.pk}/').status_code, 403)
        self.assertEqual(self.client.get(f'/slett/{refund.pk}/').status_code, 403)
        response = self.client.get('/app/poster/')
        self.assertContains(response, 'Synlig vanlig post')
        self.assertNotContains(response, 'Hemmelig gjeld')
        self.assertContains(response, 'Utvalg:')

    def test_original_asset_and_payment_url_manipulation_cannot_bypass_denial(self):
        hidden = self.entry('fund', asset=self.assets['fund'], category=None)
        bill = self.bill('fund')
        self.revoke('fund')
        for url, body in [('/ny/entry/', {'kind': 'refund', 'original': str(hidden.pk)}),
                          ('/ny/entry/', {'kind': 'expense', 'asset': str(self.assets['fund'].pk)}),
                          ('/ny/bill/', {'accounting_class': 'fund'})]:
            with self.subTest(url=url, body=body): self.assertEqual(self.client.post(url, body).status_code, 403)
        self.assertEqual(self.client.get(f'/betal/{bill.pk}/').status_code, 403)
        with self.assertRaises(PermissionDenied): services.pay_bill(self.user, bill.pk, self.day, uuid.uuid4())

    def test_old_and_new_entry_types_both_checked_under_lock(self):
        hidden = self.entry('debt', asset=self.assets['debt'], category=None)
        ordinary = self.entry()
        self.revoke('debt')
        hidden.kind = 'expense'; hidden.category = self.category; hidden.asset = None
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, hidden, hidden.version)
        ordinary.kind = 'debt'; ordinary.asset = self.assets['debt']; ordinary.category = None
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, ordinary, ordinary.version)
        hidden.refresh_from_db(); ordinary.refresh_from_db()
        self.assertEqual((hidden.kind, ordinary.kind), ('debt', 'expense'))

    def test_idempotent_payment_and_entry_retries_recheck_access(self):
        bill = self.bill()
        payment = services.pay_bill(self.user, bill.pk, self.day, uuid.uuid4())
        self.revoke('bills')
        with self.assertRaises(PermissionDenied): services.pay_bill(self.user, bill.pk, self.day, uuid.uuid4())
        replay = Entry(household=self.house, created_by=self.user, kind='expense', amount_ore=payment.amount_ore,
                       effective_date=self.day, description='Retry', category=self.category, idempotency_key=payment.idempotency_key)
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, replay)
        self.assertEqual(Entry.objects.count(), 1)

    def test_tenant_and_own_post_rules_remain_authoritative(self):
        peer_entry = self.entry(created_by=self.peer)
        self.assertEqual(self.client.get(f'/endre/entry/{peer_entry.pk}/').status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(f'/endre/entry/{peer_entry.pk}/').status_code, 404)
        with self.assertRaises(PermissionDenied): services.save_entry(self.foreign, peer_entry, peer_entry.version)

    def test_restricted_spending_excludes_hidden_bills_remittance_refunds_and_forecast(self):
        ordinary = self.entry()
        bill = self.bill()
        linked = self.entry(occurrence=bill, description='Skjult koblet regning')
        self.entry('refund', original=linked, description='Skjult refusjon', amount_ore=100)
        self.entry('remittance', description='Skjult overføring', asset=self.assets['recipient'])
        before = services.calculate(self.house, self.month)
        self.revoke('bills', 'remittance')
        data = spending(self.user, {'month': self.month.strftime('%Y-%m')})
        self.assertEqual([row['id'] for row in data['entries']], [str(ordinary.pk)])
        self.assertEqual(data['period_total_ore'], ordinary.amount_ore)
        self.assertIsNone(data['income']['forecast_ore'])
        self.assertEqual(data['coverage']['unresolved_import_count'], 0)
        self.assertTrue(data['restricted_selection'])
        self.assertEqual(before, services.calculate(self.house, self.month))
        with self.assertRaises(PermissionDenied): planning(self.user)
        self.assertEqual(self.client.get('/app/plan/data/').status_code, 403)
        self.assertEqual(self.client.get('/app/arsoversikt/?view=matrix').status_code, 403)

    def test_calendar_revocation_checks_listing_mutation_replay_participants_and_notifications(self):
        key = uuid.uuid4()
        result = cal.mutate(self.user, 'create', key, payload=self.payload())
        event = CalendarEvent.objects.get(pk=result['id'])
        self.revoke('calendar')
        for url in ['/app/kalender/', '/app/kalender/data/?start='+self.day.isoformat()+'&end='+self.day.isoformat(),
                    '/push/summary/', '/push/config/', '/app/varsler/']:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)
        with self.assertRaises(PermissionDenied): cal.mutate(self.user, 'create', key, payload=self.payload())
        with self.assertRaises(PermissionDenied): cal.listing(self.user, self.month, self.day)
        with self.assertRaises(ValidationError):
            cal.mutate(self.admin, 'create', uuid.uuid4(), payload={**self.payload(), 'scope': 'selected', 'participants': [str(self.member.pk)]})
        self.assertNotIn(self.member.pk, [m.pk for m in access.calendar_members(self.house)])
        self.assertTrue(CalendarEvent.objects.filter(pk=event.pk).exists())
        before = CalendarNotification.objects.filter(recipient=self.user).count()
        cal.mutate(self.admin, 'create', uuid.uuid4(), payload=self.payload())
        self.assertEqual(CalendarNotification.objects.filter(recipient=self.user).count(), before)

    def test_calendar_notifications_remain_without_denied_bill_section(self):
        bill = self.bill()
        result = cal.mutate(self.admin, 'create', uuid.uuid4(), payload=self.payload())
        notice = CalendarNotification.objects.get(event_id=result['id'], recipient=self.user)
        self.revoke('bills')
        response = self.client.get('/app/varsler/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kalendervarsler')
        self.assertContains(response, notice.detail)
        self.assertContains(response, f'/push/open/{notice.pk}/')
        self.assertNotContains(response, 'Regningsvarsler')
        self.assertNotContains(response, 'Ingen regninger å vise')
        self.assertNotContains(response, 'Betaling registrerer oppgjøret')
        self.assertNotContains(response, bill.name)
        self.assertNotContains(response, f'/betal/{bill.pk}/')
        self.assertNotContains(response, '/app/regninger/')

    def test_nonparticipant_revoked_creator_receives_neither_yes_nor_no_notice_or_delivery(self):
        for actor in (self.user, self.admin):
            PushSubscription.objects.create(household=self.house, user=actor,
                endpoint_digest=f'creator-reply-{actor.pk}', session_digest='synthetic-session', active=True,
                secret_ciphertext=push.encrypt({'session_key': 'synthetic', 'subscription': {}}))
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.peer_member.pk), str(self.admin_member.pk)])
        event = CalendarEvent.objects.get(pk=cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)['id'])
        self.assertNotIn(str(self.member.pk), event.payload['participants'])
        self.revoke('calendar')
        for response_revision, status in enumerate(('yes', 'no')):
            key = uuid.uuid4()
            cal.mutate(self.peer, 'respond', key, event_id=event.pk, original=self.day,
                       revision=event.revision, status=status, response_revision=response_revision)
            self.assertFalse(CalendarNotification.objects.filter(action_key=key, recipient=self.user).exists())
            self.assertFalse(PushDelivery.objects.filter(notification__action_key=key, subscription__user=self.user).exists())
            notice = CalendarNotification.objects.get(action_key=key, recipient=self.admin)
            self.assertEqual(notice.kind, status)
            self.assertEqual(PushDelivery.objects.filter(notification=notice, subscription__user=self.admin).count(), 1)
        self.assertEqual(CalendarResponse.objects.get(event=event, member=self.peer_member).status, 'no')

    def test_pending_push_cancelled_without_transport_subscription_and_history_preserved(self):
        session = self.client.session
        sub = PushSubscription.objects.create(household=self.house, user=self.user, endpoint_digest='synthetic-endpoint',
                                               session_digest=push.digest(session.session_key), active=True,
                                               secret_ciphertext=push.encrypt({'session_key': session.session_key, 'subscription': {}}))
        result = cal.mutate(self.admin, 'create', uuid.uuid4(), payload=self.payload())
        notice = CalendarNotification.objects.get(event_id=result['id'], recipient=self.user)
        job = PushDelivery.objects.get(notification=notice)
        claim = push.claim_delivery()
        self.revoke('calendar')
        self.assertEqual(push.deliver_claim(*claim, sender=lambda *_: self.fail('Revoked delivery reached provider')), 'cancelled')
        sub.refresh_from_db(); self.assertTrue(sub.active)
        job.refresh_from_db(); self.assertEqual(job.last_error, 'access_revoked')
        self.assertTrue(CalendarNotification.objects.filter(pk=notice.pk).exists())
        self.assertEqual(self.client.get(f'/push/open/{notice.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/push/read/{notice.pk}/').status_code, 403)
        request = SimpleNamespace(user=self.user, session=session)
        with self.assertRaises(PermissionDenied): push.queue_test(request, sub.pk)
        response = self.client.post('/push/device/', json.dumps({'action': 'disable', 'endpoint': 'https://fcm.googleapis.com/fcm/send/synthetic-only'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_bills_only_payment_refund_and_undo_keep_accessible_return_path(self):
        bill = self.bill()
        self.revoke('budget', 'savings', 'debt', 'fund', 'remittance')
        paid = self.client.post(f'/betal/{bill.pk}/', {'date': self.day.isoformat(), 'key': str(uuid.uuid4()), 'version': bill.version})
        self.assertRedirects(paid, '/app/regninger/', fetch_redirect_response=False)
        payment = Entry.objects.get(occurrence=bill)
        access.require_row(self.member, payment)
        self.assertEqual(self.client.get('/ny/entry/?entry_kind=refund').status_code, 200)
        refund = services.save_entry(self.user, Entry(kind='refund', amount_ore=1, original=payment,
            effective_date=self.day, description='Tillatt regningsrefusjon'))
        access.require_row(self.member, refund)
        for row in (refund, payment):
            url = f'/slett/{row.pk}/'
            data = {'version':row.version, 'key':str(uuid.uuid4()), 'operation':'reverse', 'reason':'Feilregistrering'}
            preview = self.client.post(url, data)
            self.assertEqual(preview.status_code, 200)
            data['confirmation'] = preview.context['confirmation']
            saved = self.client.post(url, data)
            self.assertRedirects(saved, f'/historikk/entry/{row.pk}/', fetch_redirect_response=False)
        self.assertFalse(Entry.objects.filter(active=True).exists())
        self.assertEqual(Entry.objects.count(), 2)

    def test_denied_bill_composite_fund_balance_and_debt_projection_are_suppressed(self):
        bill = self.bill('fund')
        self.entry('fund', asset=self.assets['fund'], category=None, occurrence=bill, amount_ore=21300)
        self.entry('fund', asset=self.assets['fund'], category=None, amount_ore=12345)
        self.revoke('bills')
        with patch('budget.services.fund_balance', return_value=987654321) as composite:
            response = self.client.get('/app/arsutgifter/')
        self.assertEqual(response.status_code, 200)
        composite.assert_not_called()
        self.assertIsNone(response.context['assets'][0]['balance'])
        self.assertEqual(response.context['assets'][0]['paid'], 12345)
        self.assertNotContains(response, '9\u00a0876\u00a0543,21')
        self.assertContains(response, 'Beholdningen krever også regningstilgang')
        with patch('budget.services.estimated_debt_balance', return_value=876543219) as estimate:
            response = self.client.get('/app/gjeld/')
        estimate.assert_not_called()
        self.assertContains(response, 'Nedbetalingsanslag krever også regningstilgang')
        self.assertNotContains(response, '8\u00a0765\u00a0432,19')

    def test_annual_denial_removes_all_year_links_and_blocks_direct_year_api(self):
        self.revoke('annual')
        self.assertEqual(self.client.get('/app/arsoversikt/').status_code, 403)
        response = self.client.get('/app/oversikt/')
        self.assertNotContains(response, '/app/arsoversikt/')
        self.assertContains(response, 'data-sp-tab="annual" hidden')
        response = self.client.get('/app/forbruk/data/', {'period': 'year'})
        self.assertEqual(response.status_code, 403)

    def test_fund_writes_require_bills_before_balance_or_amount_validation(self):
        bill = self.bill('fund')
        self.entry('fund', asset=bill.asset, category=None, occurrence=bill, amount_ore=21300)
        original = self.entry('fund', asset=bill.asset, category=None, amount_ore=500)
        refund = self.entry('refund', original=original, asset=bill.asset, category=None, amount_ore=1)
        self.revoke('bills')
        with patch('budget.services.fund_balance', side_effect=AssertionError('Hidden balance read')), \
             patch('budget.services.validate_entry', side_effect=AssertionError('Validated before access')):
            for amount in (1, 78700, 100000, 100001):
                candidate = Entry(kind='fund', asset=bill.asset, amount_ore=amount,
                                  effective_date=self.day, description='Probe')
                with self.subTest(amount=amount), self.assertRaises(PermissionDenied):
                    services.save_entry(self.user, candidate)
            with self.assertRaises(PermissionDenied):
                services.save_entry(self.user, Entry(kind='refund', original=original, amount_ore=1,
                                                      effective_date=self.day, description='Probe refund'))
            for row in (original, refund):
                with self.subTest(row=row.pk), self.assertRaises(PermissionDenied):
                    services.delete_entry(self.user, row.pk, row.version)
            original.kind, original.asset, original.category = 'expense', None, self.category
            with self.assertRaises(PermissionDenied): services.save_entry(self.user, original, original.version)
            with self.assertRaises(PermissionDenied): services.save_row(self.user, original, original.version)
        self.assertEqual(Entry.objects.count(), 3)

    def test_fund_write_ui_and_direct_requests_follow_same_policy(self):
        original = self.entry('fund', asset=self.assets['fund'], category=None, description='Tillatt fondshistorikk')
        self.revoke('budget', 'bills')
        response = self.client.get('/app/arsutgifter/', {'month': self.month.strftime('%Y-%m')})
        self.assertContains(response, original.description)
        self.assertContains(response, 'Posthistorikk')
        self.assertNotContains(response, 'entry_kind=fund')
        self.assertNotContains(response, f'/endre/entry/{original.pk}/')
        self.assertNotContains(response, f'/slett/{original.pk}/')
        self.assertContains(response, 'fondsbetalinger krever også regningstilgang')
        for url in (f'/endre/entry/{original.pk}/', f'/slett/{original.pk}/',
                    '/ny/entry/?entry_kind=fund', '/ny/entry/?asset='+str(self.assets['fund'].pk)):
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 403)
        for body in ({'kind': 'fund'}, {'kind': 'refund', 'original': str(original.pk)},
                     {'kind': 'expense', 'asset': str(self.assets['fund'].pk)}):
            with self.subTest(body=body): self.assertEqual(self.client.post('/ny/entry/', body).status_code, 403)
        form = access.restrict_form(self.member, forms.EntryForm(household=self.house))
        self.assertNotIn('fund', dict(form.fields['kind'].choices))
        self.assertNotIn(original, form.fields['original'].queryset)
        self.assertNotIn(self.assets['fund'], form.fields['asset'].queryset)
        # Write dependency does not remove the permitted read/plan contract.
        plan = MonthPlan.objects.create(household=self.house, created_by=self.admin, month=self.month,
                                        asset=self.assets['fund'], amount_ore=100)
        self.assertIn(plan, access.safe_rows(self.member, MonthPlan.objects.all()))
        services.save_entry(self.admin, Entry(kind='fund', asset=self.assets['fund'], amount_ore=1,
                                             effective_date=self.day, description='Admin payment'))

    def test_fund_dependency_rechecks_fresh_original_and_idempotent_persisted_type(self):
        original = self.entry()
        candidate = Entry(kind='refund', original=original, amount_ore=1,
                          effective_date=self.day, description='Stale original')
        self.revoke('bills')
        updated = Entry.objects.get(pk=original.pk)
        updated.kind, updated.asset, updated.category = 'fund', self.assets['fund'], None
        services.save_entry(self.admin, updated, updated.version)
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, candidate)
        self.assertEqual(candidate.original.kind, 'fund')
        replay = Entry(kind='expense', category=self.category, amount_ore=1,
                       effective_date=self.day, description='Disguised replay', idempotency_key=updated.idempotency_key)
        with self.assertRaises(PermissionDenied): services.save_entry(self.user, replay)
        with self.assertRaises(PermissionDenied):
            services.save_row(self.user, Entry(kind='fund', asset=self.assets['fund'], amount_ore=1,
                                              effective_date=self.day, description='Direct save'))
        self.assertEqual(Entry.objects.count(), 1)

    def test_module_history_without_budget_filters_pages_and_keeps_return_path(self):
        own = self.entry('deposit', asset=self.assets['savings'], category=None, description='Mitt spareinnskudd')
        peer = self.entry('deposit', asset=self.assets['savings'], category=None, created_by=self.peer, description='Annet spareinnskudd')
        debt = self.entry('debt', asset=self.assets['debt'], category=None, description='Gjeldshistorikk')
        fund = self.entry('fund', asset=self.assets['fund'], category=None, description='Fondshistorikk')
        ordinary = self.entry(description='Skjult budsjettpost')
        bill = self.bill()
        payment = self.entry(occurrence=bill, description='Betalt regning')
        refund = self.entry('refund', original=payment, amount_ore=1, description='Regningsrefusjon')
        self.revoke('budget')
        period = self.month.strftime('%Y-%m')
        for page, visible in (('sparing', [own, peer]), ('gjeld', [debt]), ('arsutgifter', [fund]), ('regninger', [payment, refund])):
            response = self.client.get(f'/app/{page}/', {'month': period})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Posthistorikk')
            self.assertContains(response, 'Utvalg: bare tillatte poster i denne modulen')
            self.assertCountEqual(list(response.context['entries']), visible)
            self.assertNotContains(response, ordinary.description)
            for row in visible:
                self.assertContains(response, row.description)
            target = visible[0]
            self.assertContains(response, f'/slett/{target.pk}/?month={period}&amp;return_to={page}')
            self.assertContains(self.client.get(f'/slett/{target.pk}/?month={period}&return_to={page}'), f'/app/{page}/?month={period}')
        self.assertNotContains(self.client.get('/app/sparing/'), f'/endre/entry/{peer.pk}/')
        edited = self.client.get(f'/endre/entry/{own.pk}/?month={period}&return_to=sparing')
        self.assertContains(edited, f'/app/sparing/?month={period}')
        filtered = self.client.get('/app/sparing/', {'month': period, 'q': 'Mitt', 'kind': 'deposit'})
        self.assertEqual(list(filtered.context['entries']), [own])
        for index in range(11): self.entry('deposit', asset=self.assets['savings'], category=None, description=f'Paginert {index}')
        second = self.client.get('/app/sparing/', {'month': period, 'page': 2})
        self.assertEqual(second.context['page_obj'].number, 2)
        self.assertEqual(second.context['page_obj'].paginator.count, 13)
        data = {'version':own.version, 'key':str(uuid.uuid4()), 'operation':'reverse', 'reason':'Feilregistrering'}
        url = f'/slett/{own.pk}/?month={period}&return_to=sparing'
        preview = self.client.post(url, data)
        data['confirmation'] = preview.context['confirmation']
        deleted = self.client.post(url, data)
        self.assertRedirects(deleted, f'/historikk/entry/{own.pk}/', fetch_redirect_response=False)

    def test_existing_full_budget_module_layout_has_no_added_history_section(self):
        for page in ('sparing', 'gjeld', 'arsutgifter', 'regninger'):
            response = self.client.get(f'/app/{page}/')
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'Posthistorikk')
            self.assertFalse(response.context['module_history'])

    def test_safe_home_respects_household_visibility_without_revoking_direct_access(self):
        self.revoke('bills')
        self.house.modules = {'debt': False, 'fund': False, 'remittance': False, 'annual_navigation': False}
        self.house.save(update_fields=['modules'])
        response = self.client.get('/app/oversikt/')
        pages = dict(response.context['available_pages'])
        for page in ('gjeld', 'arsutgifter', 'utland', 'arsoversikt'):
            self.assertNotIn(page, pages)
            self.assertNotContains(response, f'/app/{page}/')
            self.assertEqual(self.client.get(f'/app/{page}/').status_code, 200)
        self.assertIn('sparing', pages)
        self.house.modules = {'debt': True, 'fund': True, 'remittance': True}
        self.house.save(update_fields=['modules'])
        pages = dict(self.client.get('/app/oversikt/').context['available_pages'])
        for page in ('gjeld', 'arsutgifter', 'utland', 'arsoversikt'): self.assertIn(page, pages)

    def test_calendar_one_time_change_resets_revoked_and_allowed_replies_on_regrant(self):
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.member.pk), str(self.peer_member.pk)])
        event = CalendarEvent.objects.get(pk=cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)['id'])
        for actor in (self.user, self.peer):
            cal.mutate(actor, 'respond', uuid.uuid4(), event_id=event.pk, original=self.day,
                       revision=event.revision, status='yes', response_revision=0)
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': False}, 1)
        changed_day = self.day + timedelta(days=1)
        payload.update(start=changed_day.isoformat(), end=changed_day.isoformat(), participants=[str(self.member.pk)])
        cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=self.day,
                   revision=event.revision, scope='one', payload=payload)
        self.assertFalse(CalendarResponse.objects.filter(event=event, original_date=self.day).exists())
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': True}, 2)
        displayed = cal.listing(self.peer, changed_day, changed_day)[0]
        self.assertEqual({person['id']: person['status'] for person in displayed['people']},
                         {self.member.pk: 'none', self.peer_member.pk: 'none'})

    def test_calendar_future_time_change_preserves_history_but_resets_new_segment(self):
        cutoff = self.day + timedelta(days=7)
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.member.pk), str(self.peer_member.pk)], recurrence='weekly')
        event = CalendarEvent.objects.get(pk=cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)['id'])
        for original in (self.day, cutoff):
            for actor in (self.user, self.peer):
                cal.mutate(actor, 'respond', uuid.uuid4(), event_id=event.pk, original=original,
                           revision=event.revision, status='yes', response_revision=0)
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': False}, 1)
        changed_day = cutoff + timedelta(days=1)
        payload.update(start=changed_day.isoformat(), end=changed_day.isoformat(), participants=[str(self.member.pk)])
        cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=cutoff,
                   revision=event.revision, scope='future', payload=payload)
        future = CalendarEvent.objects.get(series_key=event.series_key, payload__start=changed_day.isoformat())
        self.assertFalse(CalendarResponse.objects.filter(event=future).exists())
        self.assertEqual(CalendarResponse.objects.filter(event=event, original_date=self.day, status='yes').count(), 2)
        self.assertTrue(CalendarResponse.objects.filter(event=event, original_date=cutoff, member=self.peer_member, status='yes').exists())
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': True}, 2)
        old = cal.listing(self.peer, self.day, self.day)[0]
        changed = cal.listing(self.peer, changed_day, changed_day)[0]
        self.assertTrue(all(person['status'] == 'yes' for person in old['people']))
        self.assertEqual({person['id']: person['status'] for person in changed['people']},
                         {self.member.pk: 'none', self.peer_member.pk: 'none'})

    def test_calendar_metadata_future_edit_reconciles_exception_replies_and_revoked_history(self):
        cutoff, exceptional, unchanged = (self.day + timedelta(days=n) for n in (7, 14, 21))
        payload = self.payload(); payload.update(scope='selected', participants=[str(self.member.pk), str(self.peer_member.pk)], recurrence='weekly')
        event = CalendarEvent.objects.get(pk=cal.mutate(self.user, 'create', uuid.uuid4(), payload=payload)['id'])
        exception = cal.occurrence(event, exceptional)
        exception.update(start=(exceptional + timedelta(days=1)).isoformat(), end=(exceptional + timedelta(days=1)).isoformat())
        cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=exceptional,
                   revision=event.revision, scope='one', payload=exception)
        event.refresh_from_db()
        for original in (self.day, cutoff, exceptional, unchanged):
            for actor in (self.user, self.peer):
                cal.mutate(actor, 'respond', uuid.uuid4(), event_id=event.pk, original=original,
                           revision=event.revision, status='yes', response_revision=0)
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': False}, 1)
        payload = cal.occurrence(event, cutoff)
        payload.update(title='Kun ny tittel for serien', participants=[str(self.member.pk)])
        cal.mutate(self.user, 'edit', uuid.uuid4(), event_id=event.pk, original=cutoff,
                   revision=event.revision, scope='future', payload=payload)
        future = CalendarEvent.objects.get(series_key=event.series_key, payload__start=cutoff.isoformat())
        self.assertFalse(CalendarException.objects.filter(event=event, original_date__gte=cutoff).exists())
        for day in (cutoff, unchanged):
            self.assertEqual(CalendarResponse.objects.filter(event=future, original_date=day, status='yes').count(), 2)
        self.assertFalse(CalendarResponse.objects.filter(event=future, original_date=exceptional).exists())
        self.assertEqual(CalendarResponse.objects.filter(event=event, original_date=self.day, status='yes').count(), 2)
        archived = CalendarResponse.objects.get(event=event, original_date=exceptional)
        self.assertEqual((archived.member_id, archived.status), (self.peer_member.pk, 'yes'))
        access.update_member_access(self.admin, self.peer_member.pk, {'calendar': True}, 2)
        for day in (self.day, cutoff, unchanged):
            displayed = cal.listing(self.peer, day, day)[0]
            self.assertTrue(all(person['status'] == 'yes' for person in displayed['people']))
        displayed = cal.listing(self.peer, exceptional, exceptional)[0]
        self.assertTrue(all(person['status'] == 'none' for person in displayed['people']))
        self.assertEqual(cal.listing(self.peer, exceptional + timedelta(days=1), exceptional + timedelta(days=1)), [])
        self.assertContains(self.client.get('/app/kalender/'), 'Tidligere valgte medlemmer som har mistet kalendertilgang, forblir tilknyttet avtalen.')


class AccessLockTests(TransactionTestCase):
    def setUp(self): family_fixture(self)

    def run_waiting_after_revocation(self, module, action):
        """Observe the actual HH lock query before releasing staged revocation."""
        waiting, finished = threading.Event(), threading.Event()
        outcomes, errors = [], []
        def observe(execute, sql, params, many, context):
            if 'budget_household' in sql and 'FOR UPDATE' in sql:
                waiting.set()
            return execute(sql, params, many, context)
        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor: cursor.execute("SET statement_timeout = '8s'")
                with connection.execute_wrapper(observe): outcomes.append(action())
            except PermissionDenied: outcomes.append('denied')
            except Exception as exc: errors.append(type(exc).__name__)
            finally:
                close_old_connections(); finished.set()
        thread = threading.Thread(target=worker, daemon=True)
        try:
            with transaction.atomic():
                Household.objects.select_for_update().get(pk=self.house.pk)
                access.update_member_access(self.admin, self.member.pk, {module: False}, 1)
                thread.start()
                self.assertTrue(waiting.wait(5), 'Worker never reached the household lock query')
                self.assertFalse(finished.wait(.2), 'Worker escaped the held household lock')
        finally:
            if thread.ident is not None: thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        return outcomes

    def test_claimed_delivery_waits_for_revocation_commit_and_never_transports(self):
        client = Client(); client.force_login(self.user)
        session = client.session
        sub = PushSubscription.objects.create(household=self.house, user=self.user,
            endpoint_digest='synthetic-waiting-delivery', session_digest=push.digest(session.session_key), active=True,
            secret_ciphertext=push.encrypt({'session_key': session.session_key, 'subscription': {}}))
        job = PushDelivery.objects.create(subscription=sub)
        claim = push.claim_delivery()
        self.assertEqual(claim[0], job.pk)
        calls = []
        def sender(*args):
            calls.append(args)
            return SimpleNamespace(status_code=201)
        outcomes = self.run_waiting_after_revocation('calendar', lambda: push.deliver_claim(*claim, sender=sender))
        self.assertEqual(outcomes, ['cancelled'])
        self.assertEqual(calls, [])
        job.refresh_from_db(); sub.refresh_from_db()
        self.assertEqual((job.state, job.last_error, job.attempts), ('cancelled', 'access_revoked', 0))
        self.assertIsNone(job.lease_token)
        self.assertTrue(sub.active)

    def test_waiting_bill_payment_loses_access_without_financial_or_idempotent_result(self):
        day = timezone.localdate()
        category = Category.objects.create(household=self.house, created_by=self.admin, name='Betalingskategori')
        template = BillTemplate.objects.create(household=self.house, created_by=self.user, name='Ventende betaling',
            amount_ore=12345, first_due=day, monthly=False, accounting_class='ordinary', category=category)
        bill = BillOccurrence.objects.create(household=self.house, created_by=self.user, template=template,
            name=template.name, amount_ore=template.amount_ore, due_date=day, accounting_class='ordinary', category=category)
        key = uuid.uuid4()
        before = (bill.version, bill.amount_ore, template.version, self.house.entry_sequence)
        outcomes = self.run_waiting_after_revocation('bills', lambda: services.pay_bill(self.user, bill.pk, day, key))
        self.assertEqual(outcomes, ['denied'])
        self.assertFalse(Entry.objects.exists())
        self.assertFalse(Entry.objects.filter(idempotency_key=key).exists())
        self.assertFalse(FundTopUp.objects.exists())
        self.assertFalse(Audit.objects.filter(operation='betalt').exists())
        bill.refresh_from_db(); template.refresh_from_db(); self.house.refresh_from_db()
        self.assertEqual((bill.version, bill.amount_ore, template.version, self.house.entry_sequence), before)

    def test_two_simultaneous_admin_saves_one_version_yield_one_audit_and_one_conflict(self):
        second_admin = get_user_model().objects.create_user(username='second-access-admin')
        Membership.objects.create(household=self.house, user=second_admin, role='admin')
        barrier, outcomes, errors = threading.Barrier(2), [], []
        def change(actor, module):
            close_old_connections()
            try:
                barrier.wait(5)
                access.update_member_access(actor, self.member.pk, {module: False}, 1)
                outcomes.append('saved')
            except services.Conflict: outcomes.append('conflict')
            except Exception as exc: errors.append(type(exc).__name__)
            finally: close_old_connections()
        threads = [threading.Thread(target=change, args=args) for args in ((self.admin, 'budget'), (second_admin, 'calendar'))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(outcomes, ['saved', 'conflict'])
        self.member.refresh_from_db(); self.assertEqual(self.member.access_version, 2)
        self.assertEqual(Audit.objects.filter(operation='modultilgang').count(), 1)

    def test_waiting_mutation_reloads_permissions_after_committed_revocation(self):
        ready, finished = threading.Event(), threading.Event()
        outcome = []
        def waiting_writer():
            close_old_connections()
            try:
                ready.set()
                row = Entry(kind='income', amount_ore=100, description='Must not save', effective_date=timezone.localdate())
                services.save_entry(self.user, row)
                outcome.append('saved')
            except PermissionDenied: outcome.append('denied')
            finally:
                close_old_connections(); finished.set()
        with transaction.atomic():
            Household.objects.select_for_update().get(pk=self.house.pk)
            thread = threading.Thread(target=waiting_writer); thread.start()
            self.assertTrue(ready.wait(5))
            access.update_member_access(self.admin, self.member.pk, {'budget': False}, 1)
            self.assertFalse(finished.is_set())
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, ['denied'])
        self.assertFalse(Entry.objects.exists())

    def test_transport_holds_household_lock_until_provider_acceptance(self):
        client = Client(); client.force_login(self.user)
        session = client.session
        sub = PushSubscription.objects.create(household=self.house, user=self.user, endpoint_digest='synthetic-transport',
            session_digest=push.digest(session.session_key), active=True,
            secret_ciphertext=push.encrypt({'session_key': session.session_key, 'subscription': {}}))
        push.ensure_key()
        job = PushDelivery.objects.create(subscription=sub)
        claim = push.claim_delivery()
        sending, release, revoking, revoked = (threading.Event() for _ in range(4))
        outcomes, errors = [], []
        def sender(*_):
            sending.set()
            if not release.wait(8): raise RuntimeError('Test sender timed out')
            return SimpleNamespace(status_code=201)
        def deliver():
            close_old_connections()
            try: outcomes.append(push.deliver_claim(*claim, sender=sender))
            except Exception as exc: errors.append(type(exc).__name__)
            finally: close_old_connections()
        def revoke():
            close_old_connections()
            try:
                revoking.set()
                access.update_member_access(self.admin, self.member.pk, {'calendar': False}, 1)
                revoked.set()
            except Exception as exc: errors.append(type(exc).__name__)
            finally: close_old_connections()
        first = threading.Thread(target=deliver); first.start()
        self.assertTrue(sending.wait(8))
        second = threading.Thread(target=revoke); second.start()
        self.assertTrue(revoking.wait(5))
        try:
            self.assertFalse(revoked.wait(.2))
        finally: release.set()
        first.join(10); second.join(10)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes, ['sent'])
        self.assertTrue(revoked.is_set())
        PushDelivery.objects.create(subscription=sub)
        self.assertEqual(push.deliver_claim(*push.claim_delivery(), sender=lambda *_: self.fail('Revoked send')), 'cancelled')
