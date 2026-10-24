import copy
import csv
import io
import json
import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from . import access, services, correction_services as corrections
from .correction_forms import CorrectionForm, ExportForm
from .models import BillOccurrence, BillTemplate, Entry, Audit, CorrectionEvent, Category, Asset
from .views import NAV, error_text, selected_month

MODELS = {'bill': BillOccurrence, 'entry': Entry, 'series': BillTemplate}


def get_row(member, kind, row_id):
    if kind not in MODELS: raise Http404
    row = get_object_or_404(MODELS[kind], pk=row_id, household=member.household)
    access.require_row(member, row)
    return row


@login_required
@never_cache
@transaction.atomic
def correction_view(request, kind, row_id):
    member = access.lock_member(request.user)
    row = get_row(member, kind, row_id)
    row.display_name = getattr(row, 'name', getattr(row, 'description', ''))
    row.display_date = getattr(row, 'due_date', getattr(row, 'effective_date', getattr(row, 'first_due', None)))
    services.authorize(request.user, row)
    initial = {'version': row.version, 'key': uuid.uuid4(), 'operation': request.GET.get('operation', 'correct' if kind == 'bill' else 'revise' if kind == 'series' else 'reverse'),
               'event': request.GET.get('event'), 'name': getattr(row, 'name', ''), 'amount': Decimal(row.amount_ore) / 100,
               'due_date': getattr(row, 'due_date', None), 'category': row.category_id}
    recovering = request.method == 'POST' and request.POST.get('refresh_version') == '1'
    submitted = request.POST.copy() if request.method == 'POST' else None
    if recovering:
        submitted['version'], submitted['key'] = str(row.version), str(uuid.uuid4())
        submitted.pop('confirmation', None)
    form = CorrectionForm(submitted, member=member, row=row, kind=kind, initial=initial)
    preview, affected, token, status = None, [], None, 200
    if request.method == 'POST' and form.is_valid() and request.POST.get('edit_draft') != '1' and not recovering:
        data = form.cleaned_data
        changes = {k: data[k] for k in ('name', 'due_date') if k in data and data[k] is not None}
        if data.get('amount') is not None: changes['amount_ore'] = int(data['amount'] * 100)
        if 'category' in data: changes['category_id'] = str(data['category'].pk) if data['category'] else None
        if data['operation'] not in ('correct', 'revise'): changes = {}
        if kind == 'series' and data['operation'] == 'revise':
            affected = corrections.affected(row, data['start'])
            for target in affected: services.authorize(request.user, target)
        manifest = [[str(item.pk), item.version] for item in affected]
        payload = json.loads(json.dumps({'kind': kind, 'id': str(row.pk), 'data': {k: str(v.pk) if hasattr(v, 'pk') else v for k,v in data.items()}, 'manifest': manifest}, default=str))
        supplied = request.POST.get('confirmation')
        try:
            if supplied:
                try: saved = signing.loads(supplied, salt='bill-correction', max_age=3600)
                except signing.BadSignature: raise services.Conflict('Bekreftelsen er utløpt. Se gjennom på nytt.')
                submitted = {**payload, 'manifest': saved.get('manifest')}
                if saved != submitted: raise services.Conflict('Utkastet er endret. Se gjennom på nytt.')
                manifest = saved['manifest']
                if kind == 'bill': corrections.correct_occurrence(request.user, row.pk, data['operation'], data['version'], data['key'], changes, data['reason'], data.get('event'))
                elif kind == 'entry': corrections.entry_state(request.user, row.pk, data['operation'], data['version'], data['key'], data['reason'], data.get('event'))
                else: corrections.revise_series(request.user, row.pk, data['operation'], data['version'], data['key'], data['start'], changes, manifest, data['reason'])
                messages.success(request, 'Endringen er lagret. Historikken er bevart.')
                return redirect('correction_history', kind=kind, row_id=row.pk)
            if row.version != data['version']: raise services.Conflict('Posten er endret. Utkastet ditt er beholdt.')
            preview = {'before': row, 'after_name': changes.get('name', getattr(row, 'name', row.description if kind == 'entry' else '')),
                       'after_amount': changes.get('amount_ore', row.amount_ore), 'after_date': changes.get('due_date', getattr(row, 'due_date', getattr(row, 'effective_date', None))),
                       'operation': dict(form.fields['operation'].choices)[data['operation']],
                       'before_name': row.display_name, 'before_amount': row.amount_ore, 'before_date': row.display_date,
                       'before_category': row.category.name if row.category else 'Ingen kategori',
                       'after_category': data['category'].name if data.get('category') else 'Ingen kategori' if 'category' in data else row.category.name if row.category else 'Ingen kategori'}
            if kind == 'series':
                enabled, values = corrections.series_state(row, data['start'])
                category = Category.objects.filter(pk=values.get('category_id'), household=member.household).first()
                preview.update(before_name=values['name'], before_amount=values['amount_ore'], before_date=data['start'], before_category=category.name if category else 'Ingen kategori')
                if data['operation'] != 'revise':
                    preview.update(after_name=values['name'], after_amount=values['amount_ore'], after_date=data['start'], after_category=preview['before_category'])
            if kind == 'entry': preview['after_status'] = 'Reversert' if data['operation'] == 'reverse' else 'Aktiv'
            if data['operation'] == 'restore':
                event = get_object_or_404(CorrectionEvent, pk=data['event'], household=member.household, object_type=row._meta.model_name, object_id=row.pk)
                corrections.authorize_snapshot(member, type(row), event.before)
                if event.after.get('version') != row.version: raise services.Conflict('Nyere endring hindrer gjenoppretting.')
                preview.update(after_name=event.before.get('name', event.before.get('description', row.display_name)), after_amount=event.before.get('amount_ore', row.amount_ore), after_date=event.before.get('due_date', event.before.get('effective_date')), after_status='Avbrutt' if event.before.get('cancelled') else 'Reversert' if event.before.get('active') is False else 'Aktiv' if kind == 'entry' else 'Ubetalt')
                category_id = event.before.get('category_id')
                category = Category.objects.filter(pk=category_id, household=member.household).first() if category_id else None
                preview['after_category'] = category.name if category else 'Ingen kategori'
                preview['changes'] = financial_changes(member, corrections.snapshot(row), event.before)
            if preview.get('after_date') and isinstance(preview['after_date'], str):
                from datetime import date
                preview['after_date'] = date.fromisoformat(preview['after_date'])
            def mutate():
                if kind == 'bill': return corrections.correct_occurrence(request.user, row.pk, data['operation'], data['version'], data['key'], changes, data['reason'], data.get('event'))
                if kind == 'entry': return corrections.entry_state(request.user, row.pk, data['operation'], data['version'], data['key'], data['reason'], data.get('event'))
                return corrections.revise_series(request.user, row.pk, data['operation'], data['version'], data['key'], data['start'], changes, manifest, data['reason'])
            dates = [row.display_date, preview.get('after_date'), data.get('start')]
            if kind == 'entry' and row.occurrence_id: dates.append(row.occurrence.due_date)
            preview['effects'] = corrections.economic_preview(request.user, mutate, dates)
            token = signing.dumps(payload, salt='bill-correction')
        except ValidationError as exc:
            preview, token = None, None
            form.add_error(None, error_text(exc)); status = 409 if isinstance(exc, services.Conflict) else 400
    return render(request, 'budget/correction.html', {'title': 'Trygg retting', 'member': member, 'nav': NAV, 'row': row, 'kind': kind,
        'form': form, 'preview': preview, 'affected': affected, 'confirmation': token, 'recoverable':status == 409, 'recovered':recovering,
        'back': reverse('correction_history', args=[kind, row.pk])}, status=status)


