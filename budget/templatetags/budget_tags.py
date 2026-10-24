from decimal import Decimal
from django import template
from django.utils.safestring import mark_safe
register = template.Library()

@register.simple_tag
def app_static(name):
    """Keep the app's browser/CDN asset version aligned with the rendered page."""
    from hashlib import sha256
    from pathlib import Path
    from django.templatetags.static import static
    if name not in ('ui-refresh.css', 'spending.css', 'spending.js'):
        raise ValueError('Unknown application asset')
    path = Path(__file__).resolve().parents[1] / 'static' / 'budget' / name
    return static('budget/' + name) + '?v=' + sha256(path.read_bytes()).hexdigest()[:16]

@register.simple_tag
def loader_static(name):
    """A new loader release must not reuse an older browser/CDN asset URL."""
    from hashlib import sha256
    from pathlib import Path
    from django.templatetags.static import static
    if name not in ('loader.css', 'loader.js'):
        raise ValueError('Unknown loader asset')
    path = Path(__file__).resolve().parents[1] / 'static' / 'budget' / name
    version = sha256(path.read_bytes()).hexdigest()[:16]
    return static('budget/' + name) + '?v=' + version

@register.inclusion_tag('budget/workflow_links.html')
def workflow_links(member, row):
    from budget import access
    from django.core.exceptions import PermissionDenied
    from django.db.models import Q
    from budget.models import Document, Entry, BillOccurrence, BillTemplate, ShoppingTrip
    from budget.entry_presentation import related_url, history_url, row_date, document_label
    links = []
    access.require_row(member, row)

    def add(target, label, url, status=''):
        try:
            access.require_row(member, target)
        except PermissionDenied:
            return
        links.append({'label': label, 'url': url, 'status': status})

    document_filter = Q(pk__in=[])
    if isinstance(row, Entry):
        document_filter = Q(entry=row)
        if row.occurrence_id:
            bill = row.occurrence
            add(bill, 'Regning: ' + bill.name, history_url(bill, 'bill'))
            document_filter |= Q(bill=bill)
        if row.original_id:
            original = row.original
            add(original, 'Opprinnelig betaling: ' + original.description, history_url(original),
                'Registrert' if original.active else 'Angret – teller ikke i budsjettet')
        for refund in access.safe_rows(member, row.refunds.all()).order_by('effective_date', 'sequence'):
            add(refund, 'Penger tilbake: ' + refund.description, history_url(refund),
                'Registrert' if refund.active else 'Angret – teller ikke i budsjettet')
        if access.allows(member, 'shopping'):
            for trip in access.safe_rows(member, ShoppingTrip.objects.filter(entry=row)):
                add(trip, 'Handletur: ' + trip.store,
                    related_url(row, 'shopping_detail', [trip.shopping_list_id], anchor='trip-' + str(trip.pk)))
                if trip.receipt_id:
                    document_filter |= Q(pk=trip.receipt_id)
    elif isinstance(row, (BillOccurrence, BillTemplate)):
        if isinstance(row, BillOccurrence):
            document_filter = Q(bill=row)
            add(row.template, 'Regningsoppsett: ' + row.name,
                related_url(row.template, 'correction_history', ['series', row.template_id], day=row.due_date))
            for payment in access.safe_rows(member, row.payments.all()).order_by('effective_date', 'sequence'):
                add(payment, 'Betalingspost: ' + payment.description, history_url(payment),
                    'Registrert' if payment.active else 'Angret – teller ikke i budsjettet')
    if getattr(row, 'asset_id', None):
        asset = row.asset
        page = {'savings': 'sparing', 'debt': 'gjeld', 'fund': 'arsutgifter', 'recipient': 'utland'}.get(asset.kind)
        label = {'savings': 'Sparemål', 'debt': 'Gjeld', 'fund': 'Årsutgift', 'recipient': 'Mottaker'}.get(asset.kind)
        if page:
            anchor = ('debt-' if asset.kind == 'debt' else 'asset-') + str(asset.pk)
            add(asset, label + ': ' + asset.name, related_url(asset, 'page', [page], day=row_date(row), anchor=anchor))
    for document in access.safe_rows(member, Document.objects.filter(document_filter)).distinct():
        add(document, document_label(document), related_url(document, 'document_detail', [document.pk], day=row_date(row)))
    return {'links': links}

