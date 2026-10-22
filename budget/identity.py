import hashlib
import hmac
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone
from .models import Audit, Household, Invitation, LoginCode, LoginRequest, Membership, PasswordAttempt


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def lock_identity_email(email):
    key = int(hashlib.sha256(('identity-email:' + email.strip().lower()).encode()).hexdigest()[:15], 16)
    with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_xact_lock(%s)', [key])


@transaction.atomic
def send_code(email, ip):
    email = email.strip().lower()
    now = timezone.now()
    old = LoginCode.objects.select_for_update().filter(email=email).first()
    ip_hash = digest(ip)
    if old and old.sent_at > now - timedelta(seconds=60): return
    if LoginRequest.objects.filter(ip_digest=ip_hash, sent_at__gt=now - timedelta(hours=1)).count() >= 20: return
    if LoginRequest.objects.filter(email_digest=digest(email), sent_at__gt=now - timedelta(hours=1)).count() >= 5: return
    code = f'{secrets.randbelow(1000000):06d}'
    LoginCode.objects.update_or_create(email=email, defaults={'digest': digest(email + ':' + code), 'sent_at': now, 'expires_at': now + timedelta(minutes=10), 'attempts': 0, 'consumed': False, 'ip_digest': ip_hash})
    LoginRequest.objects.create(email_digest=digest(email), ip_digest=ip_hash, sent_at=now)
    send_mail('Din engangskode til Familieblikk', f'Din kode er {code}. Den gjelder i 10 minutter. Hvis du ikke ba om koden, se bort fra meldingen.', settings.DEFAULT_FROM_EMAIL, [email])


def verify_code(request, email, code):
    # Feilforsøk må lagres også når koden avvises.
    email = email.strip().lower()
    user = None
    with transaction.atomic():
        lock_identity_email(email)
        row = LoginCode.objects.select_for_update().filter(email=email).first()
        if row and not row.consumed and row.attempts < 5 and row.expires_at > timezone.now():
            row.attempts += 1
            if hmac.compare_digest(row.digest, digest(email + ':' + code)):
                row.consumed = True
                user = get_user_model().objects.filter(email__iexact=email).first()
                if user is None:
                    username = 'email_' + hashlib.sha256(email.encode()).hexdigest()
                    user, _ = get_user_model().objects.get_or_create(username=username, defaults={'email': email})
            row.save(update_fields=['attempts', 'consumed'])
    if user is None or not user.is_active: raise ValidationError('Koden er feil, utløpt eller allerede brukt. Be om en ny kode.')
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    for key in ('preregistered_membership_id', 'provisioning_digest'): request.session.pop(key, None)
    request.session['identity_method'] = 'email_code'
    request.session['verified_email'] = email
    request.session['verified_at'] = timezone.now().isoformat()
    Membership.objects.filter(user=user).update(verified_at=timezone.now())
    return user


def binding_digest(binding):
    values = [binding.get('owner_email', '').strip().lower(), binding.get('source_sha256', ''), binding.get('import_series', '')]
    if not all(values): raise ValidationError('Privat eierbinding mangler påkrevde felt.')
    return hashlib.sha256('\n'.join(values).encode()).hexdigest()