@login_required
@never_cache
@transaction.atomic
def history_view(request, kind, row_id):
    member = access.lock_member(request.user)
    row = get_row(member, kind, row_id)
    row.display_name = getattr(row, 'name', getattr(row, 'description', ''))
    row.display_date = getattr(row, 'due_date', getattr(row, 'effective_date', getattr(row, 'first_due', None)))
    series_summary = None
    if kind == 'series':
        # The template stores the most recently written revision, which may be
        # future-dated or inserted out of order. Resolve the displayed date.
        row.display_date = selected_month(request)
        enabled, values = corrections.series_state(row, row.display_date)
        corrections.authorize_snapshot(member, BillTemplate,
            {**corrections.snapshot(row), **values, 'archived': not enabled})
        category = get_object_or_404(Category, pk=values['category_id'], household=member.household) if values.get('category_id') else None
        row.display_name = values['name']
        series_summary = {'amount_ore': values['amount_ore'], 'category': category,
                          'enabled': enabled, 'as_of': row.display_date}
    events = corrections.visible_history(member, row)
    for event in events:
        event.display_operation = {'correct':'Regningen er rettet', 'cancel':'Feilført regning avbrutt', 'reverse':'Feilregistrering angret', 'restore':'Tidligere tilstand gjenopprettet', 'edit':'Posten er rettet', 'create':'Post registrert', 'pay':'Betaling registrert', 'archive':'Serie arkivert', 'resume':'Serie gjenopptatt', 'revise':'Fremtidig serie endret', 'series_revision':'Regning endret med serien', 'series_baseline':'Opprinnelig serie bevart'}.get(event.operation, 'Endring registrert')
        event.display_changes = financial_changes(member, event.before, event.after)
        event.restore_explanation = ''
        event.can_restore = event.after.get('version') == event.subject.version and event.operation in ('cancel', 'correct', 'reverse', 'edit', 'restore') and event.subject_kind != 'series'
        if event.can_restore and isinstance(event.subject, Entry):
            event.restore_explanation = corrections.payment_restore_conflict(event.subject, event)
            if event.subject.refunds.filter(active=True).exists(): event.restore_explanation = 'Rett aktive tilbakebetalinger før gjenoppretting.'
            if event.restore_explanation: event.can_restore = False
        elif event.can_restore and isinstance(event.subject, BillOccurrence) and event.subject.payment:
            event.restore_explanation = 'Angre feilregistrert betaling før denne regningen kan gjenopprettes.'
            event.can_restore = False
    # Legacy audit has no full snapshots and is never represented as restorable.
    legacy = Audit.objects.filter(household=member.household, object_id=row.pk).exists()
    return render(request, 'budget/correction_history.html', {'title': 'Detaljer og endringer', 'member': member, 'nav': NAV, 'row': row,
        'kind': kind, 'events': events, 'legacy': legacy, 'series_summary': series_summary, 'month': services.month_start(row.display_date),
        'back_page': access.entry_page(member, row) if kind == 'entry' else 'regninger'})


