"""Read-only exploration and explicitly confirmed future plans. Money is NOK øre."""
import calendar
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from .models import (Asset, Audit, BillOccurrence, BillTemplate, Category, Entry,
                     FundTopUp, Household, ImportRecord, Membership, MonthPlan,
                     MonthlyBudgetHeader, PlanningRequest)
from .services import Conflict, fund_balance, month_start, month_end, next_month, plan_amount
from .spending_forms import exact_fields, history_values, month_value, ore_value, uuid_value
from . import access

from .financial_areas import current_area, can_write

URLS = {'spending': '/app/forbruk/data/', 'planning': '/app/plan/data/',
        'preview': '/app/plan/preview/', 'save': '/app/plan/save/'}
UNCATEGORIZED = {'id': 'uncategorized', 'name': 'Uten kategori', 'color': '#718096'}


def membership(actor):
    try:
        return Membership.objects.select_related('household').get(user=actor)
    except Membership.DoesNotExist:
        raise PermissionDenied('Bli med i en familie for å bruke forbruk og planlegging.')


def month_key(value):
    return value.strftime('%Y-%m')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def ordinary_rows(household, start, end):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    return Entry.objects.filter(active=True, household=household, effective_date__range=(start, end)).filter(
        Q(kind__in=['expense', 'remittance']) |
        Q(kind='refund', original__kind__in=['expense', 'remittance'], original__household=household)
    ).select_related('category', 'original__category', 'original__occurrence')


def net_amount(row):
    return -row.amount_ore if row.kind == 'refund' else row.amount_ore


def row_category(row):
    return row.original.category if row.kind == 'refund' else row.category


def category_info(category):
    return {'id': str(category.pk), 'name': category.name, 'color': category.color} if category else dict(UNCATEGORIZED)


def coverage(household):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    count = ImportRecord.objects.filter(household=household, status='needs_review').count()
    return {'unresolved_import_count': count, 'completeness_confirmed': False,
            'warning': (f'{count} importutkast venter på avklaring og er ikke med i tallene. ' if count else '') +
                       'Registrerte poster viser kjent aktivitet; fullstendig månedsdekning er ikke bekreftet.'}


def period_bounds(params, today):
    period = params.get('period', 'month')
    selected = month_value(params.get('month') or month_key(today))
    if period == 'month':
        start, end = selected, month_end(selected)
    elif period == 'quarter':
        start = (selected - timedelta(days=1)).replace(day=1)
        start = (start - timedelta(days=1)).replace(day=1)
        end = month_end(selected)
    elif period == 'year':
        raw = params.get('year') or str(selected.year)
        if not isinstance(raw, str) or not raw.isdigit() or not 1901 <= int(raw) <= 2198:
            raise ValidationError('Velg et gyldig år.')
        start, end = date(int(raw), 1, 1), date(int(raw), 12, 31)
    elif period == 'custom':
        try:
            start, end = date.fromisoformat(params.get('start', '')), date.fromisoformat(params.get('end', ''))
        except (ValueError, TypeError):
            raise ValidationError('Velg gyldig start- og sluttdato.')
        if not 1901 <= start.year <= end.year <= 2198:
            raise ValidationError('Velg gyldige datoer.')
    else:
        raise ValidationError('Ugyldig periode.')
    if end < start or (end - start).days > 366 * 10:
        raise ValidationError('Velg et datospenn på høyst ti år med start før slutt.')
    if start > today:
        raise ValidationError('Perioden har ikke startet ennå. Velg en periode som starter senest i dag.')
    return start, min(end, today), end


