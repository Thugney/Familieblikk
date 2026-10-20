"""Familiepolicy og én autoritativ beregningsmotor. Alle penger er øre."""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Asset, Audit, BillOccurrence, BillTemplate, Entry, FundTopUp, Membership, MonthPlan


class Conflict(ValidationError):
    pass


def membership(user):
    return Membership.objects.select_related('household').get(user=user)


def authorize(actor, row=None, admin=False):
    member = membership(actor)
    if row is not None and row.household_id != member.household_id:
        raise PermissionDenied('Ingen tilgang til denne familien.')
    if (admin or (row is not None and row.created_by_id != actor.id)) and member.role != 'admin':
        raise PermissionDenied('Bare oppretteren eller en administrator kan endre posten.')
    return member


def month_start(day): return day.replace(day=1)
def month_end(day): return day.replace(day=calendar.monthrange(day.year, day.month)[1])
def next_month(day): return date(day.year + (day.month == 12), day.month % 12 + 1, 1)
def total(rows): return rows.aggregate(n=Sum('amount_ore'))['n'] or 0


@transaction.atomic
def save_row(actor, row, expected_version=None, admin=False):
    member = authorize(actor, row if not row._state.adding else None, admin)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    before = {}
    current = None
    if row._state.adding:
        row.household = member.household
        row.created_by = actor
    else:
        current = type(row).objects.select_for_update().get(pk=row.pk, household=member.household)
        before = {field.attname: str(getattr(current, field.attname)) for field in current._meta.fields if field.name not in ('updated_at', 'created_at')}
        if expected_version != current.version:
            raise Conflict('Posten er endret av noen andre. Last inn ny versjon; feltene dine er beholdt.')
        row.created_by_id = current.created_by_id
        row.version = current.version + 1
        if isinstance(row, Asset):
            if current.kind == "fund": prepare_month(member.household, month_start(timezone.localdate()))
            if current.kind != row.kind and (Entry.objects.filter(asset=current).exists() or MonthPlan.objects.filter(asset=current).exists() or BillTemplate.objects.filter(asset=current).exists() or BillOccurrence.objects.filter(asset=current).exists()):
                raise ValidationError('Typen kan ikke endres når oppsettet har finanshistorikk.')
            if row.kind == 'savings': validate_savings(row)
        if isinstance(row, BillTemplate):
            materialize_template(current, month_start(timezone.localdate()), cutoff=timezone.localdate())
            if current.accounting_class != row.accounting_class or current.asset_id != row.asset_id:
                raise ValidationError('Regnskapsklasse og målkobling er uforanderlige. Opprett en ny serie.')
            if current.first_due != row.first_due or current.monthly != row.monthly or (row.archived and not current.archived):
                future = BillOccurrence.objects.filter(template=current, due_date__gt=timezone.localdate(), payment__isnull=True)
                if FundTopUp.objects.filter(occurrence__in=future).exists():
                    raise ValidationError('Fremtidig serie har øremerket påfyll. Avstem forpliktelsene før forfallsendring.')
                future.delete()
    if isinstance(row, MonthPlan):
        if current and current.asset_id and current.asset.kind == "savings" and current.month < month_start(timezone.localdate()):
            raise ValidationError("Avsluttet spareplan kan ikke flyttes eller endres.")
        row.derived = False
    row.full_clean()
    row.save()
    if isinstance(row, Asset) and row.kind == "fund":
        effective = month_start(timezone.localdate()) if current else month_start(row.opening_date)
        amount = row.target_ore // 12 + (row.target_ore % 12 if effective.month == 12 else 0)
        anchor = MonthPlan.objects.filter(asset=row, month=effective).first()
        MonthPlan.objects.update_or_create(household=row.household, asset=row, month=effective, defaults={"created_by": row.created_by, "amount_ore": amount, "annual_total_ore": row.target_ore, "derived": False, "version": anchor.version + 1 if anchor else 1})
    if isinstance(row, (MonthPlan, Asset)):
        if isinstance(row, Asset) and row.archived:
            MonthPlan.objects.filter(asset=row, derived=True, month__gt=month_start(timezone.localdate())).delete()
        refresh_future_plans(member.household)
    if isinstance(row, BillTemplate):
        BillOccurrence.objects.filter(template=row, due_date__gt=timezone.localdate(), payment__isnull=True).update(name=row.name, amount_ore=row.amount_ore, category=row.category)
    if isinstance(row, (Asset, MonthPlan, BillTemplate, BillOccurrence)):
        reconcile_funds(member.household, actor)
    changes = {field.attname: {'before': before.get(field.attname), 'after': str(getattr(row, field.attname))} for field in row._meta.fields if field.name not in ('updated_at', 'created_at') and before.get(field.attname) != str(getattr(row, field.attname))}
    Audit.objects.create(household=member.household, actor=actor, object_id=row.pk, operation='lagret', changes=changes)
    return row


