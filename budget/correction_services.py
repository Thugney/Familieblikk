"""Atomic, retained corrections. Household locking serializes financial commands."""
import hashlib
import json
import uuid
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from . import access, services
from .models import (BillOccurrence, BillTemplate, Category, Entry, CorrectionCommand,
                     CorrectionEvent, SeriesRevision, Audit)


def snapshot(row):
    data = {f.attname: (getattr(row, f.attname).isoformat() if hasattr(getattr(row, f.attname), 'isoformat') else
                       str(getattr(row, f.attname)) if isinstance(getattr(row, f.attname), (uuid.UUID, Decimal)) else getattr(row, f.attname))
            for f in row._meta.fields}
    if isinstance(row, Entry) and row.occurrence_id: data['occurrence_version'] = row.occurrence.version
    return data


def record(actor, row, operation, before, reason='', command=None, reverses=None, effective_date=None):
    return CorrectionEvent.objects.create(household=row.household, actor=actor,
        object_type=row._meta.model_name, object_id=row.pk, operation=operation, reason=reason,
        before=before, after=snapshot(row), effective_date=effective_date or getattr(row, 'effective_date', getattr(row, 'due_date', None)),
        command=command, reverses=reverses)


def authorize_snapshot(member, model, data):
    if not data: return
    fields = {f.attname for f in model._meta.fields}
    values = {}
    for field in model._meta.fields:
        if field.attname in data:
            values[field.attname] = (field.target_field if field.is_relation else field).to_python(data[field.attname])
    from .financial_areas import current_area
    if 'financial_area_id' not in values:
        values['financial_area_id'] = current_area(member).pk
    probe = model(**values)
    access.lock_relations(member, probe)
    access.require_row(member, probe)


@transaction.atomic
def visible_history(member, row):
    access.require_row(member, row)
    result = []
    for event in CorrectionEvent.objects.filter(household=member.household, object_type=row._meta.model_name, object_id=row.pk).order_by('-id'):
        try:
            authorize_snapshot(member, type(row), event.before)
            authorize_snapshot(member, type(row), event.after)
        except (PermissionDenied, ValidationError, Entry.DoesNotExist):
            continue
        event.subject = row
        event.subject_kind = 'bill' if isinstance(row, BillOccurrence) else 'series' if isinstance(row, BillTemplate) else 'entry'
        result.append(event)
    if isinstance(row, BillOccurrence):
        for payment in row.payments.all():
            try:
                access.require_row(member, payment)
                result.extend(visible_history(member, payment))
            except PermissionDenied:
                continue
    return sorted(result, key=lambda event: event.pk, reverse=True)


def begin(member, actor, row, operation, version, key, payload):
    digest = hashlib.sha256(json.dumps({'object': str(row.pk), 'operation': operation, 'version': version,
                                      'payload': payload}, sort_keys=True, default=str).encode()).hexdigest()
    old = CorrectionCommand.objects.filter(household=member.household, idempotency_key=key).first()
    if old:
        if old.actor_id != actor.pk or old.operation != operation or old.payload_hash != digest:
            raise services.Conflict('Nøkkelen er allerede brukt med annet innhold.')
        return old, True
    if row.version != version:
        raise services.Conflict('Posten er endret. Utkastet er beholdt; last inn ny versjon før bekreftelse.')
    cmd = CorrectionCommand.objects.create(household=member.household, actor=actor, operation=operation,
        idempotency_key=key, payload_hash=digest, result_id=row.pk, result_version=row.version + 1)
    return cmd, False


def finish(actor, row, command, before, reason, reverses=None):
    row.version += 1
    row.full_clean()
    row.save()
    event = record(actor, row, command.operation, before, reason, command, reverses)
    services.reconcile_funds(row.household, actor)
    return row


