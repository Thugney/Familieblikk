"""Compact, read-only presentation of the planner's existing commitments."""
from datetime import date
from urllib.parse import urlencode
from django.urls import reverse

from .entry_presentation import BILL_LABELS


def bill_preview(commitments, area_id, month, limit=5):
    ordered = sorted(commitments, key=lambda row: (row['due_date'], row['name'].casefold(), row['id']))
    rows = []
    query = urlencode({'area': str(area_id), 'month': month.strftime('%Y-%m')})
    for bill in ordered[:limit]:
        virtual = bill['id'].startswith('virtual:')
        identity = bill['id'].split(':')[1] if virtual else bill['id']
        url = reverse('correction_history', args=['series' if virtual else 'bill', identity])
        rows.append({**bill, 'day': date.fromisoformat(bill['due_date']),
            'type_label': BILL_LABELS[bill['accounting_class']], 'url': url + '?' + query})
    return {'rows': rows, 'count': len(ordered), 'remaining': len(ordered) - len(rows)}