@register.simple_tag
def detail_url(row, kind='entry'):
    from budget.entry_presentation import history_url
    return history_url(row, kind)

@register.filter
def entry_label(value):
    from budget.entry_presentation import ENTRY_LABELS
    return ENTRY_LABELS.get(value, value)

@register.filter
def asset_label(value):
    from budget.entry_presentation import ASSET_LABELS
    return ASSET_LABELS.get(value, value)

@register.filter
def bill_label(value):
    from budget.entry_presentation import BILL_LABELS
    return BILL_LABELS.get(value, value)

@register.filter
def allows_module(member, module):
    from budget.access import allows
    return allows(member, module)
@register.filter
def visible_navigation(nav, member):
    from budget.access import can_page
    return [(key, label) for key, label in nav if can_page(member, key)]
@register.filter
def allows_page(member, page):
    from budget.access import can_page
    return can_page(member, page)
@register.filter
def can_matrix(member):
    from budget.access import complete_finance, can_page
    return can_page(member, 'arsoversikt') and complete_finance(member)
@register.simple_tag
def unread_notifications(member):
    if not getattr(member, 'user_id', None) or not getattr(member, 'household_id', None):
        return 0
    from budget.notification_services import visible_notifications
    return len(visible_notifications(member, unread=True))
@register.simple_tag
def overdue_bills(member, month):
    from budget.financial_areas import scope_state
    if scope_state() is None: return 0
    from django.utils import timezone
    from budget import services
    from datetime import date
    try: period = date.fromisoformat(str(month) + '-01')
    except ValueError: period = timezone.localdate().replace(day=1)
    from budget.access import safe_rows
    return safe_rows(member, services.pending_bills(member.household, services.month_end(period))).filter(due_date__lt=timezone.localdate()).count()
@register.simple_tag(takes_context=True)
def can_access_private_import(context):
    from budget import importing
    from django.core.exceptions import PermissionDenied, ValidationError
    request = context.get('request')
    if not request or not request.user.is_authenticated: return False
    cached = getattr(request, '_private_import_access', None)
    if cached is not None: return cached
    try:
        _, binding = importing.load_private_source()
        importing.owner_membership(request.user, request.session.get('verified_email'), binding, auth_context=request.session)
        allowed = True
    except (OSError, ValueError, KeyError, PermissionDenied, ValidationError): allowed = False
    request._private_import_access = allowed
    return allowed
@register.simple_tag(takes_context=True)
def month_navigation_context(context):
    from budget.models import Asset, Entry
    from budget.views import debt_context
    import uuid
    request, member = context.get('request'), context.get('member')
    if not request or not member: return {}
    query, result = request.GET, {}
    allowed = {'entry_kind': dict(Entry.KINDS), 'asset_kind': dict(Asset.TYPES), 'accounting_class': ('ordinary', 'debt', 'fund'), 'once': ('1',), 'view': ('matrix',), 'return_to': ('oversikt', 'poster', 'sparing', 'gjeld', 'arsutgifter', 'utland', 'regninger', 'budsjett', 'kategorier')}
    for key, choices in allowed.items():
        if query.get(key) in choices: result[key] = query[key]
    if query.get('asset'):
        try:
            asset_id = uuid.UUID(query['asset'])
            if Asset.objects.filter(pk=asset_id, household=member.household).exists(): result['asset'] = str(asset_id)
        except ValueError: pass
    result.update(debt_context(query))
    return result
@register.simple_tag(takes_context=True)
def debt_navigation_query(context):
    from budget.views import debt_context
    from urllib.parse import urlencode
    return urlencode(debt_context(context['request'].GET)) if context.get('page') == 'gjeld' else ''
@register.simple_tag(takes_context=True)
def module_navigation(context, member):
    modules = member.household.modules
    links = [('regninger', 'Regninger & historikk', None), ('gjeld', 'Gjeld & strategi', 'debt'), ('arsutgifter', 'Årsutgifter', 'fund'), ('utland', 'Sendt utenlands', 'remittance'), ('arsoversikt', 'Årsoversikt', 'annual_navigation'), ('familie', 'Familie & tilgang', None), ('tilpass', 'Tilpass appen', None), ('varsler', 'Varsler', None), ('import', 'Mer / Kildeimport', None)]
    links = [link for link in links if link[0] != 'import' or can_access_private_import(context)]
    from budget.access import visible_page, complete_finance
    return [(key, 'Årsoversikt' if key == 'arsoversikt' and not complete_finance(member) else label)
            for key, label, module in links if visible_page(member, key)]