def spending(actor, params, today=None):
    member = membership(actor)
    access.require(member, {'budget'})
    if params.get('period') == 'year': access.require(member, {'annual'})
    household = member.household
    today = today or timezone.localdate()
    first, last, requested = period_bounds(params, today)
    q = params.get('q', '').strip()
    if len(q) > 240:
        raise ValidationError('Søket kan ha inntil 240 tegn.')
    raw_categories = params.get('categories', '')
    selected = [x for x in raw_categories.split(',') if x]
    if len(selected) != len(set(selected)):
        raise ValidationError('Velg hver kategori bare én gang.')
    categories = list(Category.objects.filter(household=household).order_by('name', 'id'))
    known = {str(c.pk) for c in categories} | {'uncategorized'}
    if any(x not in known for x in selected):
        raise ValidationError('En valgt kategori finnes ikke i familien.')
    period_rows = list(access.safe_rows(member, ordinary_rows(household, first, last)))
    rows = []
    for row in period_rows:
        cat = category_info(row_category(row))
        if selected and cat['id'] not in selected:
            continue
        if q and q.casefold() not in (row.description + ' ' + cat['name']).casefold():
            continue
        rows.append(row)
    groups = {}
    for row in rows:
        cat = category_info(row_category(row))
        group = groups.setdefault(cat['id'], {**cat, 'amount_ore': 0, 'entry_count': 0})
        group['amount_ore'] += net_amount(row)
        group['entry_count'] += 1
    # A selected empty category remains explainable, without filling the graph with income categories.
    for cat in [category_info(c) for c in categories] + [UNCATEGORIZED]:
        if cat['id'] in selected and cat['id'] not in groups:
            groups[cat['id']] = {**cat, 'amount_ore': 0, 'entry_count': 0}
    warn = coverage(household) if access.complete_finance(member) else {
        'unresolved_import_count': 0, 'completeness_confirmed': False,
        'warning': 'Utvalg: bare poster fra tillatte moduler vises. Skjulte opplysninger og summer er utelatt.'}
    trend = []
    cursor = month_start(first)
    while cursor <= month_start(requested):
        found = [r for r in rows if month_start(r.effective_date) == cursor]
        has_entries = bool(found)
        trend.append({'month': month_key(cursor), 'amount_ore': sum(net_amount(r) for r in found) if has_entries else None,
                      'has_entries': has_entries, 'status': 'partial' if has_entries else 'missing',
                      'entry_count': len(found)})
        cursor = next_month(cursor)
    entries = sorted(rows, key=lambda r: (r.effective_date, r.sequence, str(r.pk)), reverse=True)
    raw_page = params.get('page', '1')
    if not isinstance(raw_page, str) or not raw_page.isdigit() or int(raw_page) < 1:
        raise ValidationError('Velg et gyldig sidetall.')
    paginator = Paginator(entries, 20)
    page = paginator.get_page(int(raw_page))
    serialized = []
    for row in page:
        cat = category_info(row_category(row))
        serialized.append({'id': str(row.pk), 'date': row.effective_date.isoformat(), 'description': row.description,
                           'kind': row.kind, 'amount_ore': net_amount(row), 'category_id': cat['id'],
                           'category_name': cat['name'], 'detail_url': reverse('edit', args=['entry', row.pk])})
    income_rows = Entry.objects.filter(active=True, household=household, kind='income', effective_date__range=(first, last))
    forecast = None
    monthly_scope = params.get('period', 'month') != 'custom' or (first.day == 1 and requested == month_end(requested))
    if monthly_scope and access.complete_finance(member):
        forecast_first, forecast_last = month_start(first), month_start(last)
        month_count = (forecast_last.year - forecast_first.year) * 12 + forecast_last.month - forecast_first.month + 1
        headers = list(MonthlyBudgetHeader.objects.filter(household=household, month__range=(forecast_first, forecast_last)))
        forecasts = [h.expected_income_ore for h in headers]
        if len(headers) == month_count and all(x is not None for x in forecasts):
            forecast = sum(forecasts)
        scope = month_key(forecast_first) if forecast_first == forecast_last else month_key(forecast_first) + '–' + month_key(forecast_last)
        forecast_scope = 'Forventet inntekt i hele månedsplaner ' + scope + ' (ikke mottatt inntekt).'
        if forecast is None:
            forecast_scope += ' Månedsplanene er ikke fullstendig utfylt.'
    elif not access.complete_finance(member):
        forecast_scope = 'Full månedsprognose krever tilgang til alle økonomimoduler.'
    else:
        forecast_scope = 'Månedsprognose vises ikke for et delvis egendefinert datospenn.'
    return {'period': {'start': first.isoformat(), 'end': last.isoformat(), 'requested_end': requested.isoformat(),
                       'to_today': requested > today, 'label': first.strftime('%d.%m.%Y') + '–' + last.strftime('%d.%m.%Y') + (' · til i dag' if requested > today else '')},
            'filters': {'categories': selected, 'q': q}, 'period_total_ore': sum(net_amount(r) for r in period_rows),
            'total_ore': sum(net_amount(r) for r in rows), 'category_options': [category_info(c) for c in categories] + [UNCATEGORIZED],
            'categories': sorted(groups.values(), key=lambda c: (-c['amount_ore'], c['name'].casefold())),
            'trend': trend, 'coverage': warn, 'restricted_selection': not access.complete_finance(member),
            'income': {'received_ore': sum(r.amount_ore for r in income_rows if r.received),
                       'expected_entries_ore': sum(r.amount_ore for r in income_rows if not r.received),
                       'forecast_ore': forecast, 'forecast_scope': forecast_scope,
                       'label': 'Registrert inntekt for valgt periode – separat fra forbruk og kategorifilter'},
            'entries': serialized, 'pagination': {'page': page.number, 'pages': paginator.num_pages, 'count': paginator.count, 'page_size': 20}}


