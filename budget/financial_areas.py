"""Area capability boundary and explicit, two-person migration/sharing protocol."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, connection
from .financial_models import FinancialArea, FinancialAreaGrant, AreaAccessChange, FinancialRecord

_scope = ContextVar('financial_scope', default=None)


def scope_state():
    return _scope.get()


def allowed_areas(member):
    return FinancialArea.objects.filter(household_id=member.household_id, status='active',
        grants__member_id=member.pk, grants__member__user__is_active=True)


def resolve_area(member, area_id, write=False):
    if not area_id:
        raise PermissionDenied('Velg et budsjett først.')
    try:
        area = allowed_areas(member).get(pk=area_id)
    except (FinancialArea.DoesNotExist, ValueError, ValidationError):
        raise PermissionDenied('Du har ikke tilgang til dette budsjettet.') from None
    if write and not can_write(member, area):
        raise PermissionDenied('Du har kun innsyn i dette budsjettet.')
    member.financial_area = area
    return area


def can_write(member, area):
    return FinancialAreaGrant.objects.filter(area=area, area__household_id=member.household_id,
        area__status='active', member_id=member.pk, member__user__is_active=True,
        role__in=['owner', 'editor']).exists()


def current_area(member=None, write=False):
    from .models import Membership
    state = _scope.get()
    if state is None:
        raise PermissionDenied('Velg et eksplisitt målbudsjett.')
    fresh = Membership.objects.select_related('user').get(pk=state['member_id'])
    if member is not None and member.pk != fresh.pk:
        raise PermissionDenied('Budsjettet tilhører en annen økt.')
    return resolve_area(fresh, state['area_id'], write=write)


@contextmanager
def area_scope(member, area_id, write=False):
    area = resolve_area(member, area_id, write=write)
    token = _scope.set({'member_id': member.pk, 'household_id': member.household_id, 'area_id': area.pk})
    try:
        yield area
    finally:
        _scope.reset(token)


def _participants(owner, reader_ids, editor_ids=(), kind='personal'):
    from .models import Membership
    readers, editors = set(map(int, reader_ids)), set(map(int, editor_ids))
    if readers & editors or owner.pk in readers | editors or (editors and kind != 'shared'):
        raise ValidationError('Velg entydige deltakere; personlige budsjetter har bare lesere.')
    members = set(Membership.objects.filter(household_id=owner.household_id, user__is_active=True,
        pk__in=readers | editors | {owner.pk}).values_list('pk', flat=True))
    if members != readers | editors | {owner.pk}:
        raise ValidationError('Alle deltakere må være aktive medlemmer i familien.')
    return [{'member': owner.pk, 'role': 'owner'}] + [
        {'member': pk, 'role': role} for role, ids in [('reader', readers), ('editor', editors)] for pk in sorted(ids)]


@transaction.atomic
def create_area(member, name='Mitt budsjett', reader_ids=(), editor_ids=(), kind='personal'):
    from .models import Household
    Household.objects.select_for_update().get(pk=member.household_id)
    participants = _participants(member, reader_ids, editor_ids, kind)
    area = FinancialArea.objects.create(household_id=member.household_id, owner=member, name=name, kind=kind,
        modules=dict(member.household.modules))
    FinancialAreaGrant.objects.bulk_create([FinancialAreaGrant(area=area, member_id=p['member'], role=p['role']) for p in participants])
    return area


def participant_ids(change):
    """Member ids invited as reader/editor in a stored proposal.

    ``after`` is persisted JSON. Treat malformed rows as empty rather than
    letting a single bad proposal take down the proposal page or confirmation.
    """
    readers, editors = participant_roles(change)
    return set(readers) | set(editors)


def participant_roles(change):
    """Return ``(reader_ids, editor_ids)`` from a stored proposal, skipping malformed rows."""
    readers, editors = [], []
    for item in change.after or []:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        try:
            member_id = int(item.get('member'))
        except (TypeError, ValueError):
            continue
        if role == 'reader':
            readers.append(member_id)
        elif role == 'editor':
            editors.append(member_id)
    return readers, editors


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def financial_models():
    return [m for m in apps.get_app_config('budget').get_models() if issubclass(m, FinancialRecord)]


def legacy_inventory(member):
    # Metadata only: no names, values, raw source data or financial content.
    rows = {}
    for m in financial_models():
        query = m.all_objects.filter(household_id=member.household_id, financial_area__isnull=True)
        if m._meta.model_name == 'audit':
            query = query.exclude(operation__in=m.METADATA_OPERATIONS)
        rows[m._meta.model_name] = list(query.order_by('pk').values())
    return {'groups': {name: len(values) for name, values in rows.items()}, 'fingerprint': _digest(rows)}


@transaction.atomic
def propose_access_change(member, area_id, reader_ids, editor_ids=()):
    from .models import Household
    Household.objects.select_for_update().get(pk=member.household_id)
    area = FinancialArea.objects.select_for_update().get(pk=area_id, household_id=member.household_id)
    if member.pk != area.owner_id and member.role != 'admin':
        raise PermissionDenied('Bare eier eller familieadministrator kan foreslå tilgang.')
    after = _participants(area.owner, reader_ids, editor_ids, area.kind)
    before = list(area.grants.order_by('member_id').values('member_id', 'role'))
    payload = {'area': str(area.pk), 'version': area.access_version, 'before': before, 'after': after}
    return AreaAccessChange.objects.create(household=area.household, area=area, owner=area.owner,
        expected_version=area.access_version, before=before, after=after, digest=_digest(payload))


@transaction.atomic
def propose_legacy_setup(member, owner_id, reader_ids, editor_ids, fingerprint):
    from .models import Household, Membership
    Household.objects.select_for_update().get(pk=member.household_id)
    if member.role != 'admin':
        raise PermissionDenied('Bare familieadministrator kan foreslå oppsett.')
    owner = Membership.objects.get(pk=owner_id, household_id=member.household_id, user__is_active=True)
    inventory = legacy_inventory(member)
    if inventory['fingerprint'] != fingerprint:
        raise ValidationError('Datagrunnlaget er endret. Se gjennom oppsettet på nytt.')
    after = _participants(owner, reader_ids, editor_ids, 'shared')
    payload = {'inventory': inventory, 'after': after, 'owner': owner.pk}
    return AreaAccessChange.objects.create(household_id=member.household_id, owner=owner, kind='legacy',
        inventory=inventory, after=after, digest=_digest(payload))


@transaction.atomic
def confirm_access_change(member, proposal_id, digest):
    from .models import Household, Membership
    Household.objects.select_for_update().get(pk=member.household_id)
    member = Membership.objects.select_for_update().get(pk=member.pk, user__is_active=True)
    change = AreaAccessChange.objects.select_for_update().get(pk=proposal_id, household_id=member.household_id)
    if digest != change.digest or change.applied:
        raise ValidationError('Forslaget er endret eller allerede aktivert.')
    if change.owner_confirmation_id == member.pk or change.admin_confirmation_id == member.pk:
        return change
    invited_ids = participant_ids(change)
    if member.pk == change.owner_id:
        change.owner_confirmation = member
    elif member.role == 'admin' or member.pk in invited_ids:
        change.admin_confirmation = member
    else:
        raise PermissionDenied('Bekreftelsen krever eieren eller en annen deltaker i budsjettet.')
    if change.owner_confirmation_id and change.admin_confirmation_id:
        second = Membership.objects.select_for_update().get(pk=change.admin_confirmation_id)
        owner = Membership.objects.select_for_update().get(pk=change.owner_id)
        if not (second.role == 'admin' or second.pk in invited_ids) or second.household_id != member.household_id or not second.user.is_active or not owner.user.is_active:
            raise PermissionDenied('Rollene er endret. Opprett et nytt forslag.')
        readers, editors = participant_roles(change)
        if change.kind == 'legacy':
            if legacy_inventory(member) != change.inventory:
                raise ValidationError('Vertsdata er endret. Se gjennom et nytt oppsett.')
            area = create_area(owner, 'Felles budsjett', readers, editors, kind='shared')
            # Only this explicitly confirmed transition can assign quarantined rows.
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('familieblikk.legacy_assignment', %s, true)", [str(member.household_id)])
            for model in financial_models():
                query = model.all_objects.filter(household_id=member.household_id, financial_area__isnull=True)
                if model._meta.model_name == 'audit':
                    query = query.exclude(operation__in=model.METADATA_OPERATIONS)
                query.update(financial_area=area)
            change.area = area
        else:
            area = FinancialArea.objects.select_for_update().get(pk=change.area_id)
            if area.access_version != change.expected_version or area.owner_id != owner.pk:
                raise ValidationError('Tilgangen er endret. Opprett et nytt forslag.')
            participants = _participants(owner, readers, editors, area.kind)
            area.grants.all().delete()
            FinancialAreaGrant.objects.bulk_create([FinancialAreaGrant(area=area, member_id=p['member'], role=p['role']) for p in participants])
            area.access_version += 1
            area.save(update_fields=['access_version'])
        change.applied = True
    change.save()
    return change


confirm_legacy_setup = confirm_access_change
