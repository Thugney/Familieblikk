from datetime import date
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from .models import Household, Membership, Category, Entry, FinancialAreaGrant, DocumentJob
from .financial_areas import (area_scope, create_area, current_area, legacy_inventory,
                             propose_access_change, confirm_access_change)
from . import services, document_services, spending_services


class FinancialAreaTests(TestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic household')
        self.owner = self.member('owner', 'member')
        self.parent = self.member('parent', 'admin')
        self.other = self.member('other', 'admin')
        self.area = create_area(self.owner, reader_ids=[self.parent.pk])
        self.secret = create_area(self.other)
        with area_scope(self.owner, self.area.pk):
            self.category = services.save_row(self.owner.user, Category(name='Private category'), admin=True)
            self.entry = services.save_entry(self.owner.user, Entry(kind='expense', amount_ore=4500,
                description='Private expense', effective_date=date(2026, 1, 1), category=self.category))

    def member(self, name, role):
        user = get_user_model().objects.create_user(username=name, password='Synthetic-test-phrase-314!')
        return Membership.objects.create(household=self.house, user=user, role=role)

    def test_missing_scope_has_no_financial_rows_and_rejects_write(self):
        self.assertEqual(Category.objects.count(), 0)
        with self.assertRaises(PermissionDenied):
            services.save_row(self.owner.user, Category(name='No target'))

    def test_admin_without_grant_cannot_read(self):
        with self.assertRaises(PermissionDenied):
            with area_scope(self.other, self.area.pk):
                pass

    def test_reader_reads_but_cannot_write_delete_or_replay(self):
        with area_scope(self.parent, self.area.pk):
            self.assertEqual(Entry.objects.count(), 1)
            with self.assertRaises(PermissionDenied):
                services.save_row(self.parent.user, Category(name='Denied'))
            with self.assertRaises(PermissionDenied):
                Category.objects.filter(pk=self.category.pk).delete()
            with self.assertRaises(PermissionDenied):
                self.category.delete()
            with self.assertRaises(PermissionDenied):
                document_services.manual(self.parent.user, uuid.uuid4())

    def test_revocation_applies_to_lazy_queries_and_old_instances(self):
        with area_scope(self.parent, self.area.pk):
            query = Category.objects.all()
            FinancialAreaGrant.objects.filter(area=self.area, member=self.parent).delete()
            self.assertEqual(list(query), [])
            with self.assertRaises(PermissionDenied):
                current_area(self.parent)

    def test_same_family_area_cannot_supply_relations(self):
        with area_scope(self.other, self.secret.pk):
            category = services.save_row(self.other.user, Category(name='Other category'))
        with area_scope(self.owner, self.area.pk):
            with self.assertRaises((PermissionDenied, ValidationError, Category.DoesNotExist)):
                services.save_entry(self.owner.user, Entry(kind='expense', amount_ore=100,
                    description='Wrong link', effective_date=date(2026, 1, 1), category=category))
            with self.assertRaises(ValidationError):
                Entry.objects.filter(pk=self.entry.pk).update(category_id=category.pk)

    def test_database_blocks_raw_cross_area_relation(self):
        with area_scope(self.other, self.secret.pk):
            category = services.save_row(self.other.user, Category(name='Other category'))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Entry.all_objects.filter(pk=self.entry.pk).update(category=category)
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_database_blocks_cross_area_history_snapshot(self):
        from .models import CorrectionEvent
        with area_scope(self.other, self.secret.pk):
            other_category = services.save_row(self.other.user, Category(name='Secret snapshot category'))
        event = CorrectionEvent.all_objects.filter(object_id=self.entry.pk).first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CorrectionEvent.all_objects.filter(pk=event.pk).update(after={'category_id': str(other_category.pk)})
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_database_rejects_cross_family_grant(self):
        house = Household.objects.create(name='Unrelated family')
        user = get_user_model().objects.create_user(username='unrelated')
        stranger = Membership.objects.create(household=house, user=user, role='admin')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinancialAreaGrant.objects.create(area=self.area, member=stranger, role='reader')
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_saved_queryset_cannot_write_after_area_switch(self):
        with area_scope(self.owner, self.area.pk):
            query = Category.objects.all()
        with area_scope(self.other, self.secret.pk):
            with self.assertRaises(PermissionDenied):
                query.update(name='Wrong tab')

    def test_two_distinct_confirmers_and_stale_proposal(self):
        proposal = propose_access_change(self.owner, self.area.pk, [])
        confirm_access_change(self.owner, proposal.pk, proposal.digest)
        self.assertTrue(FinancialAreaGrant.objects.filter(area=self.area, member=self.parent).exists())
        result = confirm_access_change(self.parent, proposal.pk, proposal.digest)
        self.assertTrue(result.applied)
        self.assertFalse(FinancialAreaGrant.objects.filter(area=self.area, member=self.parent).exists())
        with self.assertRaises(ValidationError):
            confirm_access_change(self.parent, proposal.pk, proposal.digest)

    def test_owner_admin_cannot_confirm_both_roles(self):
        proposal = propose_access_change(self.other, self.secret.pk, [self.parent.pk])
        confirm_access_change(self.other, proposal.pk, proposal.digest)
        result = confirm_access_change(self.other, proposal.pk, proposal.digest)
        self.assertFalse(result.applied)
        self.assertIsNone(result.admin_confirmation_id)

    def test_admin_owner_can_finish_with_member_reader(self):
        proposal = propose_access_change(self.other, self.secret.pk, [self.owner.pk])
        confirm_access_change(self.other, proposal.pk, proposal.digest)
        proposal.refresh_from_db()
        self.assertFalse(proposal.applied)
        result = confirm_access_change(self.owner, proposal.pk, proposal.digest)
        result.refresh_from_db()
        self.assertTrue(result.applied)
        self.assertTrue(FinancialAreaGrant.objects.filter(area=self.secret, member=self.owner, role='reader').exists())

    def test_shared_editor_has_write_capability_personal_editor_rejected(self):
        with self.assertRaises(ValidationError):
            create_area(self.owner, editor_ids=[self.parent.pk])
        shared = create_area(self.owner, editor_ids=[self.parent.pk], kind='shared')
        with area_scope(self.parent, shared.pk):
            services.save_row(self.parent.user, Category(name='Joint category'), admin=True)
            self.assertEqual(Category.objects.count(), 1)

    def test_hidden_activity_does_not_change_revision_or_totals(self):
        with area_scope(self.owner, self.area.pk):
            before = spending_services.source_revision(self.house)
        with area_scope(self.other, self.secret.pk):
            services.save_entry(self.other.user, Entry(kind='income', amount_ore=999999,
                description='Hidden income', effective_date=date(2026, 1, 1)))
        with area_scope(self.owner, self.area.pk):
            self.assertEqual(before, spending_services.source_revision(self.house))
            self.assertEqual(services.calculate(self.house, date(2026, 1, 1))['income'], 0)

    def test_identical_document_key_is_independent_by_area(self):
        key = uuid.uuid4()
        with area_scope(self.owner, self.area.pk):
            first = document_services.manual(self.owner.user, key)
        with area_scope(self.other, self.secret.pk):
            second = document_services.manual(self.other.user, key)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(DocumentJob.objects.count(), 2)

    def test_new_areas_are_empty_and_inventory_omits_financial_values(self):
        with area_scope(self.other, self.secret.pk):
            self.assertEqual(Entry.objects.count(), 0)
        inventory = legacy_inventory(self.parent)
        self.assertEqual(sum(inventory['groups'].values()), 0)
        self.assertNotIn('Private expense', str(inventory))


class FinancialAreaUpgradeTests(TransactionTestCase):
    def test_additive_upgrade_and_explicit_two_person_assignment(self):
        from django.db.migrations.executor import MigrationExecutor
        from .financial_areas import propose_legacy_setup, confirm_legacy_setup
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes('budget')
        old_target = [('budget', '0016_transient_scans')]
        executor.migrate(old_target)
        try:
            state = executor.loader.project_state(old_target).apps
            house = state.get_model('budget', 'Household').objects.create(name='Synthetic legacy')
            user = get_user_model().objects.create_user(username='legacy-owner')
            admin_user = get_user_model().objects.create_user(username='legacy-admin')
            owner = state.get_model('budget', 'Membership').objects.create(household=house, user_id=user.pk, role='admin')
            admin = state.get_model('budget', 'Membership').objects.create(household=house, user_id=admin_user.pk, role='admin')
            category = state.get_model('budget', 'Category').objects.create(household=house, created_by_id=user.pk, name='Preserved category')
            batch = state.get_model('budget', 'ImportBatch').objects.create(household=house, created_by_id=user.pk, series='synthetic-only', sha256='a'*64)
            record = state.get_model('budget', 'ImportRecord').objects.create(household=house, created_by_id=user.pk,
                batch=batch, source_id='synthetic-row', source_kind='categories', target_id=category.pk, raw={'amount': '123,45', 'date': '2026-09-01'})
            shopping_key = uuid.uuid4()
            listing = state.get_model('budget', 'ShoppingList').objects.create(household=house, created_by_id=user.pk, name='Preserved list')
            state.get_model('budget', 'WorkflowCommand').objects.create(household=house, created_by_id=user.pk,
                key=shopping_key, operation='shopping_list', payload={'name': 'Preserved list', 'id': None, 'version': None}, result_id=listing.pk)
        finally:
            MigrationExecutor(connection).migrate(latest)
        from .models import ImportRecord
        owner, admin = Membership.objects.get(pk=owner.pk), Membership.objects.get(pk=admin.pk)
        from .shopping_services import save_list
        from .models import ShoppingList
        self.assertEqual(save_list(owner.user, 'Preserved list', shopping_key).pk, listing.pk)
        self.assertEqual(ShoppingList.objects.filter(household_id=house.pk).count(), 1)
        self.assertIsNone(Category.all_objects.get(pk=category.pk).financial_area_id)
        inventory = legacy_inventory(admin)
        proposal = propose_legacy_setup(admin, owner.pk, [], [admin.pk], inventory['fingerprint'])
        confirm_legacy_setup(admin, proposal.pk, proposal.digest)
        self.assertIsNone(Category.all_objects.get(pk=category.pk).financial_area_id)
        result = confirm_legacy_setup(owner, proposal.pk, proposal.digest)
        self.assertTrue(result.applied)
        with area_scope(owner, result.area_id):
            self.assertEqual(Category.objects.get(pk=category.pk).name, 'Preserved category')
            saved = ImportRecord.objects.get(pk=record.pk)
            self.assertEqual(saved.raw, {'amount': '123,45', 'date': '2026-09-01'})
            self.assertEqual(saved.target_id, category.pk)
        self.assertEqual(sum(legacy_inventory(admin)['groups'].values()), 0)