def password_login(request, email, password, ip):
    from django.contrib.auth.hashers import make_password
    email = email.strip().lower()
    email_key, ip_key = digest('password-email:' + email), digest('password-ip:' + ip)
    user = None
    with transaction.atomic():
        with connection.cursor() as cursor:
            for key in sorted([email_key, ip_key]): cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(key[:15], 16)])
        since = timezone.now() - timedelta(minutes=15)
        blocked = PasswordAttempt.objects.filter(email_digest=email_key, attempted_at__gte=since).count() >= 5 or PasswordAttempt.objects.filter(ip_digest=ip_key, attempted_at__gte=since).count() >= 30
        member = Membership.objects.select_related('user').filter(user__email__iexact=email, identity_method__in=['preregistered_owner', 'preregistered_admin', 'preregistered_member'], provisioned_at__isnull=False).exclude(provisioning_digest='').first() if settings.PREREGISTERED_LOGIN_ENABLED else None
        if member and member.user.is_active:
            valid = member.user.check_password(password)
        else:
            make_password(password)
            valid = False
        if valid and not blocked:
            user = member.user
        elif not blocked:
            PasswordAttempt.objects.create(email_digest=email_key, ip_digest=ip_key, attempted_at=timezone.now())
    if user is None: raise ValidationError('Innloggingen kunne ikke bekreftes. Kontroller opplysningene eller prøv igjen senere.')
    for key in ('verified_email', 'verified_at'): request.session.pop(key, None)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session['identity_method'] = member.identity_method
    request.session['preregistered_membership_id'] = member.pk
    request.session['provisioning_digest'] = member.provisioning_digest
    return user


@transaction.atomic
def provision_owner(binding, password, family_name):
    from django.contrib.auth.password_validation import validate_password
    fingerprint = binding_digest(binding)
    email = binding['owner_email'].strip().lower()
    lock_identity_email(email)
    existing = get_user_model().objects.select_for_update().filter(email__iexact=email).first()
    if existing:
        member = Membership.objects.filter(user=existing, identity_method='preregistered_owner', provisioning_digest=fingerprint, provisioned_at__isnull=False, role='admin').first()
        if member and (not binding.get('household_id') or str(member.household_id) == str(binding['household_id'])):
            return member, False
        raise ValidationError('En konto finnes allerede. Kommandoen overtar eller nullstiller aldri eksisterende kontoer.')
    if binding.get('household_id'): raise ValidationError('Eierbindingen peker allerede til en familie. Ingen ny familie opprettes.')
    user = get_user_model()(username='owner_' + hashlib.sha256(email.encode()).hexdigest(), email=email)
    validate_password(password, user)
    user.set_password(password)
    user.save()
    house = Household.objects.create(name=family_name)
    member = Membership.objects.create(user=user, household=house, role='admin', verified_at=None, identity_method='preregistered_owner', provisioned_at=timezone.now(), provisioning_digest=fingerprint, can_register_households=True)
    from .financial_areas import create_area
    create_area(member)
    return member, True


@transaction.atomic
def register_family_account(actor, email, password, *, family_name=None, role='member', financial_sharing=None, financial_reader_ids=()):
    from django.contrib.auth.password_validation import validate_password
    from .access import lock_member
    member = lock_member(actor)
    if not settings.PREREGISTERED_LOGIN_ENABLED: raise ValidationError('Lokal forhåndsregistrering er deaktivert.')
    if not actor.is_active or member.role != 'admin': raise PermissionDenied('Bare administrator kan registrere familiemedlemmer.')
    if family_name is not None and not member.can_register_households:
        raise PermissionDenied('Du har ikke tillatelse til å opprette andre familier.')
    if role not in ('member', 'admin'): raise ValidationError('Ugyldig medlemsrolle.')
    from . import financial_areas
    if family_name is None:
        validate_financial_choice(member, financial_sharing, financial_reader_ids)
    elif financial_sharing != 'private' or financial_reader_ids:
        raise ValidationError('En ny familie starter med et privat budsjett.')
    email = email.strip().lower()
    lock_identity_email(email)
    if get_user_model().objects.filter(email__iexact=email).exists():
        raise ValidationError('Adressen kan ikke registreres som ny konto. Eksisterende kontoer flyttes eller nullstilles ikke.')
    user = get_user_model()(username='registered_' + hashlib.sha256(email.encode()).hexdigest(), email=email)
    validate_password(password, user)
    user.set_password(password)
    user.save()
    household = Household.objects.create(name=family_name) if family_name is not None else member.household
    assigned_role = 'admin' if family_name is not None else role
    provenance = hashlib.sha256((str(member.pk) + ':' + str(household.pk) + ':' + email + ':' + secrets.token_hex(32)).encode()).hexdigest()
    registered = Membership.objects.create(user=user, household=household, role=assigned_role, verified_at=None, identity_method='preregistered_admin' if assigned_role == 'admin' else 'preregistered_member', provisioned_at=timezone.now(), provisioning_digest=provenance, provisioned_by=actor)
    Audit.objects.create(household=household, actor=actor, object_id=household.pk, operation='lokal registrering', changes={'membership_id': registered.pk, 'role': assigned_role, 'email_verified': False})
    financial_areas.create_area(registered, reader_ids=financial_reader_ids)
    return registered


