from datetime import date, datetime, time, timedelta

from calendar import monthrange

from zoneinfo import ZoneInfo

import hashlib

import json

import uuid

from django.core.exceptions import PermissionDenied, ValidationError

from django.db import transaction

from .models import CalendarEvent, CalendarException, CalendarResponse, CalendarRequest, Household, Membership

from .services import membership as budget_membership, Conflict

OSLO = ZoneInfo('Europe/Oslo')

def membership(actor):
    try: return budget_membership(actor)
    except Membership.DoesNotExist: raise PermissionDenied('Opprett eller bli med i en familie for å bruke kalenderen.')

def local_time(day, clock, fold=None):

    parsed=time.fromisoformat(clock)
    if parsed.tzinfo is not None: raise ValueError('Bruk lokal tid uten tidssoneoffset.')
    naive = datetime.combine(day, parsed)

    valid = []

    for n in (0, 1):

        aware = naive.replace(tzinfo=OSLO, fold=n)

        if aware.astimezone(ZoneInfo('UTC')).astimezone(OSLO).replace(tzinfo=None) == naive:

            if not any(x.utcoffset() == aware.utcoffset() for x in valid): valid.append(aware)

    if not valid: raise ValidationError('Klokkeslettet finnes ikke ved overgang til sommertid. Velg et annet klokkeslett.')

    if len(valid) == 2 and fold not in (0, 1): raise ValidationError('Klokkeslettet forekommer to ganger. Velg tidligere eller senere tidspunkt.')

    return next((x for x in valid if x.fold == fold), valid[0])

def validate_payload(data, household):

    if not isinstance(data, dict): raise ValidationError('Avtalen må inneholde gyldige felt.')

    if not isinstance(data.get('all_day'), bool) or not isinstance(data.get('participants'), list): raise ValidationError('Ugyldig heldagsvalg eller deltakerliste.')

    if any(not isinstance(x, (str, int)) or isinstance(x, bool) for x in data['participants']): raise ValidationError('Ugyldig deltaker.')

    if data.get('fold') not in (None, 0, 1) or isinstance(data.get('fold'), bool): raise ValidationError('Ugyldig valg av vintertid.')

    if any(data.get(k) is not None and not isinstance(data.get(k), str) for k in ('title','place','note','start','end','start_time','end_time','until','scope','recurrence')): raise ValidationError('Avtalefeltene må ha gyldig tekst eller dato.')
    if data.get('fold') is not None and type(data['fold']) is not int: raise ValidationError('Ugyldig valg av vintertid.')
    p = {k: data.get(k) for k in ('title','start','end','all_day','start_time','end_time','place','note','scope','participants','recurrence','until','fold')}

    p['title'] = str(p['title'] or '').strip()

    p['place'], p['note'] = str(p['place'] or '').strip(), str(p['note'] or '').strip()

    if not p['title'] or len(p['title']) > 160: raise ValidationError('Tittel må ha 1–160 tegn.')

    if len(p['place']) > 240 or len(p['note']) > 4000: raise ValidationError('Sted eller notat er for langt.')

    try: start, end = date.fromisoformat(p['start']), date.fromisoformat(p['end'])

    except (TypeError, ValueError): raise ValidationError('Velg gyldige datoer.')

    if start.year < 1900 or end.year > 2199: raise ValidationError('Dato må være mellom 1900 og 2199.')

    if end < start or (end-start).days > 366: raise ValidationError('Slutt må være etter start, og avtalen kan vare høyst ett år.')

    if p['scope'] not in ('shared','selected') or p['recurrence'] not in ('none','weekly','monthly'): raise ValidationError('Velg gyldig kalender og gjentakelse.')

    if any(not isinstance(p[k], str) for k in ('title', 'place', 'note')): raise ValidationError('Tittel, sted og notat må være tekst.')

    p['participants'] = sorted(set(str(x) for x in (p['participants'] or [])))

    valid = set(str(x) for x in Membership.objects.filter(household=household).values_list('pk', flat=True))

    if not set(p['participants']) <= valid: raise ValidationError('Deltakeren tilhører ikke familien.')

    if p['scope'] == 'selected' and not p['participants']: raise ValidationError('Velg minst ett familiemedlem.')

    if p['scope'] == 'shared': p['participants'] = []

    if p['until']:

        try: until = date.fromisoformat(p['until'])

        except (TypeError, ValueError): raise ValidationError('Velg gyldig sluttdato for serien.')

        if until < start: raise ValidationError('Seriens sluttdato kan ikke være før start.')

    else: p['until'] = None

    if p['all_day']:
        p['start_time'] = p['end_time'] = p['fold'] = None

    else:

        try:

            first = local_time(start, p['start_time'], p['fold'])

            last = local_time(end, p['end_time'], p['fold'])

        except (ValueError, TypeError): raise ValidationError('Velg gyldig start- og sluttklokkeslett.')

        if last.astimezone(ZoneInfo('UTC')) <= first.astimezone(ZoneInfo('UTC')): raise ValidationError('Slutt må være etter start.')

    return p

