"""Reviewed category imports retain valid plan links without widening access."""
from datetime import date
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from budget.financial_areas import area_scope, create_area
from budget.models import Asset, Category, Household, ImportBatch, ImportRecord, Membership, MonthPlan


@override_settings(ALLOWED_HOSTS=['testserver'])
class ImportPlanTargetTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='import-owner', email='owner@example.test')
        self.house = Household.objects.create(name='Synthetic import family')
        self.member = Membership.objects.create(user=self.user, household=self.house,
                                                role='admin', verified_at=timezone.now())
        self.area = create_area(self.member)
        self.other_area = create_area(self.member, 'Other budget')
        with area_scope(self.member, self.area.pk):
            self.category = Category.objects.create(household=self.house, created_by=self.user, name='Fictional category')
            self.plan = MonthPlan.objects.create(household=self.house, created_by=self.user,
                category=self.category, month=date(2026, 9, 1), amount_ore=120000)
            asset = Asset.objects.create(household=self.house, created_by=self.user,
                kind='savings', name='Fictional savings', opening_date=date(2026, 9, 1))
            self.asset_plan = MonthPlan.objects.create(household=self.house, created_by=self.user,
                asset=asset, month=date(2026, 9, 1), amount_ore=10000)
            self.batch = ImportBatch.objects.create(household=self.house, created_by=self.user,
                                                   series='synthetic-review', sha256='a' * 64)
            self.record = ImportRecord.objects.create(household=self.house, created_by=self.user,
                batch=self.batch, source_id='category-review', source_kind='categories',
                target_id=self.category.pk, raw={'monthly_budget_ore': 120000})
        with area_scope(self.member, self.other_area.pk):
            category = Category.objects.create(household=self.house, created_by=self.user, name='Other category')
            self.other_plan = MonthPlan.objects.create(household=self.house, created_by=self.user,
                category=category, month=date(2026, 9, 1), amount_ore=10000)
            asset = Asset.objects.create(household=self.house, created_by=self.user,
                kind='debt', name='Other debt', opening_date=date(2026, 9, 1))
            self.other_asset_plan = MonthPlan.objects.create(household=self.house, created_by=self.user,
                asset=asset, month=date(2026, 9, 1), amount_ore=10000)
        foreign_user = get_user_model().objects.create_user(username='foreign-import-owner')
        foreign_house = Household.objects.create(name='Other synthetic family')
        foreign_member = Membership.objects.create(user=foreign_user, household=foreign_house, role='admin')
        foreign_area = create_area(foreign_member)
        with area_scope(foreign_member, foreign_area.pk):
            category = Category.objects.create(household=foreign_house, created_by=foreign_user, name='Foreign category')
            self.foreign_plan = MonthPlan.objects.create(household=foreign_house, created_by=foreign_user,
                category=category, month=date(2026, 9, 1), amount_ore=10000)
            asset = Asset.objects.create(household=foreign_house, created_by=foreign_user,
                kind='fund', name='Foreign fund', opening_date=date(2026, 9, 1))
            self.foreign_asset_plan = MonthPlan.objects.create(household=foreign_house, created_by=foreign_user,
                asset=asset, month=date(2026, 9, 1), amount_ore=10000)

    def test_category_review_posts_plan_and_repeated_submit_preserves_it(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['verified_email'] = self.user.email
        session.save()
        url = '/import/avklar/%s/?area=%s' % (self.record.pk, self.area.pk)
        payload = {'month': '2026-10-01', 'category': str(self.category.pk), 'amount': '1200', 'version': 0}
        original_raw = self.record.raw.copy()
        with patch('budget.importing.load_private_source', return_value=({}, {'owner_email': self.user.email})):
            response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 302, response.content.decode())
            self.record.refresh_from_db(from_queryset=ImportRecord.all_objects.all())
            target = self.record.target_id
            self.assertEqual(self.record.status, 'confirmed')
            self.assertEqual(self.record.raw, original_raw)
            with area_scope(self.member, self.area.pk):
                plan = MonthPlan.objects.get(pk=target)
                self.assertEqual((plan.category_id, plan.amount_ore, plan.month),
                                 (self.category.pk, 120000, date(2026, 10, 1)))
            self.assertEqual(self.client.post(url, payload).status_code, 302)
            self.record.refresh_from_db(from_queryset=ImportRecord.all_objects.all())
            self.assertEqual(self.record.target_id, target)
            self.assertEqual(MonthPlan.all_objects.filter(financial_area=self.area, category=self.category, month='2026-10-01').count(), 1)

    def test_python_and_database_reject_invalid_plan_targets(self):
        cases = [
            ('foreign-budget', self.other_plan.pk, 'confirmed', 'categories'),
            ('foreign-family', self.foreign_plan.pk, 'confirmed', 'categories'),
            ('foreign-budget-asset-plan', self.other_asset_plan.pk, 'confirmed', 'categories'),
            ('foreign-family-asset-plan', self.foreign_asset_plan.pk, 'confirmed', 'categories'),
            ('missing', uuid.uuid4(), 'confirmed', 'categories'),
            ('unreviewed-plan', self.plan.pk, 'needs_review', 'categories'),
            ('unreviewed-asset-plan', self.asset_plan.pk, 'needs_review', 'categories'),
            ('transaction-plan', self.plan.pk, 'confirmed', 'transactions'),
        ]
        for label, target, status, kind in cases:
            with self.subTest(case=label):
                with area_scope(self.member, self.area.pk):
                    row = ImportRecord.objects.get(pk=self.record.pk)
                    row.target_id, row.status, row.source_kind = target, status, kind
                    with self.assertRaises(ValidationError):
                        row.save()
                # Bypass model validation to prove the database itself enforces isolation.
                with self.assertRaises(IntegrityError):
                    ImportRecord.all_objects.filter(pk=self.record.pk).update(
                        target_id=target, status=status, source_kind=kind)
                self.record.refresh_from_db(from_queryset=ImportRecord.all_objects.all())
                self.assertEqual(self.record.target_id, self.category.pk)
                self.assertEqual(self.record.status, 'needs_review')

    def test_category_import_review_can_choose_an_asset_plan(self):
        # PlanForm explicitly offers "Mål / gjeld / fond" as an alternative
        # to Category. source_kind describes the imported sheet, not that
        # reviewed choice's destination model.
        self.client.force_login(self.user)
        session = self.client.session
        session['verified_email'] = self.user.email
        session.save()
        url = '/import/avklar/%s/?area=%s' % (self.record.pk, self.area.pk)
        payload = {'month': '2026-10-01', 'category': '',
                   'asset': str(self.asset_plan.asset_id), 'amount': '1200', 'version': 0}
        original_raw = self.record.raw.copy()
        with patch('budget.importing.load_private_source', return_value=({}, {'owner_email': self.user.email})):
            response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 302)
            self.record.refresh_from_db(from_queryset=ImportRecord.all_objects.all())
            target = self.record.target_id
            self.assertEqual(self.record.status, 'confirmed')
            self.assertEqual(self.record.raw, original_raw)
            with area_scope(self.member, self.area.pk):
                plan = MonthPlan.objects.get(pk=target)
                self.assertIsNone(plan.category_id)
                self.assertEqual((plan.asset_id, plan.amount_ore), (self.asset_plan.asset_id, 120000))
            self.assertEqual(self.client.post(url, payload).status_code, 302)
            self.record.refresh_from_db(from_queryset=ImportRecord.all_objects.all())
            self.assertEqual(self.record.target_id, target)