def source_revision(household):
    """Broad household snapshot includes missing identities/new rows and all source revisions."""
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    models = [Category, Asset, Entry, MonthPlan, BillTemplate, BillOccurrence, FundTopUp, MonthlyBudgetHeader]
    sources = {model.__name__: list(model.objects.filter(household=household).order_by('pk').values()) for model in models}
    sources['imports'] = list(ImportRecord.objects.filter(household=household).order_by('pk').values('id', 'version', 'status', 'updated_at'))

    area = current_area()

    sources['area'] = {'id': str(area.pk), 'access_version': area.access_version, 'modules': area.modules}
    return digest(sources)


def source_snapshot(household, target, histories, revision=None):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    return digest({'target': target, 'history': histories, 'sources': revision or source_revision(household)})


def effective_plan(household, target, category=None, asset=None):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    rows = MonthPlan.objects.filter(household=household, category=category, asset=asset, month__lte=target)
    exact = rows.filter(month=target).first()
    if exact and not exact.derived:
        return exact.amount_ore, 'existing_plan', exact
    anchor = rows.filter(derived=False).order_by('-month').first()
    if anchor:
        return plan_amount(anchor, target), 'existing_plan', exact
    if exact:
        return exact.amount_ore, 'existing_plan', exact
    return None, 'missing', None


def commitments(household, target):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    end = month_end(target)
    actual = list(BillOccurrence.objects.filter(household=household, due_date__lte=end).select_related('template'))
    payments = {x.occurrence_id for x in Entry.objects.filter(active=True, household=household, occurrence__isnull=False, effective_date__lte=end)}
    result = []
    for row in actual:
        if row.cancelled or row.pk in payments:
            continue
        result.append({'id': str(row.pk), 'name': row.name, 'due_date': row.due_date.isoformat(),
                       'amount_ore': row.amount_ore, 'accounting_class': row.accounting_class,
                       'category_id': str(row.category_id) if row.category_id else None,
                       'asset_id': str(row.asset_id) if row.asset_id else None, 'overdue': row.due_date < target})
    existing = set(BillOccurrence.objects.filter(household=household).values_list('template_id', 'recurrence_slot'))
    # Any materialized occurrence in the month overrides its template, including a moved due day.
    for template in BillTemplate.objects.filter(household=household, first_due__lte=end):
        cursor = month_start(template.first_due)
        while cursor <= target:
            if (template.pk, cursor) not in existing:
                due = cursor.replace(day=min(template.first_due.day, calendar.monthrange(cursor.year, cursor.month)[1]))
                from .correction_services import series_state
                enabled, values = series_state(template, due)
                if not enabled:
                    if not template.monthly: break
                    cursor = next_month(cursor)
                    continue
                result.append({'id': f'virtual:{template.pk}:{due}', 'name': values['name'], 'due_date': due.isoformat(),
                               'amount_ore': values['amount_ore'], 'accounting_class': template.accounting_class,
                               'category_id': values['category_id'],
                               'asset_id': str(template.asset_id) if template.asset_id else None, 'overdue': due < target})
            if not template.monthly:
                break
            cursor = next_month(cursor)
    return sorted(result, key=lambda b: (b['due_date'], b['id']))


