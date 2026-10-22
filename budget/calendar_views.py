import json

from datetime import date, timedelta

from calendar import monthrange, Calendar

from django.contrib.auth.decorators import login_required

from django.core.exceptions import PermissionDenied, ValidationError

from django.http import JsonResponse

from django.shortcuts import redirect, render

from django.utils import timezone

from django.views.decorators.http import require_GET, require_POST

from . import calendar_services as service

from .calendar_forms import CalendarForm

from .services import Conflict

from .views import NAV



def agenda_date_label(value):
    day=date.fromisoformat(value)
    months=('jan.','feb.','mars','apr.','mai','juni','juli','aug.','sep.','okt.','nov.','des.')
    return f'{day.day}. {months[day.month-1]}'


def selected_month(request):

    raw=request.GET.get('cal_month','')

    try:

        result=date.fromisoformat(raw+'-01') if raw else timezone.localdate().replace(day=1)

        if result.year < 1901 or result.year > 2198: raise ValueError

        return result

    except ValueError: raise ValidationError('Velg en gyldig kalendermåned.')



@login_required

@require_GET

def calendar_page(request):
    if not service.Membership.objects.filter(user=request.user).exists(): return redirect('family_gate')
    member=service.membership(request.user)

    error=''

    try: current=selected_month(request)

    except ValidationError as exc: current=timezone.localdate().replace(day=1); error=' '.join(exc.messages)

    last=current.replace(day=monthrange(current.year,current.month)[1])

    selected=request.GET.get('person','all')

    grid_weeks=Calendar(firstweekday=0).monthdatescalendar(current.year,current.month)

    try: grid_events=service.listing(request.user,grid_weeks[0][0],grid_weeks[-1][-1],selected)

    except ValidationError as exc: grid_events=[]; error=' '.join(exc.messages); selected='all'

    for event in grid_events:
        event['start_label']=agenda_date_label(event['start'])
        event['end_label']=agenda_date_label(event['end'])

    weeks=[]

    events=[event for event in grid_events if event['start']<=last.isoformat() and event['display_end']>=current.isoformat()]

    for week in grid_weeks:

        weeks.append([{'date':day,'current':day.month==current.month,'today':day==timezone.localdate(),'events':[e for e in grid_events if e['start']<=day.isoformat()<=e['display_end']]} for day in week])

    budget_month=request.GET.get('month','')

    try: budget_month=date.fromisoformat(budget_month+'-01')

    except ValueError: budget_month=timezone.localdate().replace(day=1)

    members=service.access.calendar_members(member.household)

    context={'member':member,'nav':NAV,'page':'kalender','title':'Familiekalender','month':budget_month,'cal_month':current,'previous':(current-timedelta(days=1)).strftime('%Y-%m'),'next':(last+timedelta(days=1)).strftime('%Y-%m'),'events':events,'weeks':weeks,'members':members,'person':selected,'calendar_error':error,'calendar_form':CalendarForm(member.household),'weekdays':['Man','Tir','Ons','Tor','Fre','Lør','Søn']}

    context['grid_events']=grid_events

    return render(request,'budget/calendar.html',context)



@login_required

@require_GET

def calendar_data(request):

    try:

        first=date.fromisoformat(request.GET.get('start',''))

        last=date.fromisoformat(request.GET.get('end',''))

        return JsonResponse({'events':service.listing(request.user,first,last,request.GET.get('person','all'))})

    except (ValidationError,ValueError) as exc:

        return JsonResponse({'error':' '.join(exc.messages) if hasattr(exc,'messages') else 'Ugyldig dato.'},status=400)



@login_required

@require_POST

def calendar_api(request):

    try:

        data=json.loads(request.body)

        allowed={'action','key','event_id','original','revision','payload','scope','status','response_revision'}

        if not isinstance(data,dict) or set(data)-allowed: raise ValidationError('Ugyldig forespørsel. Du kan bare svare for deg selv.')

        if 'action' not in data or 'key' not in data: raise ValidationError('Handlingen mangler obligatoriske felt.')

        result=service.mutate(request.user,**data)

        return JsonResponse(result)

    except Conflict as exc: return JsonResponse({'error':' '.join(exc.messages)},status=409)

    except (ValidationError,ValueError,TypeError,json.JSONDecodeError) as exc: return JsonResponse({'error':' '.join(exc.messages) if hasattr(exc,'messages') else 'Ugyldige felt.'},status=400)