def validate_entry(row):
    if row.amount_ore <= 0:
        raise ValidationError('Beløpet må være positivt.')
    if row.effective_date > timezone.localdate() and not (row.kind == 'income' and not row.received):
        raise ValidationError('En faktisk post kan ikke ha fremtidig dato.')
    if row.kind in ('expense', 'remittance') and not row.category_id:
        raise ValidationError('Velg kategori.')
    required = {'deposit': 'savings', 'withdrawal': 'savings', 'debt': 'debt', 'fund': 'fund', 'remittance': 'recipient'}
    if row.kind in required and (not row.asset_id or row.asset.kind != required[row.kind]):
        raise ValidationError('Velg riktig mål eller kobling for posttypen.')
    if row.kind in ('income', 'expense') and row.asset_id:
        raise ValidationError('Vanlige inntekter og utgifter kan ikke samtidig føres mot gjeld, fond eller sparing.')
    if row.kind != 'refund' and row.original_id:
        raise ValidationError('Bare refusjoner kan kobles til opprinnelig betaling.')
    if row.kind == 'refund':
        if not row.original_id or row.original.kind not in ('expense', 'remittance', 'debt', 'fund'):
            raise ValidationError('Refusjonen må kobles til en betaling.')
        if row.effective_date < row.original.effective_date:
            raise ValidationError('Refusjonen kan ikke komme før betalingen.')
        refunded = total(row.original.refunds.exclude(pk=row.pk))
        if refunded + row.amount_ore > row.original.amount_ore:
            raise ValidationError('Refusjonene overstiger opprinnelig betaling.')
        row.category = row.original.category
        row.asset = row.original.asset
    if row.kind == 'remittance':
        if not row.currency or len(row.currency) != 3 or not row.original_amount or row.original_amount <= 0:
            raise ValidationError('Oppgi ISO-valuta og opprinnelig positivt beløp.')
        if row.exchange_rate is not None:
            if row.exchange_rate <= 0:
                raise ValidationError('Kursen må være positiv og bekreftet.')
            row.amount_ore = int((row.original_amount * row.exchange_rate * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) + row.fee_ore


def validate_savings(asset, candidate=None, exclude_id=None):
    events = list(Entry.objects.filter(asset=asset, kind__in=['deposit', 'withdrawal']).exclude(pk=exclude_id).order_by('effective_date', 'created_at'))
    if candidate: events.append(candidate)
    balance = asset.opening_ore
    for event in sorted(events, key=lambda item: (item.effective_date, item.sequence or 2**63)):
        if event.effective_date < asset.opening_date:
            raise ValidationError('Posten er før dokumentert åpningssaldo.')
        balance += event.amount_ore * (-1 if event.kind == 'withdrawal' else 1)
        if balance < 0:
            raise ValidationError('Uttaket gir negativ målbeholdning på denne eller en senere dato.')


@transaction.atomic
def save_entry(actor, row, expected_version=None):
    member = authorize(actor, row if not row._state.adding else None)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    row.household = member.household
    row.clean()
    if row.original_id:
        Entry.objects.select_for_update().get(pk=row.original_id, household=member.household)
    if row.asset_id:
        Asset.objects.select_for_update().get(pk=row.asset_id, household=member.household)
    current = None
    if not row._state.adding:
        current = Entry.objects.get(pk=row.pk, household=member.household)
        if current.occurrence_id:
            raise ValidationError('Bruk Angre betaling før en koblet betaling endres.')
        if current.refunds.exists():
            raise ValidationError('Betalingen har refusjoner og må korrigeres samlet.')
        if current.kind in ('deposit', 'withdrawal') and (current.asset_id != row.asset_id or row.kind not in ('deposit', 'withdrawal')):
            Asset.objects.select_for_update().get(pk=current.asset_id)
            validate_savings(current.asset, exclude_id=current.pk)
    else:
        existing = Entry.objects.filter(household=member.household, idempotency_key=row.idempotency_key).first()
        if existing: return existing
    validate_entry(row)
    if row.kind in ('deposit', 'withdrawal'): validate_savings(row.asset, row, row.pk)
    if row.kind == 'fund' and not row.occurrence_id:
        if row.effective_date < row.asset.opening_date:
            raise ValidationError('Fondsbetalingen er før dokumentert åpningsavsetning.')
        prepare_month(member.household, month_start(row.effective_date))
        balance = fund_balance(row.asset, month_end(row.effective_date))
        if current and current.kind == 'fund' and current.asset_id == row.asset_id and current.effective_date <= month_end(row.effective_date):
            balance += current.amount_ore
        if balance < row.amount_ore:
            gap = row.amount_ore - balance
            raise ValidationError(f'Finansieringsgap: {Decimal(gap) / 100:.2f} NOK. Opprett en engangsregning koblet til årsfondet og merk den betalt. Da opprettes ett sporbart påfyll før oppgjøret.')
    saved = save_row(actor, row, expected_version)
    reconcile_funds(member.household, actor)
    return saved


@transaction.atomic
def delete_entry(actor, entry_id, version):
    member = membership(actor)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    row = Entry.objects.select_for_update().get(pk=entry_id, household=member.household)
    authorize(actor, row)
    if row.version != version: raise Conflict('Posten er endret. Last inn på nytt.')
    if row.refunds.exists(): raise ValidationError('Fjern tilknyttede refusjoner først.')
    if row.kind in ('deposit', 'withdrawal'):
        Asset.objects.select_for_update().get(pk=row.asset_id)
        validate_savings(row.asset, exclude_id=row.pk)
    Audit.objects.create(household=member.household, actor=actor, object_id=row.pk, operation='slettet', changes={'kind': row.kind})
    row.delete()
    reconcile_funds(member.household, actor)


def plan_amount(anchor, month):
    if anchor.annual_total_ore is not None:
        return anchor.annual_total_ore // 12 + (anchor.annual_total_ore % 12 if month.month == 12 else 0)
    return anchor.amount_ore


def refresh_future_plans(household):
    for plan in MonthPlan.objects.filter(household=household, derived=True, month__gte=month_start(timezone.localdate())):
        anchors = MonthPlan.objects.filter(household=household, derived=False, month__lte=plan.month, asset_id=plan.asset_id, category_id=plan.category_id).order_by('-month')
        anchor = anchors.first()
        if anchor:
            amount = plan_amount(anchor, plan.month)
            if plan.amount_ore != amount:
                plan.amount_ore = amount
                plan.version += 1
                plan.save(update_fields=['amount_ore', 'version'])


def materialize_template(template, month, cutoff=None):
    cursor = month_start(template.first_due)
    while cursor <= month:
        due = cursor.replace(day=min(template.first_due.day, calendar.monthrange(cursor.year, cursor.month)[1]))
        if (cutoff is None or due <= cutoff) and not BillOccurrence.objects.filter(template=template, due_date__year=cursor.year, due_date__month=cursor.month).exists():
            BillOccurrence.objects.get_or_create(template=template, due_date=due, defaults={'household': template.household, 'created_by': template.created_by, 'name': template.name, 'amount_ore': template.amount_ore, 'accounting_class': template.accounting_class, 'category': template.category, 'asset': template.asset})
        if not template.monthly or cursor.year == 9999 and cursor.month == 12: break
        cursor = next_month(cursor)


@transaction.atomic
def prepare_month(household, month):
    type(household).objects.select_for_update().get(pk=household.pk)
    month = month_start(month)
    for asset in household.asset_set.filter(kind='fund'):
        if not MonthPlan.objects.filter(asset=asset, derived=False).exists() and asset.target_ore:
            effective = month_start(asset.opening_date)
            MonthPlan.objects.create(household=household, created_by=asset.created_by, asset=asset, month=effective, amount_ore=asset.target_ore // 12 + (asset.target_ore % 12 if effective.month == 12 else 0), annual_total_ore=asset.target_ore)
    anchors = MonthPlan.objects.filter(household=household, derived=False).select_related('asset', 'category').order_by('month')
    for anchor in list(anchors):
        cursor = anchor.month
        while cursor <= month:
            if anchor.asset and anchor.asset.archived and cursor > month_start(timezone.localdate()): break
            if anchor.category and anchor.category.archived and cursor > month_start(timezone.localdate()): break
            latest = MonthPlan.objects.filter(household=household, derived=False, month__lte=cursor, asset_id=anchor.asset_id, category_id=anchor.category_id).order_by('-month').first()
            MonthPlan.objects.get_or_create(household=household, asset=anchor.asset, category=anchor.category, month=cursor, defaults={'created_by': anchor.created_by, 'amount_ore': plan_amount(latest, cursor), 'derived': True})
            if cursor.year == 9999 and cursor.month == 12: break
            cursor = next_month(cursor)
    refresh_future_plans(household)
    for template in BillTemplate.objects.filter(household=household, archived=False, first_due__lte=month_end(month)):
        materialize_template(template, month)
    reconcile_funds(household)


def pending_bills(household, end):
    return BillOccurrence.objects.filter(household=household, due_date__lte=end).filter(Q(payment__isnull=True) | Q(payment__effective_date__gt=end))


from django.db.models import Q


def fund_balance(asset, end):
    if end < asset.opening_date: return 0
    plans = total(MonthPlan.objects.filter(asset=asset, month__lte=end))
    topups = FundTopUp.objects.filter(occurrence__asset=asset, effective_month__lte=end).aggregate(n=Sum('amount_ore'))['n'] or 0
    payments = total(Entry.objects.filter(asset=asset, kind='fund', effective_date__lte=end))
    refunds = total(Entry.objects.filter(original__asset=asset, original__kind='fund', kind='refund', effective_date__lte=end))
    return asset.opening_ore + plans + topups - payments + refunds


def reconcile_funds(household, actor=None):
    """Spill av hele fondsløpet. Påfyll tilhører første forpliktelses-/betalingsmåned."""
    for asset in Asset.objects.filter(household=household, kind='fund'):
        events = []
        for plan in MonthPlan.objects.filter(asset=asset): events.append((plan.month, 0, 0, 'allocation', plan))
        bills = list(BillOccurrence.objects.filter(asset=asset, accounting_class='fund').order_by('due_date', 'id'))
        for index, bill in enumerate(bills): events.append((bill.due_date, 1, index, 'due', bill))
        entries = Entry.objects.filter(household=household).filter(Q(asset=asset, kind='fund') | Q(original__asset=asset, original__kind='fund', kind='refund'))
        for entry in entries: events.append((entry.effective_date, 2, entry.sequence, 'entry', entry))
        balance, reserved, desired, settled = asset.opening_ore, {}, {}, set()
        for day, priority, sequence, kind, row in sorted(events, key=lambda event: event[:3]):
            if kind == 'allocation':
                balance += row.amount_ore
                continue
            if day < asset.opening_date: raise ValidationError('Fondsforpliktelse eller betaling er før åpningsdato.')
            if kind == 'due':
                if row.pk in settled: continue
                gap = max(row.amount_ore - (balance - sum(reserved.values())), 0)
                desired[row.pk] = (month_start(day), gap)
                balance += gap
                reserved[row.pk] = row.amount_ore
            elif row.kind == 'refund':
                balance += row.amount_ore
            else:
                bill_id = row.occurrence_id
                if bill_id:
                    if bill_id not in reserved:
                        gap = max(row.amount_ore - (balance - sum(reserved.values())), 0)
                        desired[bill_id] = (month_start(day), gap)
                        balance += gap
                    reserved.pop(bill_id, None)
                    settled.add(bill_id)
                if balance - sum(reserved.values()) < row.amount_ore:
                    raise ValidationError('Endringen gir et udekket senere fondsoppgjør. Avstem forpliktelser og påfyll først.')
                balance -= row.amount_ore
        for bill in bills:
            old = FundTopUp.objects.filter(occurrence=bill).first()
            period, amount = desired.get(bill.pk, (month_start(bill.due_date), 0))
            if (amount or old) and (not old or old.amount_ore != amount or old.effective_month != period):
                topup, _ = FundTopUp.objects.update_or_create(occurrence=bill, defaults={'household': household, 'created_by': old.created_by if old else bill.created_by, 'effective_month': period, 'amount_ore': amount, 'version': old.version + 1 if old else 1})
                Audit.objects.create(household=household, actor=actor or bill.created_by, object_id=topup.pk, operation='fondspåfyll avstemt', changes={'amount_ore': {'before': old.amount_ore if old else None, 'after': amount}, 'effective_month': {'before': old.effective_month.isoformat() if old else None, 'after': period.isoformat()}})


def ensure_fund_topups(household, month):
    reconcile_funds(household)


@transaction.atomic
def pay_bill(actor, occurrence_id, effective_date, key):
    member = membership(actor)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    bill = BillOccurrence.objects.select_for_update().get(pk=occurrence_id, household=member.household)
    existing = Entry.objects.filter(occurrence=bill).first()
    if existing: return existing
    if effective_date < bill.created_at.date() and effective_date < bill.template.first_due:
        raise ValidationError('Betalingsdato er før forpliktelsen.')
    kind = {'ordinary': 'expense', 'debt': 'debt', 'fund': 'fund'}[bill.accounting_class]
    entry = Entry(household=member.household, created_by=actor, kind=kind, amount_ore=bill.amount_ore, effective_date=effective_date, description=bill.name, category=bill.category, asset=bill.asset, occurrence=bill, idempotency_key=key)
    validate_entry(entry)
    entry.full_clean()
    entry.save()
    reconcile_funds(member.household, actor)
    Audit.objects.create(household=member.household, actor=actor, object_id=bill.pk, operation='betalt', changes={'entry': str(entry.pk)})
    return entry


def calculate(household, month, today=None):
    today = today or timezone.localdate()
    start, end = month_start(month), month_end(month)
    entries = Entry.objects.filter(household=household, effective_date__range=(start, end))
    income = total(entries.filter(kind='income', received=True))
    expected = total(entries.filter(kind='income', received=False))
    ordinary = total(entries.filter(kind__in=['expense', 'remittance'])) - total(entries.filter(kind='refund', original__kind__in=['expense', 'remittance']))
    pending = pending_bills(household, end)
    bills = total(pending.filter(accounting_class='ordinary'))
    savings, released = 0, 0
    for asset in Asset.objects.filter(household=household, kind='savings'):
        net = total(entries.filter(asset=asset, kind='deposit')) - total(entries.filter(asset=asset, kind='withdrawal'))
        plan = total(MonthPlan.objects.filter(asset=asset, month=start))
        savings += max(plan, net, 0)
        released += max(-net, 0)
    debt = 0
    for asset in Asset.objects.filter(household=household, kind='debt'):
        paid = total(entries.filter(asset=asset, kind='debt')) - total(entries.filter(kind='refund', original__asset=asset, original__kind='debt'))
        debt += max(total(MonthPlan.objects.filter(asset=asset, month=start)), paid + total(pending.filter(asset=asset, accounting_class='debt')))
    funds = total(MonthPlan.objects.filter(household=household, asset__kind='fund', month=start)) + total(FundTopUp.objects.filter(household=household, effective_month=start))
    available = income + released - ordinary - bills - savings - debt - funds
    cash = income + total(entries.filter(kind='withdrawal')) - ordinary - total(entries.filter(kind__in=['debt', 'fund', 'deposit'])) + total(entries.filter(kind='refund', original__kind__in=['debt', 'fund']))
    return dict(income=income, expected=expected, ordinary=ordinary, bills=bills, savings=savings, released=released, debt=debt, funds=funds, available=available, cash=cash, daily=available // (end.day - today.day + 1) if start == month_start(today) else None)


def savings_balance(asset, end=None):
    if end and end < asset.opening_date: return 0
    rows = Entry.objects.filter(asset=asset)
    if end: rows = rows.filter(effective_date__lte=end)
    return asset.opening_ore + total(rows.filter(kind='deposit')) - total(rows.filter(kind='withdrawal'))


def debt_projection(assets, strategy='avalanche', extra_ore=0):
    """360 måneders estimat fra dokumentert referansesaldo, ikke bankbalanse."""
    if any(a.annual_rate is None for a in assets): return {'error': 'Manglende rente; ingen beregnbar sluttdato.'}
    balances = {str(a.pk): a.opening_ore for a in assets}
    ordered = sorted(assets, key=lambda a: (-a.annual_rate, str(a.pk)) if strategy == 'avalanche' else (a.opening_ore, str(a.pk)))
    minima = {str(a.pk): getattr(a, 'minimum_ore', 0) for a in assets}
    budget = sum(minima.values()) + extra_ore
    interest = 0
    for number in range(1, 361):
        for asset in assets:
            key = str(asset.pk)
            charge = int((Decimal(balances[key]) * asset.annual_rate / Decimal(1200)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            balances[key] += charge
            interest += charge
        remaining = budget
        for asset in assets:
            key = str(asset.pk)
            paid = min(balances[key], minima[key], remaining)
            balances[key] -= paid
            remaining -= paid
        for asset in ordered:
            key = str(asset.pk)
            paid = min(balances[key], remaining)
            balances[key] -= paid
            remaining -= paid
        if sum(balances.values()) == 0: return {'months': number, 'interest_ore': interest}
    return {'error': 'Ikke nedbetalt innen 30 år.'}


@transaction.atomic
def allocate_debt_plan(actor, month, strategy, extra_ore):
    member = authorize(actor, admin=True)
    type(member.household).objects.select_for_update().get(pk=member.household_id)
    if month.day != 1: raise ValidationError('Velg første dag i måneden.')
    debts = list(Asset.objects.filter(household=member.household, kind='debt', archived=False))
    if any(debt.annual_rate is None for debt in debts): raise ValidationError('Bekreft rente før planen fordeles.')
    balances = {debt.pk: estimated_debt_balance(debt, month_end(month)) for debt in debts}
    debts.sort(key=lambda item: (-item.annual_rate, str(item.pk)) if strategy == 'avalanche' else (balances[item.pk], str(item.pk)))
    remaining = extra_ore
    for debt in debts:
        outstanding = balances[debt.pk] or 0
        minimum = min(debt.minimum_ore, outstanding)
        extra = min(remaining, max(outstanding - minimum, 0))
        remaining -= extra
        plan, created = MonthPlan.objects.get_or_create(household=member.household, month=month, asset=debt, defaults={'created_by': actor, 'amount_ore': minimum + extra})
        if not created:
            plan.amount_ore = minimum + extra
            save_row(actor, plan, plan.version, True)
    if remaining:
        raise ValidationError('Ekstrabeløpet overstiger gjeld som kan fordeles. Ingen plan er endret.')


def ordinary_for_period(household, start, end):
    rows = Entry.objects.filter(household=household, effective_date__range=(start, end))
    return total(rows.filter(kind__in=['expense', 'remittance'])) - total(rows.filter(kind='refund', original__kind__in=['expense', 'remittance']))


def estimated_debt_balance(asset, as_of):
    """Rentemodell: månedlig etterskuddsrente på saldo ved hver referansedagsmarkering.

    Faktiske betalinger/refusjoner mellom markeringene påvirker neste rentebeløp.
    Ved samme dato beregnes rente før betaling. Dette er kun et merket anslag.
    """
    if asset.annual_rate is None or asset.opening_date > as_of:
        return None
    events = []
    for row in Entry.objects.filter(household=asset.household, effective_date__range=(asset.opening_date, as_of)).filter(Q(asset=asset, kind='debt') | Q(original__asset=asset, original__kind='debt', kind='refund')):
        events.append((row.effective_date, 1, row.sequence, -row.amount_ore if row.kind == 'debt' else row.amount_ore))
    cursor = next_month(month_start(asset.opening_date)) if asset.opening_date.year < 9999 or asset.opening_date.month < 12 else None
    while cursor and cursor <= as_of:
        anniversary = cursor.replace(day=min(asset.opening_date.day, month_end(cursor).day))
        if anniversary <= as_of: events.append((anniversary, 0, 0, None))
        cursor = next_month(cursor) if cursor.year < 9999 or cursor.month < 12 else None
    balance = asset.opening_ore
    for day, ordering, sequence, change in sorted(events):
        if change is None:
            balance += int((Decimal(max(balance, 0)) * asset.annual_rate / Decimal(1200)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        else:
            balance += change
    return max(balance, 0)
