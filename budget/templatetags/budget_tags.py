from decimal import Decimal
from django import template
from django.utils.safestring import mark_safe
register = template.Library()
@register.filter
def nok(value):
    if value is None: return '—'
    return f'{Decimal(value) / 100:,.2f}'.replace(',', '\u00a0').replace('.', ',') + ' kr'
@register.filter
def can_edit(row, member):
    return member.role == 'admin' or row.created_by_id == member.user_id
@register.filter
def initials(value):
    words = str(value).split()
    return ''.join(word[0] for word in words[:2]).upper() if len(words) > 1 else str(value)[:2].upper()
@register.simple_tag
def nav_icon(key):
    paths = {'kalender': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>', 'oversikt': '<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>', 'poster': '<path d="M5 3h14v18H5Z"/><path d="M8 8h8M8 12h8M8 16h5"/>', 'budsjett': '<path d="M4 20V10h4v10m2 0V4h4v16m2 0v-7h4v7"/>', 'sparing': '<path d="M5 9h12l3 4-2 4v3h-3v-2H8v2H5v-4L3 14v-3l2-2Zm7 0V5h4"/><path d="M8 5h5M16 12h.01"/>', 'mer': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>', 'regninger': '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><path d="M9 7h6M9 11h6"/>', 'familie': '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>'}
    return mark_safe('<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">' + paths.get(key, paths['mer']) + '</svg>')