def filtered_rows(member, kind, data):
    model, date_field = (BillOccurrence, 'due_date') if kind == 'bill' else (Entry, 'effective_date')
    rows = access.safe_rows(member, model.objects.filter(household=member.household)).select_related('category').order_by(date_field, 'pk')
    for bound, lookup in [('date_from', 'gte'), ('date_to', 'lte')]:
        if data.get(bound): rows = rows.filter(**{date_field + '__' + lookup: data[bound]})
    if data.get('category'): rows = rows.filter(category=data['category'])
    status = data.get('status')
    if kind == 'entry':
        if status: rows = rows.filter(active=status == 'active')
    elif status == 'cancelled': rows = rows.filter(cancelled=True)
    elif status in ('paid', 'unpaid'):
        rows = rows.filter(cancelled=False)
        payments = Entry.objects.filter(active=True, household=member.household, occurrence__isnull=False).values('occurrence_id')
        rows = rows.filter(pk__in=payments) if status == 'paid' else rows.exclude(pk__in=payments)
    return rows


def csv_text(value):
    text = str(value or '')
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


@login_required
@never_cache
@transaction.atomic
def export_view(request, kind):
    if kind not in ('bill', 'entry'): raise Http404
    member = access.lock_member(request.user)
    access.require(member, {'bills'} if kind == 'bill' else set())
    form = ExportForm(request.GET, member=member, kind=kind)
    rows = filtered_rows(member, kind, form.cleaned_data) if form.is_valid() else []
    for item in rows:
        item.display_name = getattr(item, 'name', getattr(item, 'description', ''))
        item.display_date = getattr(item, 'due_date', getattr(item, 'effective_date', None))
    basis = 'Forfallsdato' if kind == 'bill' else 'Økonomisk dato'
    if request.GET.get('download') == '1' and form.is_valid():
        output = io.StringIO(newline=''); writer = csv.writer(output, delimiter=';')
        writer.writerow(['Type', basis, 'Beskrivelse', 'Kategori', 'Beløp NOK', 'Status', 'Koblings-ID'])
        for row in rows:
            access.require_row(member, row)
            is_bill = kind == 'bill'
            state = ('Avbrutt' if row.cancelled else 'Betalt' if row.payment else 'Ubetalt') if is_bill else ('Aktiv' if row.active else 'Reversert')
            writer.writerow([csv_text('Regning' if is_bill else row.get_kind_display()), getattr(row, 'due_date' if is_bill else 'effective_date').isoformat(),
                csv_text(row.name if is_bill else row.description), csv_text(row.category.name if row.category else ''),
                f'{Decimal(row.amount_ore)/100:.2f}'.replace('.', ','), state, str(row.pk)])
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="familieblikk.csv"'
        return response
    return render(request, 'budget/correction_export.html', {'title': 'Utvalg og CSV', 'member': member, 'nav': NAV,
        'form': form, 'rows': rows, 'kind': kind, 'basis': basis})



