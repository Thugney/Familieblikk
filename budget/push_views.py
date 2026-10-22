"""Authenticated, CSRF-protected browser push preferences and notification access."""
import json
from datetime import date
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from . import push_services as push
from .models import CalendarNotification, Membership, PushDelivery, PushSubscription


def member_for(request):
    try: return Membership.objects.get(user=request.user)
    except Membership.DoesNotExist: raise PermissionDenied('Bli med i en familie først.') from None


def request_data(request):
    if len(request.body) > 8192: raise ValidationError('Forespørselen er for stor.')
    try: data = json.loads(request.body)
    except (ValueError, TypeError): raise ValidationError('Ugyldig forespørsel.') from None
    if not isinstance(data, dict): raise ValidationError('Ugyldig forespørsel.')
    return data


@login_required
@never_cache
@require_GET
def config(request):
    member_for(request)
    key = push.ensure_key()
    return JsonResponse({'public_key': key.public_key})


@login_required
@never_cache
@require_POST
def device(request):
    try:
        data = request_data(request)
        action = data.get('action')
        member = member_for(request)
        if action == 'subscribe' and set(data) == {'action', 'subscription'}:
            sub = push.subscribe(request, data['subscription'])
            return JsonResponse({'id': str(sub.pk), 'state': sub.state})
        if action in ('status', 'disable') and set(data) == {'action', 'endpoint'}:
            endpoint = push.validate_endpoint(data['endpoint'])
            if action == 'disable': push.disable_session(request, endpoint)
            sub = PushSubscription.objects.filter(user=request.user, household=member.household, endpoint_digest=push.digest(endpoint), session_digest=push.digest(request.session.session_key or '')).first()
            if not sub: return JsonResponse({'state': 'disabled'})
            active = push.valid_binding(sub)
            return JsonResponse({'id': str(sub.pk), 'state': sub.state if active else 'expired', 'active': active})
        if action == 'test' and set(data) == {'action', 'id'}:
            try: delivery = push.queue_test(request, data['id'])
            except (ValueError, ValidationError): raise ValidationError('Aktiver varsler på denne enheten først, og vent ett minutt mellom tester.') from None
            return JsonResponse({'state': 'queued', 'delivery_id': str(delivery.pk)})
        raise ValidationError('Ugyldig enhetshandling.')
    except (ValidationError, ValueError, TypeError) as exc:
        return JsonResponse({'error': ' '.join(exc.messages) if hasattr(exc, 'messages') else 'Ugyldig forespørsel.'}, status=400)


@login_required
@never_cache
@require_POST
def receipt(request):
    """Only this session's own test job; never expose calendar jobs or endpoints."""
    member = member_for(request)
    try:
        data = request_data(request)
        if set(data) != {'delivery_id'}: raise ValidationError('Ugyldig testkvittering.')
        row = PushDelivery.objects.filter(
            pk=data['delivery_id'], notification__isnull=True,
            subscription__user=request.user, subscription__household=member.household,
            subscription__session_digest=push.digest(request.session.session_key or ''),
        ).first()
    except (ValidationError, ValueError, TypeError):
        return JsonResponse({'error': 'Ugyldig testkvittering.'}, status=400)
    if not row: return JsonResponse({'error': 'Testvarselet finnes ikke for denne innloggingen.'}, status=404)
    state = 'retry' if row.state == 'pending' and row.attempts else row.state
    result = {'state': state, 'attempts': row.attempts,
              'provider_accepted': row.state == 'sent', 'os_display_confirmed': False}
    if row.state == 'pending': result['next_attempt_at'] = row.available_at.isoformat()
    if row.sent_at: result['sent_at'] = row.sent_at.isoformat()
    return JsonResponse(result)


@login_required
@never_cache
@require_GET
def summary(request):
    member = member_for(request)
    return JsonResponse({'unread': CalendarNotification.objects.filter(
        recipient=request.user, household=member.household, read_at__isnull=True).count()})


@login_required
@require_POST
def mark_read(request, notification_id):
    from .views import selected_month, module_url
    month = selected_month(request)
    member = member_for(request)
    notice = get_object_or_404(CalendarNotification, pk=notification_id, recipient=request.user, household=member.household)
    if not notice.read_at:
        notice.read_at = timezone.now(); notice.save(update_fields=['read_at'])
    return redirect(module_url('varsler', month)) if 'month' in request.GET else redirect('page', page='varsler')


@login_required
@require_GET
def open_notification(request, notification_id):
    member = member_for(request)
    notice = get_object_or_404(CalendarNotification, pk=notification_id, recipient=request.user, household=member.household)
    # Normal calendar listing still applies its membership/tenant checks.
    day = notice.original_date
    resolved = False
    if notice.event_id:
        from .calendar_services import occurrence
        try:
            day = date.fromisoformat(occurrence(notice.event, notice.original_date)['start'])
            resolved = True
        except ValidationError: pass
    if not resolved:
        messages.info(request, 'Avtalen er endret eller slettet. Varselet viser en tidligere versjon som ikke lenger finnes i kalenderen.')
    return redirect(reverse('calendar') + '?' + urlencode({'cal_month': day.strftime('%Y-%m'), 'event': str(notice.event_id or ''), 'original': notice.original_date.isoformat()}))