@transaction.atomic
def correct_occurrence(actor, row_id, operation, version, key, changes=None, reason='', event_id=None):
    member = access.lock_member(actor)
    row = BillOccurrence.objects.select_for_update().get(pk=row_id, household=member.household)
    access.lock_relations(member, row)
    services.authorize(actor, row)
    changes = changes or {}
    if set(changes) - {'name', 'amount_ore', 'due_date', 'category_id'}:
        raise ValidationError('Bare navn, beløp, kategori og forfall kan rettes.')
    cmd, replay = begin(member, actor, row, operation, version, key, {'changes': changes, 'reason': reason, 'event_id': event_id})
    if replay: return row
    if row.payment: raise ValidationError('Angre feilregistrert betaling først. Betalte regninger kan ikke endres eller avbrytes.')
    before = snapshot(row)
    event = None
    if operation == 'correct':
        if row.cancelled: raise ValidationError('Gjenopprett regningen før retting.')
        for field, value in changes.items(): setattr(row, field, value)
        row.individually_corrected = True
    elif operation == 'cancel':
        if row.cancelled: raise services.Conflict('Regningen er allerede avbrutt.')
        if not reason.strip(): raise ValidationError('Oppgi en begrunnelse for avbrytelsen.')
        row.cancelled = True
    elif operation == 'restore':
        event = CorrectionEvent.objects.get(pk=event_id, household=member.household, object_type='billoccurrence', object_id=row.pk)
        authorize_snapshot(member, BillOccurrence, event.before)
        if event.after.get('version') != row.version:
            raise services.Conflict('Nyere endring hindrer gjenoppretting.')
        if event.operation == 'cancel' and row.cancelled:
            row.cancelled = False
        elif event.operation in ('correct', 'restore'):
            for field in ('name', 'amount_ore', 'due_date', 'category_id', 'cancelled', 'individually_corrected'):
                value = event.before[field]
                if field == 'due_date': value = date.fromisoformat(value)
                setattr(row, field, value)
        else: raise ValidationError('Denne hendelsen kan ikke gjenopprettes.')
    else: raise ValidationError('Ukjent handling.')
    access.lock_relations(member, row)
    access.require_write_row(member, row)
    if row.amount_ore <= 0 or not row.name.strip(): raise ValidationError('Oppgi navn og positivt beløp.')
    if row.accounting_class == 'ordinary' and not row.category_id: raise ValidationError('Velg kategori.')
    return finish(actor, row, cmd, before, reason, event)


def payment_restore_conflict(row, event):
    if not row.occurrence_id: return ''
    payment = row.occurrence.payment
    if row.occurrence.cancelled or (payment and payment.pk != row.pk) or row.occurrence.version != event.after.get('occurrence_version'):
        return 'Regningen er endret eller har en nyere betaling. Denne betalingen kan ikke gjenopprettes.'
    return ''


@transaction.atomic
def entry_state(actor, row_id, operation, version, key, reason='', event_id=None):
    member = access.lock_member(actor)
    row = Entry.objects.select_for_update().get(pk=row_id, household=member.household)
    access.lock_relations(member, row)
    services.authorize(actor, row)
    cmd, replay = begin(member, actor, row, operation, version, key, {'reason': reason, 'event_id': event_id})
    if replay: return row
    before, event = snapshot(row), None
    if operation == 'reverse':
        if not row.active: raise services.Conflict('Posten er allerede reversert.')
        if row.refunds.filter(active=True).exists(): raise ValidationError('Betalingen har aktive refusjoner. Rett refusjonen uttrykkelig først.')
        if row.kind in ('deposit', 'withdrawal'): services.validate_savings(row.asset, exclude_id=row.pk)
        row.active = False
        row.reversed_at, row.reversed_by = timezone.now(), actor
    elif operation == 'restore':
        event = CorrectionEvent.objects.get(pk=event_id, household=member.household, object_type='entry', object_id=row.pk)
        authorize_snapshot(member, Entry, event.before)
        if event.after.get('version') != row.version or event.operation not in ('reverse', 'edit', 'restore'):
            raise services.Conflict('Nyere endring hindrer gjenoppretting.')
        if row.active and event.operation == 'reverse': raise services.Conflict('Posten er allerede aktiv.')
        if row.refunds.filter(active=True).exists(): raise ValidationError('Rett aktive refusjoner først.')
        conflict = payment_restore_conflict(row, event)
        if conflict: raise services.Conflict(conflict)
        if event.operation in ('edit', 'restore'):
            if row.kind in ('deposit', 'withdrawal') and (str(row.asset_id) != str(event.before.get('asset_id')) or event.before.get('kind') not in ('deposit', 'withdrawal')):
                services.validate_savings(row.asset, exclude_id=row.pk)
            for field in row._meta.fields:
                if field.name in ('id', 'household', 'financial_area', 'created_by', 'version', 'sequence', 'idempotency_key', 'created_at', 'updated_at'): continue
                if field.attname in event.before:
                    value = (field.target_field if field.is_relation else field).to_python(event.before[field.attname])
                    setattr(row, field.attname, value)
            access.lock_relations(member, row)
            access.require_write_row(member, row)
        else:
            row.active, row.reversed_at, row.reversed_by = True, None, None
        if not row.active and row.refunds.filter(active=True).exists(): raise ValidationError('Rett refusjoner først.')
        if row.active: services.validate_entry(row)
        if row.kind in ('deposit', 'withdrawal'): services.validate_savings(row.asset, row if row.active else None, row.pk)
    else: raise ValidationError('Ukjent handling.')
    if row.occurrence_id:
        row.occurrence.version += 1
        row.occurrence.save(update_fields=['version', 'updated_at'])
    result = finish(actor, row, cmd, before, reason, event)
    return result


