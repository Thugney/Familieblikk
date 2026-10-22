"""Web Push encryption, opt-in subscriptions, transactional outbox and bounded retries.

No provider I/O occurs in a calendar request. Secrets are never included in errors.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import socket
import uuid
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from .models import CalendarNotification, Household, Membership, PushDelivery, PushKey, PushSubscription
from . import access

MAX_ATTEMPTS = 8
MAX_AGE = timedelta(hours=24)
GENERIC_TEXT = {'created': 'En ny kalenderavtale er lagt til.', 'yes': 'Et familiemedlem har godtatt en avtale.', 'no': 'Et familiemedlem har avslått en avtale.', 'test': 'Testvarsel fra Familieblikk.'}


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _cipher():
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'familieblikk-webpush-v1', info=b'database-secrets').derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value):
    return _cipher().encrypt(json.dumps(value, separators=(',', ':')).encode()).decode()


def decrypt(value):
    return json.loads(_cipher().decrypt(value.encode()).decode())


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


@transaction.atomic
def ensure_key():
    # Advisory transaction lock also serializes first boot before a row exists.
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [721945638])
    key = PushKey.objects.filter(pk=1).first()
    if key:
        # Fail closed if a changed DJANGO_SECRET_KEY cannot decrypt the existing key.
        decrypt(key.private_ciphertext)
        return key
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = _b64(private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return PushKey.objects.create(pk=1, public_key=public, private_ciphertext=encrypt(pem))


def validate_endpoint(endpoint, resolve=False):
    if not isinstance(endpoint, str) or len(endpoint) > 4096 or any(ord(x) < 33 or ord(x) > 126 for x in endpoint):
        raise ValidationError('Ugyldig pushadresse.')
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ''
        valid_host = host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com') or host.endswith('.push.apple.com') or host.endswith('.notify.windows.com')
        if url.scheme != 'https' or not valid_host or url.port not in (None, 443) or url.username or url.password or url.fragment or not url.path.startswith('/') or url.path == '/':
            raise ValueError
        if host == 'fcm.googleapis.com' and not url.path.startswith('/fcm/send/'): raise ValueError
        if host == 'updates.push.services.mozilla.com' and not url.path.startswith('/wpush/'): raise ValueError
    except ValueError:
        raise ValidationError('Bare nettleserens offisielle HTTPS-pushtjeneste kan brukes.') from None
    if resolve:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ValidationError('Pushtjenesten må ha en offentlig nettadresse.')
    return endpoint


def validate_subscription(data):
    if not isinstance(data, dict) or set(data) - {'endpoint', 'keys', 'expirationTime'}: raise ValidationError('Ugyldig nettleserabonnement.')
    endpoint = validate_endpoint(data.get('endpoint'))
    keys = data.get('keys')
    if not isinstance(keys, dict) or set(keys) != {'p256dh', 'auth'}: raise ValidationError('Abonnementet mangler krypteringsnøkler.')
    try:
        for name, value in keys.items():
            if not isinstance(value, str) or len(value) > 100 or not value or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in value): raise ValueError
        point = base64.urlsafe_b64decode(keys['p256dh'] + '=' * (-len(keys['p256dh']) % 4))
        auth = base64.urlsafe_b64decode(keys['auth'] + '=' * (-len(keys['auth']) % 4))
        if len(point) != 65 or len(auth) != 16: raise ValueError
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except (ValueError, TypeError): raise ValidationError('Abonnementet har ugyldige krypteringsnøkler.') from None
    return {'endpoint': endpoint, 'keys': keys}


def valid_binding(subscription, secret=None):
    if not subscription.active: return False
    secret = secret or decrypt(subscription.secret_ciphertext)
    user = get_user_model().objects.filter(pk=subscription.user_id, is_active=True).first()
    if not user: return False
    member = Membership.objects.filter(user_id=user.pk, household_id=subscription.household_id).first()
    if not member or not access.allows(member, 'calendar'): return False
    session = Session.objects.filter(session_key=secret['session_key'], expire_date__gt=timezone.now()).first()
    if not session: return False
    data = session.get_decoded()
    return str(data.get('_auth_user_id')) == str(user.pk) and data.get('_auth_user_backend') in settings.AUTHENTICATION_BACKENDS and constant_time_compare(data.get('_auth_user_hash', ''), user.get_session_auth_hash())


@transaction.atomic
def subscribe(request, data):
    member = access.require(access.lock_member(request.user), {'calendar'})
    Household.objects.select_for_update().get(pk=member.household_id)
    info = validate_subscription(data)
    if not request.session.session_key: raise PermissionDenied('Logg inn på nytt før du aktiverer varsler.')
    endpoint_hash = digest(info['endpoint'])
    existing = PushSubscription.objects.select_for_update().filter(endpoint_digest=endpoint_hash).first()
    # A browser may explicitly rebind its endpoint after another account logs in;
    # cancel old jobs, so a new session can never receive the previous identity's queue.
    if existing and (existing.user_id != request.user.pk or existing.household_id != member.household_id or existing.session_digest != digest(request.session.session_key)):
        existing.deliveries.filter(state__in=['pending', 'sending']).update(state='cancelled', lease_token=None, lease_until=None)
        # Diagnostic jobs belong to the former session, not to a reusable endpoint.
        existing.deliveries.filter(notification__isnull=True).delete()
    if not existing: existing = PushSubscription(endpoint_digest=endpoint_hash)
    existing.user = request.user
    existing.household = member.household
    existing.session_digest = digest(request.session.session_key)
    existing.secret_ciphertext = encrypt({'subscription': info, 'session_key': request.session.session_key})
    existing.active, existing.state = True, 'active'
    existing.save()
    return existing


@transaction.atomic
def disable_session(request, endpoint=None):
    if not request.session.session_key or not request.user.is_authenticated: return
    rows = PushSubscription.objects.select_for_update().filter(user=request.user, session_digest=digest(request.session.session_key))
    if endpoint: rows = rows.filter(endpoint_digest=digest(endpoint))
    for row in rows:
        row.active, row.state = False, 'disabled'
        row.save(update_fields=['active', 'state', 'updated_at'])
        PushDelivery.objects.filter(subscription=row, state__in=['pending', 'sending']).update(state='cancelled', lease_token=None, lease_until=None)


def record_calendar_action(actor, member, event, action_key, kind, original, payload, recipient_members=None):
    """Called inside calendar mutate's household lock and transaction."""
    people = access.calendar_members(member.household)
    if payload['scope'] != 'shared': people = [p for p in people if str(p.pk) in payload['participants']]
    if recipient_members is not None: people = [p for p in people if p.pk in recipient_members]
    users = {person.user_id: person.user for person in people}
    if kind != 'created': users[event.created_by_id] = event.created_by
    users.pop(actor.pk, None)
    actor_label = actor.get_full_name() or actor.email
    verb = {'created': 'opprettet', 'yes': 'godtok', 'no': 'avslo'}[kind]
    for user_id in users:
        # The original creator may no longer belong to this household.
        recipient = Membership.objects.filter(user_id=user_id, household=member.household).first()
        if not recipient or not access.allows(recipient, 'calendar'): continue
        notice = CalendarNotification.objects.create(household=member.household, recipient_id=user_id, event=event, original_date=original, kind=kind, action_key=action_key, detail=f'{actor_label} {verb} «{payload["title"]}».'[:400])
        PushDelivery.objects.bulk_create([PushDelivery(notification=notice, subscription=sub) for sub in PushSubscription.objects.filter(user_id=user_id, household=member.household, active=True)])