@transaction.atomic
def create_household(user, name, verified_email):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if verified_email != user.email.lower() or Membership.objects.filter(user=user).exists():
        raise ValidationError('Verifisert bruker må være uten familie.')
    house = Household.objects.create(name=name)
    member = Membership.objects.create(user=user, household=house, role='admin', verified_at=timezone.now())
    from .financial_areas import create_area
    create_area(member)
    return house


@transaction.atomic
def invite(actor, email, base_url, *, financial_sharing=None, financial_reader_ids=()):
    from .access import lock_member
    member = lock_member(actor)
    if member.role != 'admin': raise ValidationError('Bare administrator kan invitere.')
    validate_financial_choice(member, financial_sharing, financial_reader_ids)
    token = secrets.token_urlsafe(32)
    row = Invitation.objects.create(financial_sharing=financial_sharing, financial_reader_ids=list(map(int, financial_reader_ids)), household=member.household, invited_by=actor, email=email.lower(), digest=digest(token), expires_at=timezone.now() + timedelta(days=7))
    send_mail('Invitasjon til Familieblikk', f'Du er invitert til {member.household.name}. Logg inn med denne e-postadressen og godta invitasjonen: {base_url}/invitasjon/{token}/', settings.DEFAULT_FROM_EMAIL, [email])
    return row


@transaction.atomic
def accept_invite(user, token, verified_email):
    initial = Invitation.objects.filter(digest=digest(token)).only('household_id').first()
    if initial:
        Household.objects.select_for_update().get(pk=initial.household_id)
    get_user_model().objects.select_for_update().get(pk=user.pk)
    row = Invitation.objects.select_for_update().filter(digest=digest(token)).first()
    if not row or row.revoked or row.accepted or row.expires_at <= timezone.now() or row.email != verified_email:
        raise ValidationError('Invitasjonen er ugyldig, utløpt eller gjelder en annen e-postadresse.')
    if not Membership.objects.filter(user=row.invited_by, household=row.household, role='admin').exists():
        raise ValidationError('Invitasjonen er ikke lenger gyldig.')
    if Membership.objects.filter(user=user).exists(): raise ValidationError('Du tilhører allerede en familie. Du flyttes ikke automatisk.')
    inviter = Membership.objects.get(user=row.invited_by, household=row.household)
    validate_financial_choice(inviter, row.financial_sharing, row.financial_reader_ids)
    joined = Membership.objects.create(user=user, household=row.household, role='member', verified_at=timezone.now())
    from .financial_areas import create_area
    create_area(joined, reader_ids=row.financial_reader_ids)
    row.accepted = True
    row.save(update_fields=['accepted'])
    return row.household


def validate_financial_choice(member, sharing, reader_ids):
    if sharing not in ('private', 'named'):
        raise ValidationError('Velg uttrykkelig privat budsjett eller navngitt innsyn.')
    try:
        ids = set(map(int, reader_ids))
    except (TypeError, ValueError):
        raise ValidationError('Ugyldige deltakere.') from None
    if (sharing == 'private' and ids) or (sharing == 'named' and not ids):
        raise ValidationError('Privat budsjett har ingen lesere. Navngitt innsyn krever minst én leser.')
    actual = set(Membership.objects.filter(household=member.household, user__is_active=True, pk__in=ids).values_list('pk', flat=True))
    if actual != ids:
        raise ValidationError('Velg aktive medlemmer i denne familien.')