def series_values(template):
    return {key: str(getattr(template, key)) if key == 'category_id' and getattr(template, key) else getattr(template, key)
            for key in ('name', 'amount_ore', 'category_id')}


def series_state(template, due):
    revisions = template.revisions.exclude(event__operation='series_baseline')
    revision = revisions.filter(effective_date__lte=due).order_by('-effective_date', '-id').first()
    baseline = template.revisions.filter(event__operation='series_baseline').order_by('id').first()
    enabled = baseline.enabled if baseline else not template.archived
    # A value-only revision never acts as an implicit resume, even when an earlier
    # archive is inserted after that revision was written.
    status = revisions.filter(effective_date__lte=due, event__operation__in=['archive', 'resume']).order_by('-effective_date', '-id').first()
    if status: enabled = status.enabled
    values = revision.values if revision else baseline.values if baseline else series_values(template)
    return enabled, values


def affected(template, start):
    boundary = template.revisions.exclude(event__operation='series_baseline').filter(effective_date__gt=start).order_by('effective_date').first()
    rows = BillOccurrence.objects.filter(template=template, cancelled=False, individually_corrected=False,
                                        due_date__gte=start, due_date__gt=timezone.localdate())
    if boundary: rows = rows.filter(due_date__lt=boundary.effective_date)
    return [row for row in rows.order_by('id') if not row.payment]


@transaction.atomic
def revise_series(actor, row_id, operation, version, key, start, changes=None, confirmed=None, reason=''):
    member = access.lock_member(actor)
    row = BillTemplate.objects.select_for_update().get(pk=row_id, household=member.household)
    access.lock_relations(member, row)
    services.authorize(actor, row)
    changes = changes or {}
    if set(changes) - {'name', 'amount_ore', 'category_id'}: raise ValidationError('Opprett ny serie for annen klasse, kobling eller rytme.')
    if start <= timezone.localdate(): raise ValidationError('Virkningsdato må være etter i dag.')
    targets = affected(row, start) if operation == 'revise' else []
    for target in targets: services.authorize(actor, target)
    manifest = [[str(target.pk), target.version] for target in targets]
    for target_id, _ in confirmed or []:
        target = BillOccurrence.objects.select_for_update().get(pk=target_id, household=member.household, template=row)
        services.authorize(actor, target)
    cmd, replay = begin(member, actor, row, operation, version, key, {'start': start, 'changes': changes, 'confirmed': confirmed, 'reason': reason})
    if replay: return row
    if confirmed != manifest: raise services.Conflict('Listen over berørte regninger er endret. Se gjennom og bekreft på nytt.')
    before = snapshot(row)
    enabled, values = series_state(row, start)
    before.update(values, archived=not enabled)
    if not row.revisions.exists():
        baseline_event = record(actor, row, 'series_baseline', before, command=cmd, effective_date=row.first_due)
        SeriesRevision.objects.create(template=row, effective_date=date.min, enabled=not row.archived, values=series_values(row), event=baseline_event)
    if operation not in ('revise', 'archive', 'resume'): raise ValidationError('Ukjent seriehandling.')
    for field, value in {**values, **changes}.items(): setattr(row, field, value)
    access.lock_relations(member, row)
    access.require_write_row(member, row)
    if row.accounting_class == 'ordinary' and not row.category_id: raise ValidationError('Velg kategori for en vanlig regning.')
    if operation == 'archive': enabled = False
    elif operation == 'resume': enabled = True
    row.archived = not enabled
    row.version += 1
    row.full_clean()
    row.save()
    event = record(actor, row, operation, before, reason, cmd, effective_date=start)
    SeriesRevision.objects.create(template=row, effective_date=start, enabled=not row.archived, values=series_values(row), event=event)
    for target in targets:
        old = snapshot(target)
        for field, value in changes.items(): setattr(target, field, value)
        target.version += 1
        target.full_clean(); target.save()
        record(actor, target, 'series_revision', old, reason, cmd)
    services.reconcile_funds(member.household, actor)
    return row