@transaction.atomic
def queue_test(request, subscription_id):
    member = access.require(access.lock_member(request.user), {'calendar'})
    sub = PushSubscription.objects.select_for_update().filter(pk=subscription_id, user=request.user, household=member.household, session_digest=digest(request.session.session_key or ''), active=True).first()
    if not sub or not valid_binding(sub): raise ValidationError('Aktiver varsler på denne enheten først.')
    if sub.last_test_at and sub.last_test_at > timezone.now() - timedelta(seconds=60): raise ValidationError('Vent ett minutt mellom testvarsler.')
    sub.last_test_at = timezone.now(); sub.save(update_fields=['last_test_at'])
    return PushDelivery.objects.create(subscription=sub)


def notification_url(notification):
    return reverse('push_open', args=[notification.pk]) if notification else reverse('page', args=['varsler'])


class NoRedirectSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def request(self, method, url, **kwargs):
        validate_endpoint(url, resolve=True)
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def transport(subscription_info, private_pem, payload, topic):
    vapid = Vapid.from_pem(private_pem.encode())
    with NoRedirectSession() as session:
        return webpush(subscription_info=subscription_info, data=json.dumps(payload, separators=(',', ':')), vapid_private_key=vapid, vapid_claims={'sub': 'https://blikk.betilab.com'}, content_encoding='aes128gcm', ttl=86400, timeout=10, headers={'Topic': topic, 'Urgency': 'high'}, requests_session=session)