def fund_available_before(household, asset, target, bills):
    from .financial_areas import current_area
    if current_area().household_id != household.pk:
        raise PermissionDenied('Budsjettet tilhorer en annen familie.')
    before = target - timedelta(days=1)
    balance = fund_balance(asset, before)
    # Match prepare_month's known allocation anchors from their effective dates. Missing
    # past materializations are still known allocations, not a new current-month charge.
    plans = list(MonthPlan.objects.filter(household=household, asset=asset).order_by('month'))
    materialized = {row.month for row in plans}
    anchors = [row for row in plans if not row.derived]
    implicit_annual_anchor = not anchors and bool(asset.target_ore)
    cursor = min([row.month for row in anchors], default=month_start(asset.opening_date))
    current = month_start(timezone.localdate())
    while cursor < target:
        if asset.archived and cursor > current:
            break
        if cursor not in materialized:
            applicable = [row for row in anchors if row.month <= cursor]
            amount = plan_amount(applicable[-1], cursor) if applicable else None
            if amount is None and implicit_annual_anchor and cursor >= month_start(asset.opening_date):
                amount = asset.target_ore // 12 + (asset.target_ore % 12 if cursor.month == 12 else 0)
            balance += amount or 0
        cursor = next_month(cursor)
    reserved = sum(b['amount_ore'] for b in bills if b['asset_id'] == str(asset.pk) and b['accounting_class'] == 'fund' and b['overdue'])
    return balance - reserved


def plan_totals(data, category_amounts=None, asset_amounts=None, income=None):
    category_amounts = category_amounts if category_amounts is not None else {x['id']: x['other_ore'] for x in data['categories']}
    asset_amounts = asset_amounts if asset_amounts is not None else {x['id']: x['amount_ore'] for x in data['assets']}
    income = data['expected_income_ore'] if income is None else income
    variable = sum(category_amounts.values()) if all(x is not None for x in category_amounts.values()) else None
    totals = {'ordinary_fixed_ore': sum(b['amount_ore'] for b in data['commitments'] if b['accounting_class'] == 'ordinary'),
              'other_categories_ore': variable, 'savings_ore': 0, 'debt_ore': 0, 'funds_ore': 0, 'planned_remainder_ore': None}
    for asset in data['assets']:
        value = asset_amounts[asset['id']]
        key = {'savings': 'savings_ore', 'debt': 'debt_ore', 'fund': 'funds_ore'}[asset['kind']]
        if value is None:
            totals[key] = None
        elif totals[key] is not None:
            if asset['kind'] == 'debt':
                totals[key] += max(value, asset['obligation_ore'])
            elif asset['kind'] == 'fund':
                totals[key] += value + max(asset['obligation_ore'] - asset['available_balance_ore'] - value, 0)
            else:
                totals[key] += value
    costs = [totals[k] for k in ('ordinary_fixed_ore', 'other_categories_ore', 'savings_ore', 'debt_ore', 'funds_ore')]
    if income is not None and all(x is not None for x in costs):
        totals['planned_remainder_ore'] = income - sum(costs)
    return totals


