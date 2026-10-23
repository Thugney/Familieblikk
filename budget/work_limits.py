"""Explicit, fail-closed limits for date-driven financial replay.

No history is truncated: callers must reject the whole calculation if it exceeds
50 years per series or 10,000 generated monthly steps across the selected area.
HTTP requests share one cumulative budget, reset even after a rejected request.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps


MAX_MONTHS = 600
MAX_MONTH_STEPS = 10_000
_request_work = ContextVar('financial_request_work', default=None)


@contextmanager
def financial_work_scope():
    token = _request_work.set(0)
    try:
        yield
    finally:
        _request_work.reset(token)


def financial_work_operation(function):
    """Keep nested service work cumulative outside HTTP requests as well."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _request_work.get() is not None:
            return function(*args, **kwargs)
        with financial_work_scope():
            return function(*args, **kwargs)
    return wrapped


def reserve_work(steps):
    used = _request_work.get()
    if steps > MAX_MONTH_STEPS or used is not None and used + steps > MAX_MONTH_STEPS:
        raise FinancialWorkLimit()
    if used is not None:
        _request_work.set(used + steps)


class FinancialWorkLimit(ValidationError):
    def __init__(self):
        super().__init__('Perioden eller kildehistorikken er for omfattende. Beregningen er begrenset til 50 år per serie og 10 000 månedstrinn samlet. Ingen historikk er forkortet; kontroller datoene.')


def month_number(day):
    return day.year * 12 + day.month - 1


def validate_period(day):
    if abs(month_number(day) - month_number(timezone.localdate())) >= MAX_MONTHS:
        raise FinancialWorkLimit()
    return day


def month_steps(first, last, *, recurring=True):
    count = max(0, month_number(last) - month_number(first) + 1)
    if not recurring:
        count = min(count, 1)
    if count > MAX_MONTHS:
        raise FinancialWorkLimit()
    return count


def validate_financial_work(household, month):
    """Check all anchors before any date loop or materialization write.

    Managers retain the active area's access scope. Count explicit anchors as the
    writer does, including overlaps and implicit fund anchors. Debt interest is
    charged at its actual replay entry point and date, never speculatively here.
    """
    from .models import Asset, BillTemplate, MonthPlan
    from django.db.models import Min
    validate_period(month)
    work = 0
    anchored_assets = set()
    for first, asset_id in MonthPlan.objects.filter(household=household, derived=False).values_list('month', 'asset_id'):
        work += month_steps(first, month)
        anchored_assets.add(asset_id)
        if work > MAX_MONTH_STEPS:
            raise FinancialWorkLimit()
    for first, recurring in BillTemplate.objects.filter(household=household).values_list('first_due', 'monthly'):
        work += month_steps(first, month, recurring=recurring)
        if work > MAX_MONTH_STEPS:
            raise FinancialWorkLimit()
    for pk, first in Asset.objects.filter(household=household, kind='fund', target_ore__gt=0).values_list('pk', 'opening_date'):
        if pk not in anchored_assets:
            work += month_steps(first, month)
        if work > MAX_MONTH_STEPS:
            raise FinancialWorkLimit()
    # Read-only fund replay also visits retained derived rows, even when their
    # original explicit anchor no longer exists. Budget that loop separately.
    for row in MonthPlan.objects.filter(household=household, asset__kind='fund').values('asset_id').annotate(first=Min('month')):
        work += month_steps(row['first'], month)
        if work > MAX_MONTH_STEPS:
            raise FinancialWorkLimit()
    reserve_work(work)
    return work