def entry_edit_preview(request, member, form, candidate):
    """Validate the signed draft, or return a no-write accounting confirmation."""
    payload = json.loads(json.dumps({key: str(value.pk) if hasattr(value, 'pk') else value
                                   for key, value in form.cleaned_data.items()}, default=str))
    payload['entry_id'] = str(candidate.pk)
    if request.POST.get('confirmation'):
        try: saved = signing.loads(request.POST['confirmation'], salt='entry-edit', max_age=3600)
        except signing.BadSignature: raise services.Conflict('Bekreftelsen er utløpt. Se gjennom på nytt.')
        if saved != payload: raise services.Conflict('Utkastet er endret. Se gjennom på nytt.')
        return None
    current = Entry.objects.get(pk=candidate.pk, household=member.household)
    version = form.cleaned_data['version']
    if current.version != version: raise services.Conflict('Posten er endret. Utkastet ditt er beholdt.')
    services.authorize(request.user, current)
    effects = corrections.economic_preview(request.user,
        lambda: services.save_entry(request.user, copy.deepcopy(candidate), version, command_key=form.cleaned_data['command_key']),
        [current.effective_date, candidate.effective_date])
    return {'before': current, 'after': candidate, 'effects': effects,
            'changes': financial_changes(member, corrections.snapshot(current), corrections.snapshot(candidate)),
            'confirmation': signing.dumps(payload, salt='entry-edit')}



def financial_changes(member, before, after):
    labels = {'name':'Navn', 'description':'Beskrivelse', 'kind':'Posttype', 'amount_ore':'Beløp NOK',
        'category_id':'Kategori', 'asset_id':'Sparemål, gjeld, årsutgift eller mottaker', 'original_id':'Opprinnelig betaling',
        'occurrence_id':'Tilknyttet regning', 'effective_date':'Dato i budsjettet', 'due_date':'Forfall',
        'received':'Inntektsstatus', 'income_attribution':'Inntekten tilhører', 'currency':'Valuta',
        'original_amount':'Opprinnelig valutabeløp', 'exchange_rate':'NOK per valutaenhet', 'fee_ore':'Gebyr NOK',
        'accounting_class':'Hva gjelder regningen?', 'first_due':'Første forfall', 'monthly':'Gjentakelse',
        'active':'Poststatus', 'cancelled':'Regningsstatus', 'archived':'Seriestatus'}

    def display(field, value):
        if value is None or value == '': return '—'
        if field in ('amount_ore', 'fee_ore'):
            return f'{Decimal(value)/100:,.2f} kr'.replace(',', ' ').replace('.', ',')
        relations = {'category_id':Category, 'asset_id':Asset, 'original_id':Entry, 'occurrence_id':BillOccurrence}
        if field in relations:
            related = relations[field].objects.filter(pk=value, household=member.household).first()
            if not related: return 'Utilgjengelig kobling'
            if field != 'category_id': access.require_row(member, related)
            return getattr(related, 'name', getattr(related, 'description', ''))
        if field == 'kind':
            from .entry_presentation import ENTRY_LABELS
            return ENTRY_LABELS.get(value, value)
        if field == 'accounting_class': return {'ordinary':'Vanlig regning', 'debt':'Gjeld', 'fund':'Penger til årsutgifter'}.get(value, value)
        if field == 'received': return 'Mottatt' if value else 'Forventet'
        if field == 'active': return 'Registrert' if value else 'Angret – teller ikke i budsjettet'
        if field == 'cancelled': return 'Avbrutt' if value else 'Ikke avbrutt'
        if field == 'archived': return 'Stoppet fra valgt dato' if value else 'Aktiv fra valgt dato'
        if field == 'monthly': return 'Månedlig' if value else 'Engangsregning'
        return value

    return [{'label':label, 'before':display(field,before.get(field)), 'after':display(field,after[field])}
            for field,label in labels.items() if field in after and before.get(field) != after[field]]
