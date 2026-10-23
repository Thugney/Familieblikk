"""Read-only monthly plans and obligations, using the same fund replay as writes."""
from collections import defaultdict
from types import SimpleNamespace
import calendar
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .financial_areas import current_area
from .models import Asset, BillOccurrence, BillTemplate, Entry, MonthPlan


def replay_fund(asset, plans, bills, entries):
    """Pure chronological fund accounting; return required top-ups and balances."""
    from .services import month_start
    events = [(plan.month, 0, 0, 'allocation', plan) for plan in plans]
    ordered_bills = sorted(bills, key=lambda row: (row.due_date, str(row.pk)))
    events.extend((bill.due_date, 1, index, 'due', bill)
                  for index, bill in enumerate(b for b in ordered_bills if not b.cancelled))
    events.extend((entry.effective_date, 2, entry.sequence, 'entry', entry) for entry in entries)
    balance, reserved, desired, settled = asset.opening_ore, {}, {}, set()
    for day, priority, sequence, kind, row in sorted(events, key=lambda event: event[:3]):
        if kind == 'allocation':
            balance += row.amount_ore
            continue
        if day < asset.opening_date:
            raise ValidationError('Fondsforpliktelse eller betaling er før åpningsdato.')
        if kind == 'due':
            if row.pk in settled:
                continue
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
    return {'topups': desired, 'balance': balance, 'reserved': sum(reserved.values())}


def _effective_amount(group, period, current_month, archived):
    """Mirror prepare_month/refresh_future_plans without storing missing copies."""
    from .services import plan_amount
    applicable = [row for row in group if row.month <= period]
    exact = next((row for row in applicable if row.month == period), None)
    if exact and (not exact.derived or period < current_month):
        return exact.amount_ore
    if not exact and archived and period > current_month:
        return None
    anchors = [row for row in applicable if not row.derived]
    return plan_amount(anchors[-1], period) if anchors else exact.amount_ore if exact else None


def month_basis(household, month, today=None):
    """Return effective limits/plans, pending bill dictionaries and fund projections.

    UUIDs remain UUIDs in category/asset keys. Pending due_date is a date; id is a
    string and virtual distinguishes unmaterialized occurrences. No rows are saved.
    Actual payments/refunds stop at today even when projecting a future month.
    """
    from .services import month_start, month_end, next_month
    from .correction_services import series_state
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    today = today or timezone.localdate()
    start, end, current_month = month_start(month), month_end(month), month_start(today)
    cutoff = min(today, end)
    assets = list(Asset.objects.filter(household=household))
    groups, targets = defaultdict(list), {}
    for row in MonthPlan.objects.filter(household=household).select_related('asset', 'category').order_by('month'):
        key = (row.category_id, row.asset_id)
        groups[key].append(row)
        targets[key] = row.asset or row.category
    for asset in assets:
        key = (None, asset.pk)
        group = groups[key]
        targets[key] = asset
        if asset.kind == 'fund' and asset.target_ore and not any(not row.derived for row in group):
            # The same implicit annual anchor prepare_month creates on first use.
            effective = month_start(asset.opening_date)
            amount = asset.target_ore // 12 + (asset.target_ore % 12 if effective.month == 12 else 0)
            group.append(MonthPlan(asset=asset, month=effective, amount_ore=amount,
                                   annual_total_ore=asset.target_ore))
            group.sort(key=lambda row: row.month)
    category_limits, asset_plans = {}, {}
    for key, group in groups.items():
        amount = _effective_amount(group, start, current_month, targets[key].archived)
        if amount is not None:
            (category_limits if key[0] else asset_plans)[key[0] or key[1]] = amount

    materialized = list(BillOccurrence.objects.filter(household=household))
    slots = {(row.template_id, row.recurrence_slot) for row in materialized}
    bills = [row for row in materialized if row.due_date <= end]
    for template in BillTemplate.objects.filter(household=household, first_due__lte=end):
        cursor = month_start(template.first_due)
        while cursor <= start:
            if (template.pk, cursor) not in slots:
                due = cursor.replace(day=min(template.first_due.day, calendar.monthrange(cursor.year, cursor.month)[1]))
                enabled, values = series_state(template, due)
                if enabled:
                    category_id = values.get('category_id')
                    bills.append(SimpleNamespace(
                        pk=f'virtual:{template.pk}:{cursor.isoformat()}', name=values['name'],
                        due_date=due, amount_ore=values['amount_ore'],
                        accounting_class=template.accounting_class, asset_id=template.asset_id,
                        category_id=uuid.UUID(str(category_id)) if category_id else None,
                        cancelled=False,
                    ))
            if not template.monthly or cursor.year == 9999 and cursor.month == 12:
                break
            cursor = next_month(cursor)
    actual = list(Entry.objects.filter(household=household, active=True, effective_date__lte=cutoff)
                  .filter(kind__in=['fund', 'refund']).select_related('original'))
    paid = set(Entry.objects.filter(household=household, active=True,
               effective_date__lte=cutoff, occurrence__isnull=False).values_list('occurrence_id', flat=True))
    pending = [{
        'id': str(row.pk), 'name': row.name, 'due_date': row.due_date,
        'amount_ore': row.amount_ore, 'accounting_class': row.accounting_class,
        'category_id': row.category_id, 'asset_id': row.asset_id,
        'virtual': isinstance(row.pk, str),
    } for row in bills if not row.cancelled and row.pk not in paid]
    pending.sort(key=lambda row: (row['due_date'], row['id']))
    fund_topups, fund_balances = {}, {}
    for asset in assets:
        if asset.kind != 'fund':
            continue
        group = groups[(None, asset.pk)]
        allocations = []
        cursor = min((row.month for row in group), default=start)
        while cursor <= start:
            amount = _effective_amount(group, cursor, current_month, asset.archived)
            if amount is not None:
                allocations.append(SimpleNamespace(month=cursor, amount_ore=amount))
            if cursor.year == 9999 and cursor.month == 12:
                break
            cursor = next_month(cursor)
        movements = [row for row in actual if row.kind == 'fund' and row.asset_id == asset.pk
                     or row.kind == 'refund' and row.original_id
                     and row.original.kind == 'fund' and row.original.asset_id == asset.pk]
        replay = replay_fund(asset, allocations,
                             [row for row in bills if row.accounting_class == 'fund' and row.asset_id == asset.pk], movements)
        fund_topups[asset.pk] = sum(amount for period, amount in replay['topups'].values() if period == start)
        fund_balances[asset.pk] = replay['balance'] if end >= asset.opening_date else 0
    return {'category_limits': category_limits, 'asset_plans': asset_plans, 'pending': pending,
            'fund_topups': fund_topups, 'fund_balances': fund_balances}
