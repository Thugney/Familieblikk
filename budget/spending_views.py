import json
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from . import spending_services as service
from .services import Conflict
from .spending_forms import month_value
from . import access


def api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            if not request.user.is_authenticated:
                raise PermissionDenied('Logg inn for å bruke familiens opplysninger.')
            response = JsonResponse(view(request, *args, **kwargs))
        except PermissionDenied as exc:
            response = JsonResponse({'error': str(exc) or 'Ingen tilgang.'}, status=403)
        except Conflict as exc:
            response = JsonResponse({'error': ' '.join(exc.messages)}, status=409)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            response = JsonResponse({'error': ' '.join(exc.messages) if hasattr(exc, 'messages') else 'Ugyldig forespørsel.'}, status=400)
        response['Cache-Control'] = 'no-store, private'
        return response
    return wrapped


def json_body(request):
    if len(request.body) > 100_000:
        raise ValidationError('Forespørselen er for stor.')
    return json.loads(request.body)


@require_GET
@api
def spending_data(request):
    return service.spending(request.user, request.GET)


@require_GET
@api
def planning_data(request):
    raw = request.GET.get('history', '')
    return service.planning(request.user, request.GET.get('target_month'), raw.split(',') if raw else [])


@require_POST
@api
def planning_preview(request):
    return service.preview(request.user, json_body(request))


@require_POST
@api
def planning_save(request):
    return service.save_plan(request.user, json_body(request))


def shell_context(request, initial_tab='spending'):
    from .views import NAV
    member = service.membership(request.user)
    access.require_page(member, 'arsoversikt' if initial_tab == 'annual' else 'budsjett')
    access.require(member, {'budget'})
    try:
        selected = month_value(request.GET.get('month') or service.month_key(timezone.localdate()))
    except ValidationError:
        selected = timezone.localdate().replace(day=1)
    return {'member': member, 'nav': NAV, 'page': 'arsoversikt' if initial_tab == 'annual' else 'budsjett',
            'title': 'Året i bilder' if initial_tab == 'annual' else 'Forbruk og plan', 'month': selected,
            'spending_boot': {'initial_tab': initial_tab, 'urls': service.URLS, 'month': service.month_key(selected), 'can_save': getattr(request, 'financial_can_write', False),
                              'can_plan': access.complete_finance(member), 'can_annual': access.allows(member, 'annual'),
                              'restricted_selection': not access.complete_finance(member)}}


@login_required
@require_GET
def render_shell(request, initial_tab='spending'):
    from .models import Membership
    if not Membership.objects.filter(user=request.user).exists(): return redirect('family_gate')
    context = shell_context(request, initial_tab)
    response = render(request, 'budget/spending.html', context)
    response['Cache-Control'] = 'no-store, private'
    return response