def economic_preview(actor, mutate, dates):
    """Run the real command and accounting in isolated savepoints; persist nothing."""
    from django.db.models import Max, Min
    from .models import MonthPlan, FundTopUp, Asset
    with transaction.atomic():
        member = access.lock_member(actor)
        supplied = [day for day in dates if day is not None]
        if not supplied: supplied = [timezone.localdate()]
        first = services.month_start(min(supplied))
        last = max(supplied + [timezone.localdate()])
        for model, field in ((Entry, 'effective_date'), (BillOccurrence, 'due_date'), (MonthPlan, 'month'), (FundTopUp, 'effective_month')):
            latest = model.objects.filter(household=member.household).aggregate(day=Max(field))['day']
            if latest: last = max(last, latest)
        last = services.month_start(last)
        computation_start = first
        for model, field in ((BillTemplate, 'first_due'), (MonthPlan, 'month'), (Asset, 'opening_date')):
            earliest = model.objects.filter(household=member.household).aggregate(day=Min(field))['day']
            if earliest: computation_start = min(computation_start, services.month_start(earliest))
        if (last.year-computation_start.year)*12 + last.month-computation_start.month + 1 > 120:
            raise ValidationError('Forhåndsvisningen omfatter mer enn 120 måneder. Velg en nærmere dato, eller be administrator om en avgrenset gjennomgang av den lange historikken. Ingen data er endret.')
        assets = list(access.safe_rows(member, Asset.objects.filter(household=member.household, kind__in=['savings', 'debt', 'fund'])))
        assets = [asset for asset in assets if asset.kind == 'savings' or access.allows(member, 'bills')]
        balance_functions = {'savings':services.savings_balance, 'debt':services.estimated_debt_balance, 'fund':services.fund_balance}
        periods, cursor = [], first
        while cursor <= last:
            periods.append(cursor)
            if cursor.year == 9999 and cursor.month == 12: break
            cursor = services.next_month(cursor)

        def evaluate(apply):
            with transaction.atomic():
                if apply: mutate()
                result = {}
                for month in periods:
                    services.prepare_month(member.household, month)
                    result[month] = services.calculate(member.household, month)
                    result[month]['asset_balances'] = {str(asset.pk):balance_functions[asset.kind](asset,services.month_end(month)) for asset in assets}
                transaction.set_rollback(True)
            return result

        before, after = evaluate(False), evaluate(True)
        components = {'income': ('budget', 'Mottatt inntekt'), 'ordinary': ('budget', 'Vanlige utgifter netto'),
                      'bills': ('bills', 'Ubetalte vanlige regninger'), 'savings': ('savings', 'Disponert til sparing'),
                      'released': ('savings', 'Frigjort fra sparing'), 'debt': ('debt', 'Disponert til gjeld'),
                      'funds': ('fund', 'Avsetning og påfyll til fond')}
        result = []
        full = access.complete_finance(member)
        for month in periods:
            values = []
            for key, (module, label) in components.items():
                if not access.allows(member, module): continue
                # Composite fund accounting needs bill access, including hidden bill topups.
                if module in ('fund', 'debt') and not access.allows(member, 'bills'): continue
                delta = after[month][key] - before[month][key]
                if delta: values.append({'label': label, 'delta': delta})
            balances = []
            for asset in assets:
                old, new = before[month]['asset_balances'][str(asset.pk)], after[month]['asset_balances'][str(asset.pk)]
                if old != new:
                    balances.append({'name':asset.name, 'kind':asset.kind, 'before':old, 'after':new})
            delta = after[month]['available'] - before[month]['available']
            if balances or values or month in {services.month_start(d) for d in supplied}:
                result.append({'month': month, 'components': values, 'balances':balances, 'full': full,
                    'before': before[month]['available'] if full else None,
                    'after': after[month]['available'] if full else None, 'delta': delta if full else None})
        return result
