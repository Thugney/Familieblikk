import base64
import json
import uuid
import threading
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import http_ece
import requests
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from budget import calendar_services as cal, push_services as push
from budget.models import CalendarEvent, CalendarNotification, Household, Membership, PushDelivery, PushKey, PushSubscription


def response(code=201, **headers):
    result = requests.Response()
    result.status_code, result._content = code, b''
    result.headers.update(headers)
    return result


def unb64(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


class PushTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.house = Household.objects.create(name='Push testfamilie')
        cls.foreign = Household.objects.create(name='Separat testfamilie')
        cls.users, cls.members = [], []
        for index in range(4):
            user = get_user_model().objects.create_user(username=f'push{index}', email=f'push{index}@example.test', password='Synthetic-push-password-742')
            cls.users.append(user)
            cls.members.append(Membership.objects.create(user=user, household=cls.house if index < 3 else cls.foreign, role='admin' if index == 0 else 'member'))
        cls.no_family = get_user_model().objects.create_user(username='push-no-family')

    def setUp(self):
        self.client.force_login(self.users[1])
        self.browser_private = ec.generate_private_key(ec.SECP256R1())
        point = self.browser_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.info = {'endpoint': 'https://fcm.googleapis.com/fcm/send/synthetic-test-only', 'keys': {'p256dh': push._b64(point), 'auth': push._b64(b'0123456789abcdef')}}
        self.request = SimpleNamespace(user=self.users[1], session=self.client.session)
        push.ensure_key()

    def subscribe(self, client=None, **changes):
        client = client or self.client
        result = client.post('/push/device/', data=json.dumps({'action': 'subscribe', 'subscription': {**self.info, **changes}}), content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        return PushSubscription.objects.get(pk=result.json()['id'])

    def create(self, **changes):
        data = dict(title='Privat tittel bare i familien', start='2026-10-22', end='2026-10-22', all_day=True, start_time=None, end_time=None, place='Privat sted', note='Privat sensitivt notat', scope='shared', participants=[], recurrence='weekly', until=None, fold=None)
        result = cal.mutate(self.users[0], 'create', uuid.uuid4(), payload={**data, **changes})
        return CalendarEvent.objects.get(pk=result['id'])

    def reply(self, event, actor=1, status='yes', version=0, key=None):
        return cal.mutate(self.users[actor], 'respond', key or uuid.uuid4(), event_id=event.pk, original='2026-10-22', revision=event.revision, status=status, response_revision=version)

    def deliver(self, sender=None):
        claim = push.claim_delivery()
        self.assertIsNotNone(claim)
        return push.deliver_claim(*claim, sender=sender or (lambda *_: response()))

    def test_shared_series_notifies_other_family_members_once(self):
        self.subscribe(); event = self.create()
        self.assertEqual(set(CalendarNotification.objects.values_list('recipient_id', flat=True)), {self.users[1].pk, self.users[2].pk})
        self.assertEqual(PushDelivery.objects.count(), 1)
        self.assertEqual(list(CalendarNotification.objects.values_list('original_date', flat=True)), [date(2026, 10, 22)] * 2)
        self.assertTrue(all(n.event_id == event.pk for n in CalendarNotification.objects.all()))

    def test_selected_event_only_notifies_selected_members_excluding_creator(self):
        self.create(scope='selected', participants=[str(self.members[0].pk), str(self.members[1].pk)])
        self.assertEqual(list(CalendarNotification.objects.values_list('recipient_id', flat=True)), [self.users[1].pk])

    def test_edit_invites_only_new_effective_participants_once(self):
        self.subscribe()
        for edit_scope in ('one', 'future'):
            with self.subTest(scope=edit_scope):
                event = self.create(scope='selected', participants=[str(self.members[0].pk)])
                key = uuid.uuid4()
                payload = {**event.payload, 'participants':[str(self.members[0].pk), str(self.members[1].pk)]}
                args = dict(event_id=event.pk, original='2026-10-22', revision=event.revision, payload=payload, scope=edit_scope)
                cal.mutate(self.users[0], 'edit', key, **args)
                notice = CalendarNotification.objects.get(action_key=key)
                self.assertEqual(notice.recipient_id, self.users[1].pk)
                self.assertEqual(notice.event_id == event.pk, edit_scope == 'one')
                self.assertEqual(PushDelivery.objects.filter(notification=notice).count(), 1)
                cal.mutate(self.users[0], 'edit', key, **args)
                self.assertEqual(CalendarNotification.objects.filter(action_key=key).count(), 1)

    def test_selected_to_shared_invites_only_new_members_and_metadata_does_not_invite(self):
        event = self.create(scope='selected', participants=[str(self.members[0].pk), str(self.members[1].pk)])
        key = uuid.uuid4()
        cal.mutate(self.users[0], 'edit', key, event_id=event.pk, original='2026-10-22', revision=event.revision,
                   payload={**event.payload, 'scope':'shared', 'participants':[]})
        self.assertEqual(list(CalendarNotification.objects.filter(action_key=key).values_list('recipient_id', flat=True)), [self.users[2].pk])
        event.refresh_from_db()
        key = uuid.uuid4()
        cal.mutate(self.users[0], 'edit', key, event_id=event.pk, original='2026-10-22', revision=event.revision,
                   payload={**cal.occurrence(event, date(2026,10,22)), 'title':'Ny tittel'})
        self.assertFalse(CalendarNotification.objects.filter(action_key=key).exists())

    def test_future_edit_invites_one_occurrence_guest_into_series_but_one_edit_does_not(self):
        for scope in ('one', 'future'):
            with self.subTest(scope=scope):
                event = self.create(scope='selected', participants=[str(self.members[0].pk)])
                payload = {**event.payload, 'participants':[str(self.members[0].pk), str(self.members[1].pk)]}
                cal.mutate(self.users[0], 'edit', uuid.uuid4(), event_id=event.pk, original='2026-10-22', revision=event.revision, payload=payload)
                event.refresh_from_db()
                key = uuid.uuid4()
                cal.mutate(self.users[0], 'edit', key, event_id=event.pk, original='2026-10-22', revision=event.revision,
                           payload={**payload, 'title':'Oppdatert serie'}, scope=scope)
                recipients = list(CalendarNotification.objects.filter(action_key=key).values_list('recipient_id', flat=True))
                self.assertEqual(recipients, [self.users[1].pk] if scope == 'future' else [])

    def test_moved_future_invitation_opens_replacement_occurrence(self):
        event = self.create(scope='selected', participants=[str(self.members[0].pk)])
        key = uuid.uuid4()
        cal.mutate(self.users[0], 'edit', key, event_id=event.pk, original='2026-10-29', revision=event.revision,
                   payload={**event.payload, 'start':'2026-11-05', 'end':'2026-11-05',
                            'participants':[str(self.members[0].pk), str(self.members[1].pk)]}, scope='future')
        notice = CalendarNotification.objects.get(action_key=key, recipient=self.users[1])
        replacement = CalendarEvent.objects.get(series_key=event.series_key, payload__start='2026-11-05')
        self.assertNotEqual(replacement.pk, event.pk)
        self.assertEqual(notice.event_id, replacement.pk)
        self.assertEqual(notice.original_date, date(2026,11,5))
        opened = self.client.get(f'/push/open/{notice.pk}/')
        self.assertIn('cal_month=2026-11', opened.url)
        self.assertIn('event='+str(replacement.pk), opened.url)
        self.assertIn('original=2026-11-05', opened.url)
        page = self.client.get(opened.url)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(any(row['id'] == str(replacement.pk) and row['original'] == '2026-11-05' for row in page.context['events']))

    def test_response_notifies_other_participants_and_creator_even_when_not_participant(self):
        event = self.create(scope='selected', participants=[str(self.members[1].pk), str(self.members[2].pk)])
        self.reply(event)
        self.assertEqual(set(CalendarNotification.objects.filter(kind='yes').values_list('recipient_id', flat=True)), {self.users[0].pk, self.users[2].pk})
        self.assertEqual(CalendarNotification.objects.filter(kind='yes').count(), 2)

    def test_unchanged_answer_and_duplicate_request_never_enqueue(self):
        event = self.create(); key = uuid.uuid4()
        self.reply(event, key=key)
        before = CalendarNotification.objects.count()
        self.reply(event, key=key)
        self.reply(event, version=1)
        self.assertEqual(CalendarNotification.objects.count(), before)
        self.reply(event, status='no', version=2)
        self.assertEqual(CalendarNotification.objects.filter(kind='no').count(), 2)
        self.reply(event, status='none', version=3)
        self.assertEqual(CalendarNotification.objects.count(), before + 2)

    def test_duplicate_create_request_has_one_notification_per_recipient(self):
        event = self.create()
        request = event.household.calendarrequest_set.get()
        result = cal.mutate(self.users[0], 'create', request.key, payload=event.payload)
        self.assertEqual(result['id'], str(event.pk))
        self.assertEqual(CalendarNotification.objects.count(), 2)

    def test_rollback_removes_event_notifications_and_deliveries(self):
        self.subscribe()
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.create(); raise RuntimeError('abort')
        self.assertEqual(CalendarEvent.objects.count(), 0)
        self.assertEqual(CalendarNotification.objects.count(), 0)
        self.assertEqual(PushDelivery.objects.count(), 0)

    def test_invalid_participant_never_enqueues(self):
        with self.assertRaises(ValidationError): self.create(scope='selected', participants=[str(self.members[3].pk)])
        self.assertEqual(PushDelivery.objects.count(), 0)
        self.assertEqual(CalendarNotification.objects.count(), 0)

    def test_private_key_subscription_and_session_are_encrypted(self):
        sub = self.subscribe(); key = PushKey.objects.get()
        self.assertNotIn('PRIVATE KEY', key.private_ciphertext)
        self.assertNotIn('fcm.googleapis.com', sub.secret_ciphertext)
        self.assertNotIn(self.client.session.session_key, sub.secret_ciphertext)
        self.assertNotIn(self.info['keys']['auth'], sub.secret_ciphertext)
        self.assertEqual(push.decrypt(sub.secret_ciphertext)['subscription'], self.info)
        original = key.private_ciphertext
        self.assertEqual(push.ensure_key().private_ciphertext, original)
        with override_settings(SECRET_KEY='changed-key-must-fail'):
            with self.assertRaises(InvalidToken): push.ensure_key()

    def test_subscription_requires_authentication_membership_and_csrf(self):
        self.assertEqual(Client().post('/push/device/').status_code, 302)
        client = Client(enforce_csrf_checks=True); client.force_login(self.users[1])
        self.assertEqual(client.post('/push/device/', data='{}', content_type='application/json').status_code, 403)
        client.force_login(self.no_family)
        self.assertEqual(client.get('/push/config/').status_code, 403)
        self.assertEqual(self.client.get('/push/device/').status_code, 405)

    def test_endpoints_block_arbitrary_private_redirect_lookalike_and_credentials(self):
        bad = ['http://fcm.googleapis.com/fcm/send/x', 'https://127.0.0.1/x', 'https://192.168.20.135/x', 'https://fcm.googleapis.com.evil.test/fcm/send/x', 'https://evil.test/fcm/send/x', 'https://user:secret@fcm.googleapis.com/fcm/send/x', 'https://fcm.googleapis.com:444/fcm/send/x', 'https://fcm.googleapis.com/fcm/send/x#fragment', 'https://fcm.googleapis.com/redirect', 'https://web.push.apple.com\\@127.0.0.1/x']
        for endpoint in bad:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValidationError): push.validate_endpoint(endpoint)
        for endpoint in ['https://updates.push.services.mozilla.com/wpush/v2/test', 'https://web.push.apple.com/test', 'https://wns2.notify.windows.com/w/test']:
            self.assertEqual(push.validate_endpoint(endpoint), endpoint)
        with patch('budget.push_services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), self.assertRaises(ValidationError):
            push.validate_endpoint(self.info['endpoint'], resolve=True)

    def test_bad_crypto_keys_and_extra_fields_rejected(self):
        for data in [{**self.info, 'keys': {'p256dh': 'x', 'auth': 'y'}}, {**self.info, 'keys': {'p256dh': 'A' * 87, 'auth': self.info['keys']['auth']}}, {**self.info, 'user_id': self.users[0].pk}]:
            with self.assertRaises(ValidationError): push.validate_subscription(data)

    def test_enable_never_sends_synchronously(self):
        with patch('budget.push_services.transport', side_effect=AssertionError('calendar must not call provider')):
            self.subscribe(); self.create()
        self.assertEqual(PushDelivery.objects.get().state, 'pending')

    def test_reenable_same_session_retains_jobs_and_account_change_cancels_them(self):
        sub = self.subscribe(); self.create(); self.subscribe()
        self.assertEqual(PushDelivery.objects.get().state, 'pending')
        other = Client(); other.force_login(self.users[3]); self.subscribe(other)
        sub.refresh_from_db()
        self.assertEqual(sub.household_id, self.foreign.pk)
        self.assertEqual(PushDelivery.objects.get().state, 'cancelled')

    def test_rebind_removes_former_sessions_test_receipts_and_preserves_calendar_history(self):
        for recipient in (1, 2, 3):
            with self.subTest(new_user=recipient):
                self.client = Client(); self.client.force_login(self.users[1])
                sub = self.subscribe(); self.create()
                calendar_ids = set(sub.deliveries.filter(notification__isnull=False).values_list('pk',flat=True))
                notice_ids = set(CalendarNotification.objects.values_list('pk',flat=True))
                tests = [PushDelivery.objects.create(subscription=sub, state=state) for state in ('pending','sending','sent','failed','cancelled')]
                self.subscribe()
                self.assertTrue(all(PushDelivery.objects.filter(pk=row.pk).exists() for row in tests))
                other = Client(); other.force_login(self.users[recipient]); self.subscribe(other)
                self.assertFalse(PushDelivery.objects.filter(pk__in=[row.pk for row in tests]).exists())
                self.assertEqual(set(PushDelivery.objects.filter(pk__in=calendar_ids).values_list('pk',flat=True)), calendar_ids)
                self.assertEqual(set(CalendarNotification.objects.values_list('pk',flat=True)), notice_ids)
                for row in tests:
                    result = other.post('/push/receipt/', data=json.dumps({'delivery_id':str(row.pk)}), content_type='application/json')
                    self.assertEqual(result.status_code, 404)

    def test_logout_cancels_pending_delivery(self):
        sub = self.subscribe(); self.create()
        self.client.post('/utlogging/')
        sub.refresh_from_db(); self.assertFalse(sub.active)
        self.assertEqual(PushDelivery.objects.get().state, 'cancelled')
        self.assertIsNone(push.claim_delivery())

    def test_expired_session_password_change_and_inactive_user_stop_delivery(self):
        for change in ('expiry', 'password', 'inactive', 'membership'):
            with self.subTest(change=change):
                self.users[1].refresh_from_db()
                self.client = Client()
                self.client.force_login(self.users[1]); sub = self.subscribe()
                job = PushDelivery.objects.create(subscription=sub)
                if change == 'expiry': Session.objects.filter(session_key=self.client.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))
                elif change == 'password':
                    self.users[1].set_password('Replacement-synthetic-password'); self.users[1].save()
                elif change == 'inactive': get_user_model().objects.filter(pk=self.users[1].pk).update(is_active=False)
                else: Membership.objects.filter(pk=self.members[1].pk).update(household=self.foreign)
                self.assertEqual(self.deliver(lambda *_: self.fail('invalid session must not send')), 'cancelled')
                job.refresh_from_db(); self.assertEqual(job.last_error, 'session_expired')
                get_user_model().objects.filter(pk=self.users[1].pk).update(is_active=True)
                Membership.objects.filter(pk=self.members[1].pk).update(household=self.house)

    def test_subscription_rebound_to_other_household_never_receives_old_notification(self):
        sub = self.subscribe(); self.create()
        PushSubscription.objects.filter(pk=sub.pk).update(household=self.foreign)
        self.assertEqual(self.deliver(lambda *_: self.fail('foreign household must not send')), 'cancelled')

    def test_stale_notification_inserted_after_rebind_does_not_revoke_new_device(self):
        self.create(); notice = CalendarNotification.objects.get(recipient=self.users[1])
        sub = self.subscribe()
        foreign = Client(); foreign.force_login(self.users[3]); self.subscribe(foreign)
        sub.refresh_from_db(); rebound_secret = sub.secret_ciphertext
        job = PushDelivery.objects.create(notification=notice, subscription=sub)
        self.assertEqual(self.deliver(lambda *_: self.fail('stale identity must not send')), 'cancelled')
        sub.refresh_from_db(); job.refresh_from_db()
        self.assertTrue(sub.active); self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.secret_ciphertext, rebound_secret)
        self.assertTrue(push.valid_binding(sub))
        self.assertEqual(job.last_error, 'binding_changed')

    def test_delivery_sends_generic_content_and_stable_topic_once(self):
        self.subscribe(); self.create(); captured = []
        self.assertEqual(self.deliver(lambda *args: (captured.append(args), response())[1]), 'sent')
        info, pem, payload, topic = captured[0]
        self.assertEqual(info, self.info); self.assertIn('PRIVATE KEY', pem)
        self.assertEqual(payload['body'], push.GENERIC_TEXT['created'])
        self.assertNotIn('Privat', json.dumps(payload))
        self.assertTrue(payload['url'].startswith('/push/open/'))
        self.assertLessEqual(len(topic), 32)
        self.assertIsNone(push.claim_delivery())

    def test_real_webpush_encrypts_payload_and_signs_vapid_without_external_transport(self):
        self.subscribe(); self.create(); captured = []
        def send(_session, prepared, **kwargs):
            self.assertFalse(kwargs.get('allow_redirects'))
            captured.append(prepared)
            return response()
        with patch('budget.push_services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch.object(requests.Session, 'send', send):
            self.assertEqual(self.deliver(push.transport), 'sent')
        prepared = captured[0]
        self.assertEqual(prepared.headers['Content-Encoding'], 'aes128gcm')
        self.assertEqual(prepared.headers['TTL'], '86400')
        self.assertEqual(prepared.headers['Urgency'], 'high')
        decoded = http_ece.decrypt(prepared.body, private_key=self.browser_private, auth_secret=unb64(self.info['keys']['auth']), version='aes128gcm')
        payload = json.loads(decoded)
        self.assertEqual(payload['body'], push.GENERIC_TEXT['created'])
        self.assertNotIn('Privat', decoded.decode())
        authorization = prepared.headers['Authorization']
        jwt = authorization.split('t=', 1)[1].split(',', 1)[0]
        head, body, signature = jwt.split('.')
        claims = json.loads(unb64(body)); self.assertEqual(claims['aud'], 'https://fcm.googleapis.com')
        raw = unb64(signature); r, s = int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')
        key = PushKey.objects.get()
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64(key.public_key))
        public.verify(utils.encode_dss_signature(r, s), f'{head}.{body}'.encode(), ec.ECDSA(hashes.SHA256()))

    def test_provider_429_5xx_and_network_failures_retry_with_bound(self):
        sub = self.subscribe(); job = PushDelivery.objects.create(subscription=sub)
        for code in (429, 503, None):
            def send(*_):
                if code is None: raise requests.Timeout('secret-endpoint-must-not-be-stored')
                return response(code, **{'Retry-After': '120'})
            self.assertEqual(self.deliver(send), 'pending')
            job.refresh_from_db(); self.assertNotIn('secret', job.last_error)
            self.assertGreater(job.available_at, timezone.now() + timedelta(seconds=20))
            job.available_at = timezone.now(); job.save(update_fields=['available_at'])
        job.attempts = push.MAX_ATTEMPTS - 1; job.save(update_fields=['attempts'])
        self.assertEqual(self.deliver(lambda *_: response(503)), 'failed')
        sub.refresh_from_db(); self.assertEqual(sub.state, 'failed')
        self.assertIsNone(push.claim_delivery())

    def test_real_pywebpush_provider_exceptions_persist_expiry_retry_after_and_exhaustion(self):
        for code in (410, 429, 503):
            with self.subTest(code=code):
                sub = self.subscribe(); job = PushDelivery.objects.create(subscription=sub)
                captured = []
                def send(_session, prepared, **kwargs):
                    captured.append(prepared)
                    self.assertFalse(kwargs.get('allow_redirects'))
                    return response(code, **{'Retry-After': '120'})
                started = timezone.now()
                with patch('budget.push_services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch.object(requests.Session, 'send', send):
                    self.assertEqual(self.deliver(push.transport), 'cancelled' if code == 410 else 'pending')
                self.assertEqual(captured[0].headers['Content-Encoding'], 'aes128gcm')
                self.assertIn('vapid ', captured[0].headers['Authorization'])
                job.refresh_from_db(); sub.refresh_from_db()
                self.assertEqual(job.attempts, 1)
                if code == 410:
                    self.assertFalse(sub.active); self.assertEqual(sub.state, 'expired')
                    self.assertEqual(job.last_error, 'subscription_expired')
                else:
                    self.assertTrue(sub.active); self.assertEqual(sub.state, 'retrying')
                    self.assertEqual(job.last_error, 'provider')
                    self.assertGreaterEqual(job.available_at, started + timedelta(seconds=120))
                    self.assertLess(job.available_at, timezone.now() + timedelta(seconds=121))
                    job.attempts, job.available_at = push.MAX_ATTEMPTS - 1, timezone.now()
                    job.save(update_fields=['attempts', 'available_at'])
                    with patch('budget.push_services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch.object(requests.Session, 'send', send):
                        self.assertEqual(self.deliver(push.transport), 'failed')
                    sub.refresh_from_db(); self.assertEqual(sub.state, 'failed')

    def test_queue_partial_indexes_exist_after_migration(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename='budget_pushdelivery' AND indexname IN ('push_pending_queue', 'push_sending_lease')")
            indexes = dict(cursor.fetchall())
        self.assertEqual(set(indexes), {'push_pending_queue', 'push_sending_lease'})
        self.assertIn('(available_at, created_at)', indexes['push_pending_queue'])
        self.assertIn("state)::text = 'pending'", indexes['push_pending_queue'])
        self.assertIn('(lease_until)', indexes['push_sending_lease'])
        self.assertIn("state)::text = 'sending'", indexes['push_sending_lease'])

    def test_404_410_disables_subscription_and_other_4xx_fails(self):
        for code in (404, 410, 403, 302):
            sub = self.subscribe(); PushDelivery.objects.create(subscription=sub)
            self.assertEqual(self.deliver(lambda *_: response(code)), 'cancelled' if code in (404, 410) else 'failed')
            sub.refresh_from_db(); self.assertEqual(sub.active, code not in (404, 410))

    def test_process_death_lease_recovery_fences_old_worker(self):
        sub = self.subscribe(); row = PushDelivery.objects.create(subscription=sub)
        old = push.claim_delivery(); self.assertIsNone(push.claim_delivery())
        PushDelivery.objects.filter(pk=row.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        new = push.claim_delivery(); self.assertNotEqual(new[1], old[1])
        self.assertEqual(push.deliver_claim(*old, sender=lambda *_: self.fail('stale worker sends')), 'sending')
        self.assertEqual(push.deliver_claim(*new, sender=lambda *_: response()), 'sent')

    def test_stale_jobs_fail_without_transport(self):
        sub = self.subscribe(); job = PushDelivery.objects.create(subscription=sub)
        PushDelivery.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.deliver(lambda *_: self.fail('expired job sends')), 'failed')

    def test_test_notification_is_only_own_current_device_and_rate_limited(self):
        sub = self.subscribe()
        result = self.client.post('/push/device/', data=json.dumps({'action': 'test', 'id': str(sub.pk)}), content_type='application/json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(CalendarNotification.objects.count(), 0)
        self.assertEqual(self.client.post('/push/device/', data=json.dumps({'action': 'test', 'id': str(sub.pk)}), content_type='application/json').status_code, 400)
        foreign = Client(); foreign.force_login(self.users[3])
        self.assertEqual(foreign.post('/push/device/', data=json.dumps({'action': 'test', 'id': str(sub.pk)}), content_type='application/json').status_code, 400)
        captured = []
        self.deliver(lambda *args: (captured.append(args), response())[1])
        self.assertEqual(captured[0][2]['body'], push.GENERIC_TEXT['test'])

    def test_notification_overview_and_read_open_are_recipient_and_tenant_bound(self):
        self.create(); notice = CalendarNotification.objects.get(recipient=self.users[1])
        self.assertContains(self.client.get('/app/varsler/'), notice.detail)
        self.assertContains(self.client.get('/app/varsler/'), 'Regningsvarsler')
        self.assertIn('private, no-store', self.client.get('/app/varsler/')['Cache-Control'])
        self.assertEqual(self.client.get(f'/push/read/{notice.pk}/').status_code, 405)
        self.assertEqual(self.client.post(f'/push/read/{notice.pk}/').status_code, 302)
        notice.refresh_from_db(); self.assertIsNotNone(notice.read_at)
        opened = self.client.get(f'/push/open/{notice.pk}/')
        self.assertIn('cal_month=2026-10', opened.url); self.assertIn(str(notice.event_id), opened.url)
        self.client.force_login(self.users[3])
        self.assertEqual(self.client.get(f'/push/open/{notice.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/push/read/{notice.pk}/').status_code, 404)
        self.assertNotContains(self.client.get('/app/varsler/'), notice.detail)

    def test_config_only_returns_public_key_and_status_never_returns_secrets(self):
        sub = self.subscribe()
        config = self.client.get('/push/config/'); self.assertEqual(set(config.json()), {'public_key'})
        status = self.client.post('/push/device/', data=json.dumps({'action': 'status', 'endpoint': self.info['endpoint']}), content_type='application/json')
        self.assertEqual(status.json()['state'], 'active')
        self.assertNotIn(self.info['endpoint'], status.content.decode())
        self.assertNotIn(self.info['keys']['auth'], status.content.decode())
        self.client.post('/push/device/', data=json.dumps({'action': 'disable', 'endpoint': self.info['endpoint']}), content_type='application/json')
        sub.refresh_from_db(); self.assertFalse(sub.active)

    def test_receipt_is_private_csrf_protected_and_only_current_sessions_test_delivery(self):
        sub = self.subscribe(); job = push.queue_test(self.request, sub.pk)
        def receipt(client=self.client, delivery=job.pk):
            return client.post('/push/receipt/', data=json.dumps({'delivery_id':str(delivery)}), content_type='application/json')
        self.assertEqual(self.client.get('/push/receipt/').status_code, 405)
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.users[1])
        self.assertEqual(receipt(csrf).status_code, 403)
        another_session = Client(); another_session.force_login(self.users[1])
        foreign = Client(); foreign.force_login(self.users[3])
        self.assertEqual(receipt(another_session).status_code, 404)
        self.assertEqual(receipt(foreign).status_code, 404)
        self.create()
        actual = PushDelivery.objects.exclude(notification=None).get()
        self.assertEqual(receipt(delivery=actual.pk).status_code, 404)
        for state, attempts, expected in [('pending',0,'pending'),('sending',1,'sending'),('pending',1,'retry'),('failed',8,'failed'),('cancelled',0,'cancelled'),('sent',1,'sent')]:
            PushDelivery.objects.filter(pk=job.pk).update(state=state, attempts=attempts)
            result = receipt()
            self.assertEqual(result.json()['state'], expected)
            self.assertEqual(result.json()['provider_accepted'], state == 'sent')
            self.assertFalse(result.json()['os_display_confirmed'])
            self.assertIn('no-store', result['Cache-Control'])
            self.assertNotIn(self.info['endpoint'], result.content.decode())
            self.assertNotIn(self.info['keys']['auth'], result.content.decode())
        self.client.logout()
        self.assertEqual(receipt().status_code, 302)

    def test_unread_badge_and_summary_use_only_current_recipient_and_household(self):
        self.create()
        notice = CalendarNotification.objects.get(recipient=self.users[1])
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread':1})
        for url in ['/app/oversikt/', '/app/kalender/', '/app/familie/', '/ny/entry/']:
            page = self.client.get(url)
            self.assertContains(page, 'id="notification-bell"')
            self.assertContains(page, 'Varsler, 1 uleste')
            self.assertContains(page, 'data-push-config=')
            self.assertContains(page, '/static/budget/push.js')
        CalendarNotification.objects.create(household=self.foreign, recipient=self.users[1], original_date=date(2026,10,22), kind='created', action_key=uuid.uuid4(), detail='Foreign household')
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread':1})
        result = self.client.post(f'/push/read/{notice.pk}/')
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread':0})
        self.assertContains(self.client.get('/app/oversikt/'), 'Varsler, ingen uleste')
        self.assertIn('no-store', self.client.get('/push/summary/')['Cache-Control'])
        self.client.force_login(self.users[3])
        self.assertEqual(self.client.get('/push/summary/').json(), {'unread':0})

    def test_old_series_notification_explains_future_split_and_deleted_event(self):
        for change in ('split', 'deleted', 'missing'):
            with self.subTest(change=change):
                event = self.create()
                notice = CalendarNotification.objects.get(event=event, recipient=self.users[1])
                if change == 'split':
                    cal.mutate(self.users[0], 'edit', uuid.uuid4(), event_id=event.pk, original='2026-10-22', revision=event.revision, payload={**event.payload, 'title':'Ny delserie'}, scope='future')
                elif change == 'deleted':
                    CalendarEvent.objects.filter(pk=event.pk).update(deleted=True)
                else:
                    CalendarNotification.objects.filter(pk=notice.pk).update(event=None)
                opened = self.client.get(f'/push/open/{notice.pk}/', follow=True)
                self.assertEqual(opened.status_code, 200)
                self.assertContains(opened, 'Avtalen er endret eller slettet.')
                self.assertContains(opened, 'tidligere versjon som ikke lenger finnes i kalenderen')


class PushConcurrencyTests(TransactionTestCase):
    def test_two_workers_claim_each_job_only_once(self):
        house = Household.objects.create(name='Concurrent synthetic family')
        user = get_user_model().objects.create_user(username='worker-test')
        sub = PushSubscription.objects.create(user=user, household=house, endpoint_digest='a'*64, session_digest='b'*64, secret_ciphertext=push.encrypt({}))
        row = PushDelivery.objects.create(subscription=sub)
        ready, results, errors = threading.Barrier(3), [], []
        def worker():
            close_old_connections()
            try:
                ready.wait(timeout=10)
                results.append(push.claim_delivery())
            except Exception as exc: errors.append(type(exc).__name__)
            finally: close_old_connections()
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        ready.wait(timeout=10)
        for thread in threads: thread.join(timeout=15)
        self.assertFalse(errors); self.assertTrue(all(not thread.is_alive() for thread in threads))
        claims = [result for result in results if result]
        self.assertEqual(len(claims), 1); self.assertEqual(claims[0][0], row.pk)
