"""Regression coverage for shared-budget approval and safe recovery."""
from copy import deepcopy
from datetime import date
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings

from budget.financial_areas import (area_scope, can_write, confirm_access_change,
    create_area, legacy_inventory, participant_ids, propose_access_change,
    propose_legacy_setup, proposal_problem)
from budget.financial_models import AreaAccessChange, FinancialAreaGrant
from budget.models import Category, Household, Membership
from budget import services, spending_services


@override_settings(ALLOWED_HOSTS=['testserver'])
class SharingRecoveryTests(TestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic sharing family')
        self.owner = self.member('owner', 'admin')
        self.wife = self.member('wife', 'member')
        self.outsider = self.member('outsider', 'member')
        self.area = create_area(self.owner, 'Shared household', kind='shared')

    def member(self, name, role):
        user = get_user_model().objects.create_user(username=name, email=name+'@example.test')
        return Membership.objects.create(household=self.house, user=user, role=role)

    def proposal(self):
        return propose_access_change(self.owner, self.area.pk, [], [self.wife.pk])

    def test_sending_sharing_invitation_counts_as_owner_approval(self):
        self.client.force_login(self.owner.user)
        from django.urls import reverse
        url = reverse('financial_sharing', args=[self.area.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Bekreft og send forslag')
        response = self.client.post(url, {'editors': [self.wife.pk]}, follow=True)
        self.assertContains(response, 'Du har bekreftet. Venter på')
        self.assertNotContains(response, 'Jeg bekrefter dette forslaget')
        change = AreaAccessChange.objects.get()
        self.assertEqual(change.owner_confirmation_id, self.owner.pk)
        self.assertIsNone(change.admin_confirmation_id)
        self.assertFalse(change.applied)
        self.assertFalse(can_write(self.wife, self.area))
        self.client.post(url, {'editors': [self.wife.pk]})
        self.assertEqual(AreaAccessChange.objects.count(), 1)
        self.client.force_login(self.wife.user)
        response = self.client.post(reverse('financial_proposal', args=[change.pk]),
                                    {'digest': change.digest}, follow=True)
        self.assertContains(response, 'Forslaget er aktivert.')
        self.assertTrue(can_write(self.wife, self.area))

    def test_admin_sending_someone_elses_budget_still_requires_owner(self):
        from django.urls import reverse
        area = create_area(self.wife, 'Other owner', kind='shared')
        self.client.force_login(self.owner.user)
        response = self.client.post(reverse('financial_sharing', args=[area.pk]),
                                    {'editors': [self.owner.pk]}, follow=True)
        self.assertContains(response, 'Venter på budsjetteieren')
        change = AreaAccessChange.objects.get(area=area)
        self.assertIsNone(change.owner_confirmation_id)
        self.assertEqual(change.admin_confirmation_id, self.owner.pk)
        self.assertFalse(can_write(self.owner, area))
        self.client.force_login(self.wife.user)
        self.client.post(reverse('financial_proposal', args=[change.pk]), {'digest': change.digest})
        self.assertTrue(can_write(self.owner, area))

    def test_changed_sharing_invitation_requires_new_recipient_approval(self):
        from django.urls import reverse
        self.client.force_login(self.owner.user)
        url = reverse('financial_sharing', args=[self.area.pk])
        self.client.post(url, {'readers': [self.wife.pk]})
        first = AreaAccessChange.objects.get()
        self.client.post(url, {'editors': [self.wife.pk]})
        second = AreaAccessChange.objects.exclude(pk=first.pk).get()
        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(second.owner_confirmation_id, self.owner.pk)
        self.assertIsNone(second.admin_confirmation_id)
        self.assertFalse(second.applied)

    def test_both_approval_orders_enable_both_people_to_administer(self):
        for first, second in ((self.owner, self.wife), (self.wife, self.owner)):
            with self.subTest(first=first.pk):
                change = self.proposal()
                url = '/budsjetter/forslag/%s/' % change.pk
                self.client.force_login(first.user)
                self.assertContains(self.client.get(url), 'Jeg bekrefter dette forslaget')
                response = self.client.post(url, {'digest': change.digest}, follow=True)
                self.assertContains(response, 'Du har bekreftet. Venter på')
                self.assertNotContains(response, 'Jeg bekrefter dette forslaget')
                change.refresh_from_db()
                self.assertFalse(change.applied)
                self.client.force_login(second.user)
                response = self.client.post(url, {'digest': change.digest}, follow=True)
                self.assertContains(response, 'Forslaget er aktivert.')
                self.assertContains(response, 'Åpne budsjettet')
                change.refresh_from_db()
                self.assertTrue(change.applied)
                self.area.refresh_from_db()
                for member in (self.owner, self.wife):
                    self.assertTrue(can_write(member, self.area))
                    self.client.force_login(member.user)
                    self.assertEqual(self.client.get('/ny/category/', {'area': self.area.pk}).status_code, 200)
                    with area_scope(member, self.area.pk):
                        saved = services.save_row(member.user, Category(name='Category %s %s' % (first.pk, member.pk)), admin=True)
                        self.assertEqual(saved.financial_area_id, self.area.pk)

    def test_repeated_creation_reuses_pending_confirmed_proposal(self):
        original = self.proposal()
        confirm_access_change(self.owner, original.pk, original.digest)
        for _ in range(3):
            self.assertEqual(self.proposal().pk, original.pk)
        self.assertEqual(AreaAccessChange.objects.count(), 1)
        self.assertTrue(confirm_access_change(self.wife, original.pk, original.digest).applied)

    def test_shared_editor_can_save_plan_but_revoked_editor_cannot_replay(self):
        change = self.proposal()
        confirm_access_change(self.owner, change.pk, change.digest)
        confirm_access_change(self.wife, change.pk, change.digest)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 23)):
            with area_scope(self.wife, self.area.pk):
                draft = spending_services.planning(self.wife.user)['draft']
                draft.update(expected_income_ore=500000, acknowledge_incomplete=True)
                preview = spending_services.preview(self.wife.user, draft)
                payload = {'draft': preview['draft'], 'confirmation_digest': preview['confirmation_digest'],
                           'confirm': True, 'key': str(uuid.uuid4())}
                result = spending_services.save_plan(self.wife.user, payload)
                self.assertTrue(result['saved'])
                self.assertEqual(spending_services.save_plan(self.wife.user, payload), result)
                FinancialAreaGrant.objects.filter(area=self.area, member=self.wife).update(role='reader')
                with self.assertRaises(PermissionDenied):
                    spending_services.save_plan(self.wife.user, payload)

    def test_owner_cannot_self_approve_second_slot(self):
        change = self.proposal()
        for _ in range(2):
            result = confirm_access_change(self.owner, change.pk, change.digest)
            self.assertFalse(result.applied)
            self.assertIsNone(result.admin_confirmation_id)
        self.assertFalse(can_write(self.wife, self.area))

    def test_changed_valid_payload_cannot_reuse_existing_approval(self):
        change = self.proposal()
        confirm_access_change(self.owner, change.pk, change.digest)
        change.after = [{'member': self.owner.pk, 'role': 'owner'}, {'member': self.wife.pk, 'role': 'reader'}]
        change.save(update_fields=['after'])
        with self.assertRaises(ValidationError):
            confirm_access_change(self.wife, change.pk, change.digest)
        change.refresh_from_db()
        self.assertFalse(change.applied)
        self.assertIsNone(change.admin_confirmation_id)
        self.assertFalse(FinancialAreaGrant.objects.filter(area=self.area, member=self.wife).exists())

    def test_malformed_proposals_fail_closed_and_render_recovery(self):
        change = self.proposal()
        valid = deepcopy(change.after)
        self.client.force_login(self.owner.user)
        cases = [7, True, {}, 'bad', [None], valid + ['bad'],
                 valid + [{'member': [], 'role': {}}],
                 [{'member': True, 'role': 'owner'}, valid[1]],
                 [valid[0], {'member': float(self.wife.pk), 'role': 'editor'}],
                 valid + [valid[1]]]
        for after in cases:
            with self.subTest(after=after):
                change.after = after
                change.save(update_fields=['after'])
                self.assertTrue(proposal_problem(change))
                participant_ids(change)  # malformed metadata must never crash the chooser
                response = self.client.get('/budsjetter/forslag/%s/' % change.pk)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Gjennomgå nytt forslag')
                self.assertNotContains(response, 'Jeg bekrefter dette forslaget')
                with self.assertRaises(ValidationError):
                    confirm_access_change(self.owner, change.pk, change.digest)
        self.assertFalse(can_write(self.wife, self.area))

    def test_stale_proposal_is_rejected_even_for_already_confirmed_owner(self):
        change = self.proposal()
        confirm_access_change(self.owner, change.pk, change.digest)
        self.area.access_version += 1
        self.area.save(update_fields=['access_version'])
        with self.assertRaises(ValidationError):
            confirm_access_change(self.owner, change.pk, change.digest)
        replacement = self.proposal()
        self.assertNotEqual(replacement.pk, change.pk)
        self.assertIsNone(replacement.owner_confirmation_id)
        self.client.force_login(self.owner.user)
        response = self.client.get('/budsjetter/forslag/%s/' % change.pk)
        self.assertContains(response, 'Tilgangen er endret.')
        self.assertNotContains(response, 'Jeg bekrefter dette forslaget')

    def test_unrelated_member_and_other_household_cannot_confirm(self):
        change = self.proposal()
        self.client.force_login(self.outsider.user)
        url = '/budsjetter/forslag/%s/' % change.pk
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'digest': change.digest}).status_code, 403)
        foreign = Household.objects.create(name='Other family')
        self.outsider.household = foreign
        self.outsider.save(update_fields=['household'])
        self.assertEqual(self.client.post(url, {'digest': change.digest}).status_code, 404)

    def test_empty_legacy_setup_is_rejected(self):
        inventory = legacy_inventory(self.owner)
        with self.assertRaises(ValidationError):
            propose_legacy_setup(self.owner, self.owner.pk, [], [self.wife.pk], inventory['fingerprint'])

    def test_old_duplicate_links_are_presented_as_one_confirmed_proposal(self):
        original = self.proposal()
        confirm_access_change(self.owner, original.pk, original.digest)
        duplicate = AreaAccessChange.objects.get(pk=original.pk)
        duplicate.pk = None
        duplicate.owner_confirmation = None
        duplicate.save()
        self.client.force_login(self.wife.user)
        response = self.client.get('/budsjetter/')
        self.assertContains(response, '/budsjetter/forslag/%s/' % original.pk)
        self.assertNotContains(response, '/budsjetter/forslag/%s/' % duplicate.pk)
        self.assertEqual(self.proposal().pk, original.pk)

    def test_integrity_failure_explains_rollback_without_claiming_activation(self):
        change = self.proposal()
        self.client.force_login(self.owner.user)
        with patch('budget.area_views.areas.confirm_access_change', side_effect=IntegrityError):
            response = self.client.post('/budsjetter/forslag/%s/' % change.pk, {'digest': change.digest})
        self.assertContains(response, 'Ingen tilgang eller økonomiposter er endret.')
        self.assertNotContains(response, 'Forslaget er aktivert.')
        change.refresh_from_db()
        self.assertIsNone(change.owner_confirmation_id)