def dates(p, first, last):

    anchor = date.fromisoformat(p['start'])

    until = min(last, date.fromisoformat(p['until'])) if p.get('until') else last

    if p['recurrence'] == 'none':

        if first <= anchor <= until: yield anchor

        return

    if p['recurrence'] == 'weekly':

        n = max(0, (first-anchor).days//7)

        day = anchor + timedelta(days=n*7)

        while day <= until:

            if day >= first: yield day

            day += timedelta(days=7)

    else:

        n = max(0, (first.year-anchor.year)*12 + first.month-anchor.month)

        while True:

            y, m = divmod(anchor.year*12+anchor.month-1+n, 12)

            day = date(y,m+1,min(p.get('anchor_day', anchor.day),monthrange(y,m+1)[1]))

            if day > until: break

            if day >= first: yield day

            n += 1

def shifted(p, day):

    result = dict(p)

    delta = day-date.fromisoformat(p['start'])

    result['start'] = day.isoformat()

    result['end'] = (date.fromisoformat(p['end'])+delta).isoformat()

    return result

def occurrence(event, original):

    base = event.payload

    if event.deleted or original not in dates(base, original, original): raise ValidationError('Avtalen finnes ikke lenger.')

    ex = event.exceptions.filter(original_date=original).first()

    if ex:

        if ex.payload is None: raise ValidationError('Avtalen er slettet.')

        return ex.payload

    return shifted(base, original)

def eligible(p, members):

    return members if p['scope'] == 'shared' else [m for m in members if str(m.pk) in p['participants']]

def listing(actor, first, last, selected='all'):

    member = membership(actor)

    if first.year < 1900 or last.year > 2199: raise ValidationError('Kalenderen viser år 1900–2199.')

    if last < first or (last-first).days > 93: raise ValidationError('Velg et datointervall på høyst 93 dager.')

    members = list(Membership.objects.filter(household=member.household).select_related('user'))

    if selected not in ('all','shared') and selected not in {str(m.pk) for m in members}: raise ValidationError('Ugyldig personfilter.')

    result=[]

    for event in CalendarEvent.objects.filter(household=member.household,deleted=False).prefetch_related('exceptions','responses'):

        p=event.payload

        span=(date.fromisoformat(p['end'])-date.fromisoformat(p['start'])).days

        originals=set(dates(p, first-timedelta(days=span), last))

        exceptions={e.original_date:e.payload for e in event.exceptions.all()}

        originals.update(exceptions)

        responses={(r.original_date,r.member_id):r for r in event.responses.all()}

        for original in sorted(originals):

            data=exceptions.get(original, shifted(p,original))

            if data is None: continue
            display_end=data['end']
            if not data['all_day'] and time.fromisoformat(data['end_time'])==time(0,0):
                display_end=(date.fromisoformat(data['end'])-timedelta(days=1)).isoformat()
            if data['start'] > last.isoformat() or display_end < first.isoformat(): continue

            if selected=='shared' and data['scope']!='shared': continue

            if selected not in ('all','shared') and (data['scope']!='selected' or selected not in data['participants']): continue

            people=[]

            for person in eligible(data,members):

                response=responses.get((original,person.pk))

                people.append({'id':person.pk,'name':person.user.get_full_name() or person.user.email,'status':response.status if response else 'none','revision':response.revision if response else 0,'self':person.pk==member.pk})

            warning=''

            if not data['all_day']:

                try:

                    local_time(date.fromisoformat(data['start']),data['start_time'],data.get('fold'))

                    local_time(date.fromisoformat(data['end']),data['end_time'],data.get('fold'))

                except ValidationError as error: warning=' '.join(error.messages)

            result.append({'id':str(event.pk),'original':original.isoformat(),'revision':event.revision,'editable':event.created_by_id==actor.pk or member.role=='admin','people':people,'warning':warning,'display_end':display_end,'exception':original in exceptions,'canonical_id':str(event.series_key)+':'+original.isoformat(),'future_exceptions':[{'original':d.isoformat(),'start':v.get('start') if v else None,'title':v.get('title') if v else 'Slettet forekomst'} for d,v in sorted(exceptions.items()) if d>=original],**data})

    return sorted(result,key=lambda x:(x['start'],x.get('start_time') or '',x['title']))

@transaction.atomic

def mutate(actor, action, key, event_id=None, original=None, revision=None, payload=None, scope='one', status=None, response_revision=None):

    if not isinstance(action,str) or not isinstance(scope,str): raise ValidationError('Ugyldig handling.')

    member=membership(actor)

    Household.objects.select_for_update().get(pk=member.household_id)

    try: key=uuid.UUID(str(key))

    except (TypeError,ValueError): raise ValidationError('Forespørselen mangler en gyldig lagringsnøkkel.')

    digest=hashlib.sha256(json.dumps([action,str(event_id),str(original),revision,payload,scope,status,response_revision],sort_keys=True).encode()).hexdigest()

    prior=CalendarRequest.objects.filter(household=member.household,key=key).first()

    if prior:

        if prior.actor_id!=actor.pk or prior.digest!=digest: raise Conflict('Lagringsnøkkelen er allerede brukt til en annen endring.')

        return prior.result

    event=None

    if action!='create':

        try: event_id=uuid.UUID(str(event_id))

        except (TypeError,ValueError): raise ValidationError('Ugyldig avtaleidentitet.')

        try: event=CalendarEvent.objects.select_for_update().get(pk=event_id,household=member.household,deleted=False)

        except CalendarEvent.DoesNotExist: raise PermissionDenied('Ingen tilgang til avtalen.')

        if type(revision) is not int or revision!=event.revision: raise Conflict('Avtalen er endret. Last inn på nytt før du lagrer.')

        try: original=date.fromisoformat(str(original))

        except ValueError: raise ValidationError('Ugyldig forekomstdato.')

        current=occurrence(event,original)

        if action!='respond' and event.created_by_id!=actor.pk and member.role!='admin': raise PermissionDenied('Bare oppretter eller administrator kan endre avtalen.')

    if action=='create':

        p=validate_payload(payload,member.household)

        event=CalendarEvent.objects.create(household=member.household,created_by=actor,payload=p)

    elif action=='respond':

        if status not in ('none','yes','no'): raise ValidationError('Ugyldig svar.')

        if member.pk not in {m.pk for m in eligible(current,[member])}: raise PermissionDenied('Du er ikke deltaker i avtalen.')

        response=CalendarResponse.objects.filter(event=event,original_date=original,member=member).first()

        if type(response_revision) is not int or response_revision!=(response.revision if response else 0): raise Conflict('Svaret er endret. Last inn på nytt.')

        if response:

            response.status=status; response.revision+=1; response.save()

        else: CalendarResponse.objects.create(event=event,original_date=original,member=member,status=status)

    elif action in ('edit','delete'):

        if scope not in ('one','future'): raise ValidationError('Velg bare denne eller denne og fremtidige.')

        p=None
        if action=='edit':
            if scope=='one' and isinstance(payload,dict):
                if payload.get('recurrence')!=current['recurrence'] or (payload.get('until') or None)!=current.get('until'): raise ValidationError('Gjentakelse og serieslutt kan bare endres for denne og fremtidige.')
                # The end of a series limits original dates, not where an exception may move.
                p=validate_payload({**payload,'recurrence':'none','until':None},member.household)
                p['recurrence'],p['until']=current['recurrence'],current.get('until')
            else:
                p=validate_payload(payload,member.household)

        if p and p['recurrence']=='monthly' and p['start']==current['start'] and event.payload['recurrence']=='monthly':

            p['anchor_day']=event.payload.get('anchor_day',date.fromisoformat(event.payload['start']).day)

        if p and scope=='future' and event.payload['recurrence']!='none' and date.fromisoformat(p['start']) < original:
            raise ValidationError('Denne og fremtidige kan ikke starte før den valgte originaldatoen. Flytt bare denne avtalen for å bevare tidligere avtaler.')
        reset=p is None or any(p.get(k)!=current.get(k) for k in ('start','end','all_day','start_time','end_time','fold','scope','participants'))

        if scope=='one' or event.payload['recurrence']=='none':

            CalendarException.objects.update_or_create(event=event,original_date=original,defaults={'payload':p})

            if reset: event.responses.filter(original_date=original).delete()

        else:

            old_payload=event.payload
            old_exceptions={ex.original_date:ex.payload for ex in event.exceptions.filter(original_date__gte=original)}
            event.payload={**event.payload,'until':(original-timedelta(days=1)).isoformat()}

            event.exceptions.filter(original_date__gte=original).delete()

            if action=='edit':

                # A new segment retains creator and family; old segment and prior exceptions remain intact.

                future=CalendarEvent.objects.create(household=event.household,created_by=event.created_by,payload=p,series_key=event.series_key)

                # Replacing future exceptions may change a particular occurrence even when
                # the cutoff edit changes only metadata. Reconcile each original separately.
                material=('start','end','all_day','start_time','end_time','fold','scope','participants')
                for response in event.responses.filter(original_date__gte=original):
                    day=response.original_date
                    before=old_exceptions.get(day,shifted(old_payload,day))
                    if before is None or day not in dates(p,day,day): continue
                    after=shifted(p,day)
                    if any(before.get(k)!=after.get(k) for k in material): continue
                    if after['scope']=='selected' and str(response.member_id) not in after['participants']: continue
                    response.event=future; response.save(update_fields=['event'])

            event.responses.filter(original_date__gte=original).delete()

        event.revision+=1; event.save()

    else: raise ValidationError('Ugyldig handling.')

    result={'id':str(event.pk),'revision':event.revision}

    CalendarRequest.objects.create(household=member.household,actor=actor,key=key,digest=digest,result=result)

    return result