@register.filter
def nok(value):
    if value is None: return '—'
    return f'{Decimal(value) / 100:,.2f}'.replace(',', '\u00a0').replace('.', ',') + ' kr'
@register.filter
def can_edit(row, member):
    from budget.access import require_write_row
    from django.core.exceptions import PermissionDenied
    try: require_write_row(member, row)
    except PermissionDenied: return False
    return True
@register.filter
def initials(value):
    words = str(value).split()
    return ''.join(word[0] for word in words[:2]).upper() if len(words) > 1 else str(value)[:2].upper()
@register.simple_tag
def nav_icon(key):
    paths = {'kalender': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>', 'oversikt': '<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>', 'poster': '<path d="M5 3h14v18H5Z"/><path d="M8 8h8M8 12h8M8 16h5"/>', 'budsjett': '<path d="M4 20V10h4v10m2 0V4h4v16m2 0v-7h4v7"/>', 'sparing': '<path d="M5 9h12l3 4-2 4v3h-3v-2H8v2H5v-4L3 14v-3l2-2Zm7 0V5h4"/><path d="M8 5h5M16 12h.01"/>', 'mer': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>', 'regninger': '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><path d="M9 7h6M9 11h6"/>', 'familie': '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>'}
    paths.update({'dokumenter': '<path d="M4 7h3l2-2h6l2 2h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z"/><circle cx="12" cy="13" r="3.5"/>', 'handlelister': '<path d="M9 5h11M9 12h11M9 19h11M4 5l1.5 1.5L8 4M4 12l1.5 1.5L8 11M4 19l1.5 1.5L8 18"/>', 'gjeld': '<path d="M4 4h16v16H4Z"/><path d="M8 8h8m-8 4h8m-8 4h4"/>', 'arsutgifter': '<path d="M3 10h18M5 10v10m7-10v10m7-10v10M3 21h18M3 7l9-4 9 4Z"/>', 'utland': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18"/>', 'arsoversikt': '<path d="M3 3v18h18M7 16l4-6 4 3 6-8"/>', 'tilpass': '<path d="M3 6h18M3 12h18M3 18h18M7 3v6m10 0v6M9 15v6"/>', 'varsler': '<path d="M6 9a6 6 0 0 1 12 0c0 6 3 6 3 8H3c0-2 3-2 3-8M10 21h4"/>', 'import': '<path d="M4 3h10l6 6v12H4Z"/><path d="M14 3v6h6m-8 2v7m-3-3 3 3 3-3"/>'})
    return mark_safe('<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">' + paths.get(key, paths['mer']) + '</svg>')
@register.simple_tag(takes_context=True)
def accessible_financial_areas(context):
    request, member = context.get('request'), context.get('member')
    if not request or not member:
        return []
    cached = getattr(request, '_accessible_financial_areas', None)
    if cached is not None:
        return cached
    if not getattr(member, 'pk', None) or not getattr(request, 'financial_area', None):
        return []
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        from budget.financial_models import FinancialAreaGrant
        from budget.area_requests import financial_url
        current = request.financial_area
        raw_path = request.get_full_path() if hasattr(request, 'get_full_path') else '/app/oversikt/'
        parts = urlsplit(raw_path)
        clean_path = urlunsplit(('', '', parts.path, urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'area']), parts.fragment))
        palette = ('#34D399', '#60A5FA', '#F472B6', '#FBBF24', '#A78BFA')
        grants = FinancialAreaGrant.objects.filter(
            member_id=member.pk, member__user__is_active=True,
            area__household_id=member.household_id, area__status='active'
        ).select_related('area').order_by('area__name', 'area__id')
        result = []
        for idx, grant in enumerate(grants):
            area = grant.area
            writable = grant.role in ('owner', 'editor')
            result.append({
                'pk': area.pk,
                'name': area.name,
                'kind': area.kind,
                'kind_label': area.get_kind_display(),
                'can_write': writable,
                'is_current': str(area.pk) == str(getattr(current, 'pk', '')),
                'open_url': financial_url(clean_path, area.pk),
                'dot_color': palette[idx % len(palette)],
            })
        request._accessible_financial_areas = result
        return result
    except Exception:
        return []
