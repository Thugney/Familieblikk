import json
import uuid
from datetime import date
from types import SimpleNamespace
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from budget import financial_areas as areas, push_services as push, shopping_services as shopping
from budget import notification_services as notices
from budget.models import Household, Membership, CalendarNotification, PushDelivery, PushSubscription, ShoppingItem
from budget.financial_models import FinancialAreaGrant, AreaAccessChange


class SharingNotificationTests(TestCase):
    def setUp(self):
        self.house = Household.objects.create(name='Synthetic notification family')
        self.other_house = Household.objects.create(name='Other synthetic notification family')
        self.owner = self.member('notice-owner')
        self.invited = self.member('notice-invited')
        self.admin = self.member('notice-admin', role='admin')
        self.peer = self.member('notice-peer')
        self.foreign = self.member('notice-foreign', household=self.other_house)
        self.area = areas.create_area(self.owner, 'Sensitive budget label', kind='shared')
        self.client.force_login(self.invited.user)
        key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.info = {'endpoint': 'https://fcm.googleapis.com/fcm/send/sharing-synthetic',
                     'keys': {'p256dh': push._b64(key), 'auth': push._b64(b'0123456789abcdef')}}
        push.ensure_key()

    def member(self, username, role='member', household=None):
        user = get_user_model().objects.create_user(username=username, email=username+'@example.test')
        return Membership.objects.create(user=user, household=household or self.house, role=role)

    def subscribe(self):
        response = self.client.post('/push/device/', json.dumps({'action': 'subscribe', 'subscription': self.info}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        return PushSubscription.objects.get(pk=response.json()['id'])

    def proposal(self, actor=None, readers=(), editors=None):
        proposal = areas.propose_access_change(actor or self.owner, self.area.pk, readers,
                                              [self.invited.pk] if editors is None else editors)
        # Calling the integration hook twice proves its durable deduplication.
        notices.record_budget_proposal(actor or self.owner, proposal)
        return proposal

    def confirm(self, member, proposal):
        result = areas.confirm_access_change(member, proposal.pk, proposal.digest)
        notices.record_budget_confirmation(member, result)
        return result

    def send(self):
        payloads = []
        def sender(_subscription, _key, payload, _topic):
            payloads.append(payload)
            return SimpleNamespace(status_code=201)
        while claim := push.claim_delivery():
            push.deliver_claim(*claim, sender=sender)
        return payloads

    def test_proposal_generic_push_open_status_and_mark_read_without_calendar(self):
        Membership.objects.filter(pk=self.invited.pk).update(module_access={'calendar': False})
        self.invited.refresh_from_db()
        self.subscribe()
        proposal = self.proposal()
        notice = CalendarNotification.objects.get(recipient=self.invited.user, kind='budget_proposal')
        self.assertEqual(CalendarNotification.objects.count(), 1)
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread': 1})
        page = self.client.get('/app/varsler/')
        self.assertContains(page, 'Se og bekreft forslaget')
        self.assertContains(page, 'id="notification-bell"')
        self.assertNotContains(page, 'Sensitive budget label')
        self.assertRedirects(self.client.get(reverse('push_open', args=[notice.pk])), reverse('financial_proposal', args=[proposal.pk]), fetch_redirect_response=False)
        payloads = self.send()
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]['body'], notices.TEXT['budget_proposal'])
        self.assertNotIn('Sensitive', json.dumps(payloads))
        self.assertEqual(self.client.post(reverse('push_read', args=[notice.pk])).status_code, 302)
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread': 0})
        job = push.queue_test(SimpleNamespace(user=self.invited.user, session=self.client.session), PushSubscription.objects.get().pk)
        self.assertEqual(self.client.post('/push/receipt/', json.dumps({'delivery_id': str(job.pk)}), content_type='application/json').json()['state'], 'pending')
        self.send()
        receipt = self.client.post('/push/receipt/', json.dumps({'delivery_id': str(job.pk)}), content_type='application/json').json()
        self.assertTrue(receipt['provider_accepted'])
        self.assertFalse(receipt['os_display_confirmed'])

    def test_repeated_proposal_and_confirmation_do_not_duplicate_queue(self):
        self.subscribe()
        proposal = self.proposal()
        self.proposal()
        self.assertEqual(CalendarNotification.objects.count(), 1)
        self.assertEqual(PushDelivery.objects.count(), 1)
        proposal = self.confirm(self.owner, proposal)
        notices.record_budget_confirmation(self.owner, proposal)
        self.assertEqual(CalendarNotification.objects.count(), 1)
        proposal = self.confirm(self.invited, proposal)
        notices.record_budget_confirmation(self.invited, proposal)
        self.assertEqual(CalendarNotification.objects.filter(kind='budget_active').count(), 1)
        self.assertFalse(notices.visible_notifications(self.invited))
        self.assertEqual(len(notices.visible_notifications(self.owner)), 1)
        self.assertEqual(self.send(), [])  # obsolete approval jobs are cancelled
        self.assertEqual(PushDelivery.objects.get().last_error, 'access_revoked')

    def test_invitee_confirms_first_then_owner_activation_reaches_invitee(self):
        self.subscribe()
        proposal = self.proposal()
        proposal = self.confirm(self.invited, proposal)
        self.assertEqual(len(notices.visible_notifications(self.owner)), 1)
        proposal = self.confirm(self.owner, proposal)
        self.assertEqual([p['body'] for p in self.send()], [notices.TEXT['budget_active']])
        notice = CalendarNotification.objects.get(kind='budget_active', recipient=self.invited.user)
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).url, reverse('financial_proposal', args=[proposal.pk]))

    def test_admin_fallback_for_private_proposal_and_activation_has_no_finance_grant(self):
        proposal = self.proposal(editors=[])
        self.assertEqual(set(CalendarNotification.objects.values_list('recipient_id', flat=True)), {self.admin.user_id})
        proposal = self.confirm(self.admin, proposal)
        proposal = self.confirm(self.owner, proposal)
        self.assertFalse(FinancialAreaGrant.objects.filter(area=self.area, member=self.admin).exists())
        self.assertTrue(any(n.kind == 'budget_active' for n in notices.visible_notifications(self.admin)))

    def test_proposal_rollback_removes_outbox(self):
        self.subscribe()
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.proposal()
            raise RuntimeError('synthetic rollback')
        self.assertFalse(AreaAccessChange.objects.exists())
        self.assertFalse(CalendarNotification.objects.exists())
        self.assertFalse(PushDelivery.objects.exists())

    def test_stale_proposal_is_hidden_and_delivery_cancelled(self):
        self.subscribe()
        proposal = self.proposal()
        notice = CalendarNotification.objects.get()
        self.area.access_version += 1
        self.area.save(update_fields=['access_version'])
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread': 0})
        self.assertNotContains(self.client.get('/app/varsler/'), notices.TEXT['budget_proposal'])
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('push_read', args=[notice.pk])).status_code, 404)
        self.assertEqual(self.send(), [])

    def test_activation_rollback_keeps_grants_and_outbox_unchanged(self):
        self.subscribe()
        proposal = self.confirm(self.invited, self.proposal())
        before_notices = CalendarNotification.objects.count()
        before_jobs = PushDelivery.objects.count()
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.confirm(self.owner, proposal)
            raise RuntimeError('synthetic activation rollback')
        proposal.refresh_from_db()
        self.assertFalse(proposal.applied)
        self.assertFalse(FinancialAreaGrant.objects.filter(area=self.area, member=self.invited).exists())
        self.assertEqual(CalendarNotification.objects.count(), before_notices)
        self.assertEqual(PushDelivery.objects.count(), before_jobs)

    def test_revoked_active_grant_removes_list_open_and_delivery_access(self):
        self.subscribe()
        proposal = self.confirm(self.invited, self.proposal())
        self.confirm(self.owner, proposal)
        notice = CalendarNotification.objects.get(kind='budget_active')
        FinancialAreaGrant.objects.filter(area=self.area, member=self.invited).delete()
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).status_code, 404)
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread': 0})
        self.assertEqual(self.send(), [])

    def test_foreign_recipient_and_target_are_rejected(self):
        self.subscribe()
        proposal = self.proposal()
        notice = CalendarNotification.objects.get()
        self.client.force_login(self.foreign.user)
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('push_read', args=[notice.pk])).status_code, 404)
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread': 0})
        foreign_proposal = AreaAccessChange.objects.create(household=self.other_house, owner=self.foreign, digest='0'*64)
        CalendarNotification.objects.filter(pk=notice.pk).update(proposal=foreign_proposal)
        self.assertFalse(notices.visible_notifications(self.invited))
        self.assertEqual(self.send(), [])

    def test_inactive_user_never_receives_or_exposes_notification(self):
        self.subscribe()
        self.proposal()
        self.invited.user.is_active = False
        self.invited.user.save(update_fields=['is_active'])
        self.assertEqual(self.send(), [])

    def test_shopping_changes_are_shared_generic_atomic_and_idempotent(self):
        self.subscribe()
        listing = shopping.save_list(self.owner.user, 'Private shopping label', uuid.uuid4())
        key = uuid.uuid4()
        item = shopping.save_item(self.owner.user, listing.pk, listing.version, key, name='Sensitive item')
        shopping.save_item(self.owner.user, listing.pk, listing.version, key, name='Sensitive item')
        self.assertEqual(CalendarNotification.objects.count(), 3)
        self.assertFalse(CalendarNotification.objects.filter(recipient=self.foreign.user).exists())
        self.assertEqual(len(self.send()), 1)
        notice = CalendarNotification.objects.get(recipient=self.invited.user)
        self.assertEqual(notice.detail, notices.TEXT['shopping_changed'])
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).url, reverse('shopping_detail', args=[listing.pk]))
        listing.refresh_from_db()
        shopping.save_item(self.owner.user, listing.pk, listing.version, uuid.uuid4(), item_id=item.pk, name='Sensitive item')
        self.assertEqual(CalendarNotification.objects.count(), 3)  # unchanged value
        listing.refresh_from_db()
        with self.assertRaises(RuntimeError), transaction.atomic():
            shopping.save_item(self.owner.user, listing.pk, listing.version, uuid.uuid4(), name='Rolled back')
            raise RuntimeError('synthetic rollback')
        self.assertFalse(ShoppingItem.objects.filter(name='Rolled back').exists())
        self.assertEqual(CalendarNotification.objects.count(), 3)

    def test_shopping_revocation_hides_and_cancels_but_keeps_device_active(self):
        sub = self.subscribe()
        listing = shopping.save_list(self.owner.user, 'List', uuid.uuid4())
        shopping.save_item(self.owner.user, listing.pk, listing.version, uuid.uuid4(), name='Milk')
        notice = CalendarNotification.objects.get(recipient=self.invited.user)
        Membership.objects.filter(pk=self.invited.pk).update(module_access={'shopping': False})
        self.assertEqual(self.client.get(reverse('push_open', args=[notice.pk])).status_code, 404)
        self.assertNotContains(self.client.get('/app/varsler/'), notices.TEXT['shopping_changed'])
        self.assertEqual(self.send(), [])
        sub.refresh_from_db()
        self.assertTrue(sub.active)

    def test_bill_alerts_only_link_current_granted_budget_and_never_write(self):
        from budget.models import BillTemplate
        from budget import services
        with areas.area_scope(self.owner, self.area.pk):
            services.save_row(self.owner.user, BillTemplate(name='Sensitive bill', amount_ore=77777, first_due=date(2026, 10, 1)), admin=True)
            services.prepare_month(self.house, date(2026, 10, 1))
        self.assertEqual(notices.bill_alerts(self.invited, date(2026,10,1)), [])
        FinancialAreaGrant.objects.create(area=self.area, member=self.invited, role='reader')
        alerts = notices.bill_alerts(self.invited, date(2026,10,1))
        self.assertFalse(hasattr(self.invited, 'financial_area'))
        self.assertEqual(len(alerts), 1)
        self.assertIn('area='+str(self.area.pk), alerts[0]['url'])
        page = self.client.get('/app/varsler/?month=2026-10')
        self.assertContains(page, 'Regningsvarsler')
        self.assertNotContains(page, 'Sensitive bill')
        self.assertNotContains(page, '77777')

    def test_bill_alerts_preserve_existing_member_area_and_context(self):
        other = areas.create_area(self.invited, 'My private budget')
        FinancialAreaGrant.objects.create(area=self.area, member=self.invited, role='reader')
        with areas.area_scope(self.invited, other.pk):
            original = self.invited.financial_area
            notices.bill_alerts(self.invited, date(2026, 10, 1))
            self.assertIs(self.invited.financial_area, original)
            self.assertEqual(areas.current_area(self.invited).pk, other.pk)