@transaction.atomic
def planning(actor, target_month=None, history=None, today=None):
    member = access.require(access.lock_member(actor), access.FINANCE)
    household = member.household
    Household.objects.select_for_update().get(pk=household.pk)
    today = today or timezone.localdate()
    current = month_start(today)
    target = month_value(target_month) if target_month else next_month(current)
    if target <= current:
        raise ValidationError('Bare fremtidige månedsplaner kan redigeres her.')
    histories = history_values(history or [], current)
    history_dates = list(Entry.objects.filter(active=True, household=household, effective_date__lt=current).values_list('effective_date', flat=True))
    history_counts = {}
    for day in history_dates:
        history_counts[month_start(day)] = history_counts.get(month_start(day), 0) + 1
    warn = coverage(household)
    options = [{'month': month_key(m), 'has_entries': True, 'entry_count': n,
                'status': 'partial'} for m, n in sorted(history_counts.items(), reverse=True)]
    # No source model attests that a month is complete. Calendar completion alone cannot do that.
    weak = True
    warn['requires_acknowledgement'] = weak
    if weak:
        warn['warning'] = ' '.join(filter(None, [warn['warning'], 'Historikken er sparsom eller ikke fullstendig bekreftet. Kontroller beløpene og bekreft grunnlaget manuelt.']))
    bills = commitments(household, target)
    plans = list(MonthPlan.objects.filter(household=household, month=target))
    cat_ids = {b['category_id'] for b in bills if b['accounting_class'] == 'ordinary'} | {str(p.category_id) for p in plans if p.category_id}
    cats = list(Category.objects.filter(household=household).filter(Q(archived=False) | Q(pk__in=[x for x in cat_ids if x])).order_by('name', 'id'))
    historic = list(ordinary_rows(household, min(histories), month_end(max(histories)))) if histories else []
    historic = [row for row in historic if month_start(row.effective_date) in histories]
    category_lines = []
    for cat in cats:
        fixed = sum(b['amount_ore'] for b in bills if b['accounting_class'] == 'ordinary' and b['category_id'] == str(cat.pk))
        amount, source, _ = effective_plan(household, target, category=cat)
        observed = [row for row in historic if row_category(row) and row_category(row).pk == cat.pk]
        variable_rows = [row for row in observed if not (row.original.occurrence_id if row.kind == 'refund' else row.occurrence_id)]
        average = None
        observed_months = {month_start(row.effective_date) for row in observed}
        if histories and observed and all(m in observed_months for m in histories):
            average = int((Decimal(sum(net_amount(r) for r in variable_rows)) / len(histories)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        other = max(amount - fixed, 0) if amount is not None else None
        historical_other = average if average is not None and average >= 0 else None
        if histories:
            # Explicit history selection requests a suggestion, even when a target plan exists.
            other, source = historical_other, 'history' if historical_other is not None else 'missing'
        category_lines.append({**category_info(cat), 'fixed_ore': fixed, 'other_ore': other,
                               'total_ore': fixed + other if other is not None else None, 'source': source,
                               'historical_average_ore': average, 'historical_other_ore': historical_other,
                               'observations': len(observed), 'observed_months': len(observed_months)})
    asset_ids = {b['asset_id'] for b in bills if b['asset_id']} | {str(p.asset_id) for p in plans if p.asset_id}
    assets = []
    for candidate in Asset.objects.filter(household=household, kind__in=['savings', 'debt', 'fund']).order_by('kind', 'name', 'id'):
        historical_amount, _, _ = effective_plan(household, target, asset=candidate)
        retained_obligation = candidate.kind in ('debt', 'fund') and (
            historical_amount is not None or candidate.minimum_ore > 0 or candidate.kind == 'fund' and candidate.target_ore > 0)
        if not candidate.archived or str(candidate.pk) in asset_ids or retained_obligation:
            assets.append(candidate)
    asset_lines = []
    for asset in assets:
        amount, source, _ = effective_plan(household, target, asset=asset)
        obligation = sum(b['amount_ore'] for b in bills if b['asset_id'] == str(asset.pk) and b['accounting_class'] == asset.kind and (asset.kind != 'fund' or not b['overdue']))
        if asset.kind == 'debt':
            obligation = max(obligation, asset.minimum_ore)
        if amount is None and asset.kind == 'debt' and (obligation or asset.minimum_ore):
            amount, source = max(obligation, asset.minimum_ore), 'confirmed_commitment'
        elif amount is None and asset.kind == 'fund' and asset.target_ore:
            amount, source = asset.target_ore // 12 + (asset.target_ore % 12 if target.month == 12 else 0), 'confirmed_commitment'
        available = fund_available_before(household, asset, target, bills) if asset.kind == 'fund' else None
        topup = max(obligation - available - amount, 0) if asset.kind == 'fund' and amount is not None else 0
        asset_lines.append({'id': str(asset.pk), 'name': asset.name, 'kind': asset.kind,
                            'amount_ore': amount, 'source': source, 'obligation_ore': obligation,
                            'topup_ore': topup, 'available_balance_ore': available})
    header = MonthlyBudgetHeader.objects.filter(household=household, month=target).first()
    revision = source_revision(household)
    snapshot = source_snapshot(household, target, histories, revision)

    result = {'target_month': month_key(target), 'can_save': can_write(member, current_area(member)), 'snapshot': snapshot,
              'source_revision': revision,
              'history_months': [month_key(x) for x in histories], 'history_options': options, 'coverage': warn,
              'expected_income_ore': header.expected_income_ore if header else None,
              'income_source': 'existing_plan' if header and header.expected_income_ore is not None else 'missing',
              'categories': category_lines, 'assets': asset_lines, 'commitments': bills,
              'uncategorized_fixed_ore': sum(b['amount_ore'] for b in bills if b['accounting_class'] == 'ordinary' and not b['category_id']),
              'no_savings_goals': not any(a.kind == 'savings' for a in assets)}
    result['totals'] = plan_totals(result)
    result['draft'] = {'target_month': result['target_month'], 'history_months': result['history_months'], 'snapshot': snapshot,
                       'expected_income_ore': result['expected_income_ore'],
                       'categories': [{'id': x['id'], 'other_ore': x['other_ore']} for x in category_lines],
                       'assets': [{'id': x['id'], 'amount_ore': x['amount_ore']} for x in asset_lines],
                       'acknowledge_incomplete': False}
    return result


def validated_preview(actor, draft):
    exact_fields(draft, ['target_month', 'history_months', 'snapshot', 'expected_income_ore', 'categories', 'assets', 'acknowledge_incomplete'])
    if type(draft['acknowledge_incomplete']) is not bool:
        raise ValidationError('Bekreftelsen må være et eksplisitt valg.')
    if not isinstance(draft['snapshot'], str) or len(draft['snapshot']) != 64:
        raise ValidationError('Last inn et gyldig plangrunnlag.')
    if not isinstance(draft['history_months'], list):
        raise ValidationError('Kildemåneder må være en liste.')
    data = planning(actor, draft['target_month'], draft['history_months'])
    if draft['snapshot'] != data['snapshot']:
        raise Conflict('Grunnlaget eller planen er endret. Last inn på nytt og sammenlign før du lagrer.')
    if data['coverage']['requires_acknowledgement'] and not draft['acknowledge_incomplete']:
        raise ValidationError('Kontroller og bekreft det ufullstendige grunnlaget før forhåndsvisning.')
    income = ore_value(draft['expected_income_ore'])
    maps = {}
    for field, value_field in [('categories', 'other_ore'), ('assets', 'amount_ore')]:
        values = draft[field]
        if not isinstance(values, list) or len(values) != len(data[field]):
            raise ValidationError('Alle planlinjer må være med nøyaktig én gang.')
        mapping = {}
        for item in values:
            exact_fields(item, ['id', value_field])
            identity = uuid_value(item['id'])
            if identity in mapping:
                raise ValidationError('En planlinje kan ikke gjentas.')
            mapping[identity] = ore_value(item[value_field])
        if set(mapping) != {x['id'] for x in data[field]}:
            raise ValidationError('Planlinjene må tilhøre familien og gjeldende plangrunnlag.')
        maps[field] = mapping
    totals = plan_totals(data, maps['categories'], maps['assets'], income)
    changes = [{'kind': 'income', 'id': 'income', 'name': 'Forventet inntekt',
                'before_ore': data['expected_income_ore'], 'after_ore': income}]
    for cat in data['categories']:
        old = MonthPlan.objects.filter(household=membership(actor).household, month=month_value(data['target_month']), category_id=cat['id']).first()
        changes.append({'kind': 'category', 'id': cat['id'], 'name': cat['name'],
                        'before_ore': old.amount_ore if old else None,
                        'after_ore': cat['fixed_ore'] + maps['categories'][cat['id']]})
    for asset in data['assets']:
        old = MonthPlan.objects.filter(household=membership(actor).household, month=month_value(data['target_month']), asset_id=asset['id']).first()
        changes.append({'kind': asset['kind'], 'id': asset['id'], 'name': asset['name'],
                        'before_ore': old.amount_ore if old else None, 'after_ore': maps['assets'][asset['id']]})
    normalized = {'target_month': data['target_month'], 'history_months': data['history_months'], 'snapshot': data['snapshot'],
                  'expected_income_ore': income, 'categories': [{'id': k, 'other_ore': v} for k, v in sorted(maps['categories'].items())],
                  'assets': [{'id': k, 'amount_ore': v} for k, v in sorted(maps['assets'].items())],
                  'acknowledge_incomplete': draft['acknowledge_incomplete']}
    result = {'target_month': data['target_month'], 'snapshot': data['snapshot'], 'totals': totals,
              'changes': changes, 'draft': normalized}
    result['confirmation_digest'] = digest(result)
    return result


def preview(actor, draft):
    # The same household lock as writers makes the source snapshot and diff one consistent view.
    member = membership(actor)
    with transaction.atomic():
        Household.objects.select_for_update().get(pk=member.household_id)
        return validated_preview(actor, draft)


@transaction.atomic
def save_plan(actor, payload):
    exact_fields(payload, ['draft', 'confirmation_digest', 'confirm', 'key'])
    member = access.require(access.lock_member(actor), access.FINANCE)
    Household.objects.select_for_update().get(pk=member.household_id)
    locked_household_id = member.household_id
    member.refresh_from_db()
    if member.role != 'admin' or member.household_id != locked_household_id:
        raise PermissionDenied('Bare en administrator kan bekrefte familiens månedsplan.')
    if payload['confirm'] is not True:
        raise ValidationError('Bekreft månedsplanen eksplisitt før lagring.')
    key = uuid_value(payload['key'])
    request_digest = digest({'actor': actor.pk, 'payload': payload})
    previous = PlanningRequest.objects.filter(household=member.household, key=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.digest != request_digest:
            raise Conflict('Forespørselsnøkkelen er allerede brukt med et annet innhold.')
        return previous.result
    candidate = validated_preview(actor, payload['draft'])
    if not isinstance(payload['confirmation_digest'], str) or payload['confirmation_digest'] != candidate['confirmation_digest']:
        raise Conflict('Endringsoversikten stemmer ikke lenger. Forhåndsvis planen på nytt.')
    target = month_value(candidate['target_month'])
    header, created = MonthlyBudgetHeader.objects.get_or_create(household=member.household, month=target,
                    defaults={'created_by': actor, 'expected_income_ore': candidate['draft']['expected_income_ore']})
    if not created:
        header.expected_income_ore = candidate['draft']['expected_income_ore']
        header.version += 1
        header.full_clean()
        header.save()
    for change in candidate['changes']:
        if change['kind'] == 'income':
            continue
        category_id = change['id'] if change['kind'] == 'category' else None
        asset_id = change['id'] if change['kind'] != 'category' else None
        row = MonthPlan.objects.filter(household=member.household, month=target, category_id=category_id, asset_id=asset_id).first()
        if row:
            row.amount_ore = change['after_ore']
            row.annual_total_ore = None
            row.derived = False
            row.version += 1
        else:
            row = MonthPlan(household=member.household, created_by=actor, month=target,
                            category_id=category_id, asset_id=asset_id, amount_ore=change['after_ore'])
        row.full_clean()
        row.save()
    result = {'saved': True, 'target_month': candidate['target_month'], 'revision': header.version}
    Audit.objects.create(household=member.household, actor=actor, object_id=header.pk, operation='månedsplan bekreftet',
                         changes={'target_month': candidate['target_month'], 'changes': candidate['changes'],
                                  'totals': candidate['totals'], 'source_snapshot': candidate['snapshot'],
                                  'history_months': candidate['draft']['history_months'],
                                  'incomplete_basis_acknowledged': candidate['draft']['acknowledge_incomplete'],
                                  'monthly_override': True})
    PlanningRequest.objects.create(household=member.household, actor=actor, key=key, digest=request_digest, result=result)
    return result
