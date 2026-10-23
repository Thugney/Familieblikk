"""Synthetic upgrade coverage for the connected legacy financial record graph."""
from datetime import date
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from budget.financial_areas import (
    area_scope, confirm_access_change, financial_models, legacy_inventory,
    propose_legacy_setup,
)
from budget.models import Membership, SeriesRevision, DocumentJob, ShoppingList


class LegacySharingGraphTests(TransactionTestCase):
    def seed_old_graph(self, state, suffix):
        """Build entirely fictional rows using the actual pre-area schema."""
        user = get_user_model().objects.create_user(username='legacy-owner-' + suffix)
        second_user = get_user_model().objects.create_user(username='legacy-reader-' + suffix)
        house = state.get_model('budget', 'Household').objects.create(name='Synthetic ' + suffix)
        owner = state.get_model('budget', 'Membership').objects.create(
            household=house, user_id=user.pk, role='admin')
        second = state.get_model('budget', 'Membership').objects.create(
            household=house, user_id=second_user.pk, role='member')

        def make(model_name, **values):
            model = state.get_model('budget', model_name)
            fields = {field.name for field in model._meta.fields}
            defaults = {}
            if 'household' in fields:
                defaults['household'] = house
            if 'created_by' in fields:
                defaults['created_by_id'] = user.pk
            if 'actor' in fields:
                defaults['actor_id'] = user.pk
            return model.objects.create(**(defaults | values))

        day = date(2026, 9, 1)
        category = make('Category', name='Fictional groceries')
        asset = make('Asset', name='Fictional fund', kind='fund', opening_date=day)
        plan = make('MonthPlan', month=day, category=category, amount_ore=120000)
        template = make('BillTemplate', name='Fictional bill', amount_ore=25000,
                        first_due=day, category=category, asset=asset, accounting_class='fund')
        bill = make('BillOccurrence', template=template, name='Fictional bill', due_date=day,
                    recurrence_slot=day, amount_ore=25000, category=category,
                    asset=asset, accounting_class='fund')
        payment = make('Entry', kind='fund', amount_ore=25000, effective_date=day,
                       description='Fictional payment', occurrence=bill,
                       category=category, asset=asset, sequence=1)
        expense = make('Entry', kind='expense', amount_ore=10000, effective_date=day,
                       description='Fictional trip', category=category, sequence=2)
        make('Entry', kind='refund', amount_ore=1000, effective_date=day,
             description='Fictional refund', original=expense, category=category, sequence=3)
        make('FundTopUp', occurrence=bill, effective_month=day, amount_ore=25000)
        batch = make('ImportBatch', series='synthetic', sha256='a' * 64)
        # The import review screen replaces a category target with the saved
        # MonthPlan when its previously undated monthly limit is confirmed.
        make('ImportRecord', batch=batch, source_id='synthetic-reviewed-category',
             source_kind='categories', raw={'monthly_budget_ore': 120000},
             status='confirmed', target_id=plan.pk)
        asset_plan = make('MonthPlan', month=day, asset=asset, amount_ore=25000)
        # Existing import review also allowed choosing "Mål / gjeld / fond".
        make('ImportRecord', batch=batch, source_id='synthetic-reviewed-asset-plan',
             source_kind='categories', raw={'monthly_budget_ore': 25000},
             status='confirmed', target_id=asset_plan.pk)
        make('ImportRecord', batch=batch, source_id='synthetic-category-draft',
             source_kind='categories', raw={'monthly_budget_ore': 120000},
             target_id=category.pk)
        make('ImportRecord', batch=batch, source_id='synthetic-entry', source_kind='transactions',
             raw={'amount': '250,00', 'date': '2026-09-01'}, target_id=payment.pk,
             status='confirmed', approved_decision={'category_id': str(category.pk), 'amount_ore': 25000})
        make('ImportRecord', batch=batch, source_id='synthetic-draft', source_kind='settings',
             raw={'unresolved': True})
        make('MonthlyBudgetHeader', month=day, expected_income_ore=500000)
        make('PlanningRequest', digest='b' * 64, result={'month': '2026-09-01'})
        command = make('CorrectionCommand', operation='series_change', idempotency_key=uuid.uuid4(),
                       payload_hash='c' * 64, result_id=template.pk, result_version=2)
        event = make('CorrectionEvent', object_type='billtemplate', object_id=template.pk,
                     operation='series_change', command=command,
                     before={'category_id': str(category.pk), 'amount_ore': 24000},
                     after={'category_id': str(category.pk), 'amount_ore': 25000})
        make('CorrectionEvent', object_type='entry', object_id=payment.pk, operation='create',
             after={'category_id': str(category.pk), 'occurrence_id': str(bill.pk)})
        revision = make('SeriesRevision', template=template, event=event, effective_date=day,
                        values={'category_id': str(category.pk), 'amount_ore': 25000})
        document = make('Document', storage_key='synthetic-only-' + suffix, filename='fictional.png',
                        size=10, category=category, entry=expense, confirmed=True)
        job = make('DocumentJob', document=document, status='done')
        listing = make('ShoppingList', name='Fictional shared list')
        trip = make('ShoppingTrip', shopping_list=listing, store='Fictional shop',
                    entry=expense, receipt=document)
        make('ShoppingItem', shopping_list=listing, name='Fictional item', purchased=True, trip=trip)
        make('WorkflowCommand', key=uuid.uuid4(), operation='shopping_complete', result_id=trip.pk,
             payload={'category': str(category.pk), 'receipt': str(document.pk)})
        make('WorkflowCommand', key=uuid.uuid4(), operation='document_confirm', result_id=document.pk,
             payload={'id': str(document.pk)})
        make('WorkflowCommand', key=uuid.uuid4(), operation='shopping_list', result_id=listing.pk,
             payload={'name': 'Fictional shared list'})
        make('Audit', object_id=expense.pk, operation='opprettet', changes={'amount_ore': 10000})
        make('Audit', object_id=listing.pk, operation='handlelistevare', changes={'purchased': True})
        return house.pk, owner.pk, second.pk, revision.pk, job.pk, listing.pk

    def migrated_graphs(self, suffixes, target=None):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes('budget')
        old = [('budget', '0016_transient_scans')]
        executor.migrate(old)
        try:
            state = executor.loader.project_state(old).apps
            fixtures = [self.seed_old_graph(state, suffix) for suffix in suffixes]
        finally:
            MigrationExecutor(connection).migrate(target or latest)
        return fixtures

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_failed_existing_invitation_can_be_accepted_after_compatibility_migration(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes('budget')
        try:
            house_id, owner_id, second_id, *_ = self.migrated_graphs(
                ('retry-existing',), [('budget', '0025_reviewed_category_import_targets')])[0]
            owner = Membership.objects.get(pk=owner_id)
            second = Membership.objects.get(pk=second_id)
            inventory = legacy_inventory(owner)
            proposal = propose_legacy_setup(owner, owner.pk, [], [second.pk], inventory['fingerprint'])
            url = '/budsjetter/forslag/%s/' % proposal.pk
            self.client.force_login(owner.user)
            self.assertEqual(self.client.post(url, {'digest': proposal.digest}).status_code, 302)
            self.client.force_login(second.user)
            response = self.client.post(url, {'digest': proposal.digest})
            self.assertContains(response, 'Ingen tilgang eller økonomiposter er endret.')
            proposal.refresh_from_db()
            self.assertEqual(proposal.owner_confirmation_id, owner.pk)
            self.assertIsNone(proposal.admin_confirmation_id)
            self.assertIsNone(proposal.area_id)
            self.assertEqual(legacy_inventory(owner), inventory)
        finally:
            MigrationExecutor(connection).migrate(latest)
        # A function-only repair must leave the signed inventory and first
        # approval intact. The spouse can retry the very same invitation.
        self.assertEqual(legacy_inventory(owner), inventory)
        response = self.client.post(url, {'digest': proposal.digest}, follow=True)
        self.assertContains(response, 'Forslaget er aktivert.')
        self.assertContains(response, 'Åpne budsjettet')
        proposal.refresh_from_db()
        self.assertTrue(proposal.applied)
        from budget import services
        from budget.models import Category
        for member in (owner, second):
            self.client.force_login(member.user)
            self.assertEqual(self.client.get('/ny/category/', {'area': proposal.area_id}).status_code, 200)
            with area_scope(member, proposal.area_id, write=True):
                category = services.save_row(member.user, Category(name='Shared edit %s' % member.pk), admin=True)
                self.assertEqual(category.financial_area_id, proposal.area_id)

    def test_connected_graph_survives_both_confirmation_orders(self):
        fixtures = self.migrated_graphs(('owner-first', 'editor-first'))
        for house_id, owner_id, second_id, revision_id, job_id, listing_id in fixtures:
            with self.subTest(household=house_id):
                owner, second = Membership.objects.get(pk=owner_id), Membership.objects.get(pk=second_id)
                snapshots = {}
                for model in financial_models():
                    rows = list(model.all_objects.filter(household_id=house_id).order_by('pk').values())
                    for row in rows:
                        row.pop('financial_area_id')
                    snapshots[model] = rows
                related_before = {
                    'revision': SeriesRevision.objects.filter(pk=revision_id).values().get(),
                    'job': DocumentJob.objects.filter(pk=job_id).values().get(),
                    'list': ShoppingList.objects.filter(pk=listing_id).values().get(),
                }
                inventory = legacy_inventory(owner)
                proposal = propose_legacy_setup(owner, owner.pk, [], [second.pk], inventory['fingerprint'])
                first, last = (owner, second) if owner.user.username.endswith('owner-first') else (second, owner)
                self.assertFalse(confirm_access_change(first, proposal.pk, proposal.digest).applied)
                self.assertEqual(legacy_inventory(owner), inventory)
                result = confirm_access_change(last, proposal.pk, proposal.digest)
                self.assertTrue(result.applied)
                self.assertEqual(sum(legacy_inventory(owner)['groups'].values()), 0)
                for model, before in snapshots.items():
                    after = list(model.all_objects.filter(household_id=house_id).order_by('pk').values())
                    for row in after:
                        area_id = row.pop('financial_area_id')
                        metadata = model._meta.model_name == 'audit' and row['operation'] in model.METADATA_OPERATIONS
                        self.assertEqual(area_id, None if metadata else result.area_id)
                    self.assertEqual(after, before, model._meta.model_name)
                self.assertEqual(SeriesRevision.objects.filter(pk=revision_id).values().get(), related_before['revision'])
                self.assertEqual(DocumentJob.objects.filter(pk=job_id).values().get(), related_before['job'])
                self.assertEqual(ShoppingList.objects.filter(pk=listing_id).values().get(), related_before['list'])
                with area_scope(second, result.area_id, write=True):
                    from budget.models import Entry
                    self.assertEqual(Entry.objects.count(), 3)

    def test_historical_revision_change_requires_fresh_legacy_approval(self):
        house_id, owner_id, second_id, revision_id, _, _ = self.migrated_graphs(('stale-history',))[0]
        owner, second = Membership.objects.get(pk=owner_id), Membership.objects.get(pk=second_id)
        inventory = legacy_inventory(owner)
        proposal = propose_legacy_setup(owner, owner.pk, [], [second.pk], inventory['fingerprint'])
        confirm_access_change(owner, proposal.pk, proposal.digest)
        SeriesRevision.objects.filter(pk=revision_id).update(values={'amount_ore': 26000})
        self.assertNotEqual(legacy_inventory(owner)['fingerprint'], inventory['fingerprint'])
        with self.assertRaises(ValidationError):
            confirm_access_change(second, proposal.pk, proposal.digest)
        proposal.refresh_from_db()
        self.assertFalse(proposal.applied)
        self.assertIsNone(proposal.admin_confirmation_id)
        self.assertIsNone(proposal.area_id)
        from budget.models import Entry
        self.assertEqual(Entry.all_objects.filter(household_id=house_id, financial_area=None).count(), 3)

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_sending_legacy_invitation_needs_only_spouse_acceptance(self):
        from budget.financial_models import AreaAccessChange
        house_id, owner_id, second_id, *_ = self.migrated_graphs(('send-once',))[0]
        owner, second = Membership.objects.get(pk=owner_id), Membership.objects.get(pk=second_id)
        inventory = legacy_inventory(owner)
        self.client.force_login(owner.user)
        response = self.client.post('/budsjetter/', {'owner': owner.pk, 'editors': [second.pk],
                                   'fingerprint': inventory['fingerprint']}, follow=True)
        self.assertContains(response, 'Du har bekreftet. Venter på')
        self.assertNotContains(response, 'Jeg bekrefter dette forslaget')
        proposal = AreaAccessChange.objects.get(household_id=house_id)
        self.assertEqual(proposal.owner_confirmation_id, owner.pk)
        self.assertIsNone(proposal.admin_confirmation_id)
        self.assertEqual(legacy_inventory(owner), inventory)
        self.client.force_login(second.user)
        response = self.client.post('/budsjetter/forslag/%s/' % proposal.pk,
                                    {'digest': proposal.digest}, follow=True)
        self.assertContains(response, 'Forslaget er aktivert.')
        proposal.refresh_from_db()
        self.assertTrue(proposal.applied)
        self.assertEqual(sum(legacy_inventory(owner)['groups'].values()), 0)
