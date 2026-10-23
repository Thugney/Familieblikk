"""Explain recorded money movements and remaining plans without posting anything."""
from collections import defaultdict
from urllib.parse import urlencode

from django.utils import timezone

from . import access, services
from .area_requests import financial_url
from .financial_areas import current_area
from .models import Asset, Category, Entry
from .financial_projection import month_basis
from .spending_services import coverage


def overview(member, month, totals, today=None):
    access.require(member, access.FINANCE)
    area = current_area(member)
    today = today or timezone.localdate()
    start, end = services.month_start(month), services.month_end(month)
    if start > today:
        return None
    cutoff = min(today, end)
    house = member.household
    entries = list(Entry.objects.filter(household=house, active=True,
        effective_date__range=(start, cutoff)).select_related('original'))
    movements = defaultdict(int)
    groups = defaultdict(lambda: {'spent': 0, 'gross': 0, 'refunds': 0, 'pending': 0})
    for entry in entries:
        if entry.kind == 'income' and not entry.received:
            continue
        movements[entry.kind] += entry.amount_ore
        ordinary = entry.kind in ('expense', 'remittance')
        ordinary_refund = entry.kind == 'refund' and entry.original.kind in ('expense', 'remittance')
        if ordinary or ordinary_refund:
            key = entry.original.category_id if ordinary_refund else entry.category_id
            row = groups[key]
            row['spent'] += -entry.amount_ore if ordinary_refund else entry.amount_ore
            row['refunds' if ordinary_refund else 'gross'] += entry.amount_ore
    basis = month_basis(house, start, today=today)
    for bill in basis['pending']:
        if bill['accounting_class'] == 'ordinary':
            groups[bill['category_id']]['pending'] += bill['amount_ore']
    limits = basis['category_limits']
    planned_savings = sum(basis['asset_plans'].get(key, 0)
        for key in Asset.objects.filter(household=house, kind='savings').values_list('pk', flat=True))
    categories = {row.pk: row for row in Category.objects.filter(household=house)}

    def url(path, **params):
        return financial_url(path + '?' + urlencode({'month': start.strftime('%Y-%m'), **params}), area.pk)

    rows = []
    for key in groups.keys() | limits.keys():
        values = groups[key]
        category = categories.get(key)
        limit = limits.get(key)
        used = values['spent'] + values['pending']
        rows.append({**values, 'name': category.name if category else 'Uten kategori',
            'uncategorized': category is None, 'archived': bool(category and category.archived),
            'limit': limit, 'remaining': max(limit - used, 0) if limit is not None else None,
            'over': max(used - limit, 0) if limit is not None else 0,
            'entries_url': url('/app/poster/', **({'category': str(key)} if key else {}))})
    rows.sort(key=lambda row: (-row['over'], row['limit'] is not None, -row['gross'], row['name']))
    remaining = sum(row['remaining'] or 0 for row in rows)
    remainder = totals['available'] - remaining
    missing = [row for row in rows if row['limit'] is None and (row['gross'] or row['pending'])]
    exceeded = [row for row in rows if row['over']]
    basis = coverage(house)
    notices = []
    if totals['available'] < 0:
        notices.append({'title': 'Registrert underskudd', 'amount': -totals['available'],
            'text': 'Mottatt inntekt dekker ikke registrert forbruk og avsetninger. Se gjennom regninger og prioriter nødvendige utgifter.',
            'url': url('/app/regninger/'), 'link': 'Se regningene'})
    elif remainder < 0:
        notices.append({'title': 'Månedsrammene mangler dekning', 'amount': -remainder,
            'text': 'Resterende kategorirammer er større enn beløpet igjen å bruke. Forventet inntekt teller først når den er mottatt.',
            'url': url('/app/kategorier/'), 'link': 'Se rammene'})
    if exceeded:
        notices.append({'title': 'Over kategorirammene', 'amount': sum(row['over'] for row in exceeded),
            'text': 'Registrert forbruk og ubetalte regninger overstiger rammen i ' + str(len(exceeded)) + ' kategori(er). Se detaljene nedenfor før nye kjøp.',
            'url': url('/app/kategorier/'), 'link': 'Gå gjennom kategoriene'})
    if missing:
        notices.append({'title': 'Pengebruk uten månedsramme', 'amount': None,
            'text': str(len(missing)) + ' kategori(er) har utgifter eller regninger, men mangler ramme. Dette er et hull i planen, ikke bevis på feil pengebruk.',
            'url': url('/app/kategorier/'), 'link': 'Sett eller gjennomgå rammer'})
    if any(row['uncategorized'] and (row['gross'] or row['pending']) for row in rows):
        notices.append({'title': 'Utgifter uten kategori', 'amount': None,
            'text': 'Kategoriser postene for å kunne følge forbruket mot en konkret ramme.',
            'url': url('/app/poster/'), 'link': 'Kontroller postene'})
    if start == services.month_start(today) and remainder > 0 and not missing and not exceeded and not basis['unresolved_import_count'] and groups and totals['income'] > 0:
        notices.append({'title': 'Vurder buffer før ekstra forbruk', 'amount': None,
            'text': 'Det er et positivt restbeløp i de registrerte planene. Kontroller kontoutskriften, kommende regninger og årsutgifter før du vurderer ekstra sparing.',
            'url': url('/app/sparing/'), 'link': 'Se sparemål'})
    ordinary_gross = movements['expense'] + movements['remittance']
    ordinary_refunds = sum(row['refunds'] for row in rows)
    cash_in = movements['income'] + movements['withdrawal'] + movements['refund']
    cash_out = ordinary_gross + movements['deposit'] + movements['debt'] + movements['fund']
    return {'through': cutoff, 'current': start == services.month_start(today), 'rows': rows,
        'ordinary_gross': ordinary_gross, 'ordinary_refunds': ordinary_refunds,
        'ordinary_net': ordinary_gross - ordinary_refunds, 'movements': dict(movements),
        'cash_in': cash_in, 'cash_out': cash_out, 'cash_net': cash_in - cash_out,
        'remaining_categories': remaining, 'plan_remainder': remainder,
        'notices': notices if start == services.month_start(today) else [],
        'coverage': basis, 'entries_url': url('/app/poster/'),
        'categories_url': url('/app/kategorier/'), 'category_limits': limits,
        'planned_savings': planned_savings}
