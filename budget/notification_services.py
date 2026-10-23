"""One privacy policy for notification listing, opening and queued delivery.

These hooks run inside the caller's household transaction. No transport or
financial content is included in a sharing/shopping notification.
"""
import uuid
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from . import access
from .models import CalendarNotification, Membership, PushDelivery, PushSubscription

TEXT = {
    'budget_proposal': 'Et forslag til budsjettdeling venter på din bekreftelse.',
    'budget_active': 'En bekreftet budsjettdeling er aktivert.',
    'shopping_changed': 'En felles handleliste er oppdatert.',
}
CALENDAR_KINDS = {'created', 'yes', 'no'}


def proposal_recipients(change):
    from .financial_areas import participant_ids
    members = Membership.objects.filter(household_id=change.household_id, user__is_active=True)
    invited = participant_ids(change) - {change.owner_id}
    # Named participants can provide the second confirmation. A private-only
    # proposal instead needs an administrator distinct from the owner.
    second = members.filter(pk__in=invited)
    if not second.exists():
        second = members.filter(role='admin').exclude(pk=change.owner_id)
    return members.filter(Q(pk=change.owner_id) | Q(pk__in=second.values('pk')))


def can_view_notification(member, notice):
    if (not member or not member.user.is_active or notice.household_id != member.household_id
            or notice.recipient_id != member.user_id):
        return False
    if notice.kind in CALENDAR_KINDS:
        return access.allows(member, 'calendar') and (not notice.event_id or notice.event.household_id == member.household_id)
    if notice.kind == 'shopping_changed':
        return bool(access.allows(member, 'shopping') and notice.shopping_list_id
                    and notice.shopping_list.household_id == member.household_id)
    if notice.kind in ('budget_proposal', 'budget_active'):
        from .financial_areas import allowed_areas, proposal_problem
        change = notice.proposal
        if not change or change.household_id != member.household_id:
            return False
        if notice.kind == 'budget_proposal':
            return bool(not change.applied and not proposal_problem(change)
                        and member.pk not in (change.owner_confirmation_id, change.admin_confirmation_id)
                        and proposal_recipients(change).filter(pk=member.pk).exists())
        # Current grants are rechecked: historical notification ownership never
        # restores access removed by a later sharing change.
        return bool(change.applied and change.area_id and change.area.household_id == member.household_id
                    and change.area.status == 'active' and (
                        allowed_areas(member).filter(pk=change.area_id).exists()
                        or member.role == 'admin' and change.admin_confirmation_id == member.pk))
    return False


def visible_notifications(member, *, unread=False, limit=None):
    query = CalendarNotification.objects.filter(recipient_id=member.user_id, household_id=member.household_id)
    if unread:
        query = query.filter(read_at__isnull=True)
    query = query.select_related('event', 'shopping_list', 'proposal__area', 'proposal__owner__user',
                                 'proposal__admin_confirmation__user').order_by('-created_at', '-pk')
    result = []
    for notice in query.iterator(chunk_size=100):
        if can_view_notification(member, notice):
            notice.open_label = {'budget_proposal': 'Se og bekreft forslaget',
                                 'budget_active': 'Se budsjettdelingen',
                                 'shopping_changed': 'Åpne handlelisten'}.get(notice.kind, 'Åpne kalenderen')
            notice.is_calendar = notice.kind in CALENDAR_KINDS
            result.append(notice)
            if limit and len(result) >= limit:
                break
    return result


def _record(actor_member, members, kind, action_key, **target):
    for member in members.exclude(user_id=actor_member.user_id).select_related('user'):
        if member.household_id != actor_member.household_id:
            continue
        notice = CalendarNotification(household_id=actor_member.household_id, recipient_id=member.user_id,
            original_date=timezone.localdate(), kind=kind, action_key=action_key, detail=TEXT[kind], **target)
        if not can_view_notification(member, notice):
            continue
        notice, created = CalendarNotification.objects.get_or_create(
            household_id=notice.household_id, recipient_id=notice.recipient_id, action_key=action_key,
            defaults={'original_date': notice.original_date, 'kind': kind, 'detail': notice.detail, **target})
        if created:
            PushDelivery.objects.bulk_create([PushDelivery(notification=notice, subscription=sub)
                for sub in PushSubscription.objects.filter(user_id=member.user_id,
                    household_id=member.household_id, active=True)])


def record_budget_proposal(actor_member, change):
    if change.applied or change.household_id != actor_member.household_id:
        return
    _record(actor_member, proposal_recipients(change), 'budget_proposal',
            uuid.uuid5(change.pk, 'budget_proposal'), proposal=change)


def record_budget_confirmation(actor_member, change):
    if not change.applied:
        record_budget_proposal(actor_member, change)
        return
    if not change.area_id or change.household_id != actor_member.household_id:
        return
    members = Membership.objects.filter(household_id=change.household_id, user__is_active=True).filter(
        Q(financialareagrant__area_id=change.area_id) | Q(pk=change.admin_confirmation_id, role='admin')).distinct()
    _record(actor_member, members, 'budget_active', uuid.uuid5(change.pk, 'budget_active'), proposal=change)


def record_shopping_change(actor_member, listing, command_key):
    members = Membership.objects.filter(household_id=actor_member.household_id, user__is_active=True)
    _record(actor_member, members, 'shopping_changed',
            uuid.uuid5(listing.pk, f'shopping_changed:{actor_member.pk}:{command_key}'), shopping_list=listing)


def notification_destination(member, notice):
    """Only call after can_view_notification has revalidated the target."""
    if notice.kind == 'shopping_changed':
        return reverse('shopping_detail', args=[notice.shopping_list_id])
    if notice.kind == 'budget_proposal':
        return reverse('financial_proposal', args=[notice.proposal_id])
    if notice.kind == 'budget_active':
        return reverse('financial_proposal', args=[notice.proposal_id])
    return None


def bill_alerts(member, month):
    """Per-budget in-app counts; never aggregate undisclosed financial areas."""
    if not access.allows(member, 'bills'):
        return []
    from .financial_areas import allowed_areas, area_scope
    from . import services
    from .area_requests import financial_url
    result = []
    # resolve_area attaches its target to the supplied member. Use a fresh
    # instance so this general page cannot inherit the last inspected budget.
    scoped_member = Membership.objects.select_related('household').get(pk=member.pk, household_id=member.household_id)
    for area in allowed_areas(member).order_by('name', 'pk'):
        with area_scope(scoped_member, area.pk):
            bills = access.safe_rows(scoped_member, services.pending_bills(scoped_member.household, services.month_end(month)))
            result.append({'name': area.name, 'pending': bills.count(),
                'overdue': bills.filter(due_date__lt=timezone.localdate()).count(),
                'url': financial_url(reverse('page', args=['regninger']) + '?month=' + month.strftime('%Y-%m'), area.pk)})
    return result