@transaction.atomic
def claim_delivery():
    now = timezone.now()
    row = PushDelivery.objects.select_for_update(skip_locked=True).filter(Q(state='pending', available_at__lte=now) | Q(state='sending', lease_until__lte=now)).order_by('available_at', 'created_at').first()
    if not row: return None
    row.state, row.lease_token, row.lease_until = 'sending', uuid.uuid4(), now + timedelta(minutes=2)
    row.save(update_fields=['state', 'lease_token', 'lease_until'])
    return row.pk, row.lease_token


def retry_delay(response, attempts):
    seconds = min(30 * 2 ** (attempts - 1), 3600)
    raw = response.headers.get('Retry-After', '') if response is not None else ''
    try:
        retry = int(raw) if raw.isdigit() else int((parsedate_to_datetime(raw) - timezone.now()).total_seconds())
        seconds = max(seconds, min(max(retry, 0), 3600))
    except (TypeError, ValueError, OverflowError): pass
    return timedelta(seconds=seconds)


@transaction.atomic
def deliver_claim(delivery_id, token, sender=None):
    # Lock subscription through the bounded HTTP call: disabling/logout wins before
    # a future delivery can start. Row lock + fencing token exclude two workers.
    initial = PushDelivery.objects.filter(pk=delivery_id).values('subscription_id', 'subscription__household_id').first()
    if not initial: return 'cancelled'
    # Keep the same first lock as revocation through provider acceptance. A
    # provider-accepted notification cannot subsequently be recalled.
    Household.objects.select_for_update().get(pk=initial['subscription__household_id'])
    # NO KEY UPDATE still serializes disable/rebind, while allowing concurrent
    # calendar outbox inserts to validate their subscription foreign key.
    sub = PushSubscription.objects.select_for_update(no_key=True).get(pk=initial['subscription_id'])
    if sub.household_id != initial['subscription__household_id']:
        return 'cancelled'
    row = PushDelivery.objects.select_for_update(of=('self',)).select_related('notification').get(pk=delivery_id)
    if row.state != 'sending' or row.lease_token != token: return row.state
    now = timezone.now()
    notice = row.notification
    recipient_member = Membership.objects.filter(user_id=sub.user_id, household_id=sub.household_id).first()
    if notice and (notice.recipient_id != sub.user_id or notice.household_id != sub.household_id):
        # A delayed insert can refer to this endpoint's former identity.
        row.state, row.last_error = 'cancelled', 'binding_changed'
    elif recipient_member and not access.allows(recipient_member, 'calendar'):
        row.state, row.last_error = 'cancelled', 'access_revoked'
    elif row.created_at < now - MAX_AGE or row.attempts >= MAX_ATTEMPTS:
        row.state, row.last_error = 'failed', 'expired'
        sub.state = 'failed'; sub.save(update_fields=['state', 'updated_at'])
    else:
        try:
            secret = decrypt(sub.secret_ciphertext)
            valid = valid_binding(sub, secret)
        except Exception:
            valid = False
        if not valid:
            sub.active, sub.state = False, 'expired'
            sub.save(update_fields=['active', 'state', 'updated_at'])
            row.state, row.last_error = 'cancelled', 'session_expired'
        else:
            row.attempts += 1
            payload = {'title': 'Familieblikk', 'body': GENERIC_TEXT[notice.kind if notice else 'test'], 'url': notification_url(notice), 'tag': str(row.pk)}
            response, code, failure = None, None, ''
            try:
                key = PushKey.objects.get(pk=1)
                response = (sender or transport)(secret['subscription'], decrypt(key.private_ciphertext), payload, _b64(row.pk.bytes))
                code = response.status_code
            except WebPushException as exc:
                response = exc.response
                code = response.status_code if response is not None else None
                failure = 'provider'
            except Exception:
                failure = 'transport'
            if code is not None and 200 <= code < 300:
                row.state, row.sent_at, row.last_error = 'sent', timezone.now(), ''
                sub.state = 'active'; sub.save(update_fields=['state', 'updated_at'])
            elif code in (404, 410):
                sub.active, sub.state = False, 'expired'; sub.save(update_fields=['active', 'state', 'updated_at'])
                row.state, row.last_error = 'cancelled', 'subscription_expired'
            elif code is None or code == 429 or code >= 500:
                row.state = 'failed' if row.attempts >= MAX_ATTEMPTS else 'pending'
                row.available_at = timezone.now() + retry_delay(response, row.attempts)
                row.last_error = failure or 'provider_retry'
                sub.state = 'failed' if row.state == 'failed' else 'retrying'; sub.save(update_fields=['state', 'updated_at'])
            else:
                row.state, row.last_error = 'failed', 'provider_rejected'
                sub.state = 'failed'; sub.save(update_fields=['state', 'updated_at'])
    row.lease_token = row.lease_until = None
    row.save()
    return row.state
