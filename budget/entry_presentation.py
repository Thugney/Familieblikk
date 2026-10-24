"""Readable labels and explicit links; no changes to stored financial values."""
from urllib.parse import urlencode

from django.urls import reverse


ENTRY_LABELS = {
    'income': 'Penger inn', 'expense': 'Utgift', 'refund': 'Penger tilbake',
    'deposit': 'Satt inn på sparing', 'withdrawal': 'Tatt ut fra sparing',
    'debt': 'Betalt på gjeld', 'fund': 'Betalt årsutgift', 'remittance': 'Sendt utenlands',
}
ASSET_LABELS = {'savings': 'Sparemål', 'debt': 'Gjeld', 'fund': 'Penger til årsutgifter', 'recipient': 'Mottaker'}
BILL_LABELS = {'ordinary': 'Vanlig regning', 'debt': 'Betaling på gjeld', 'fund': 'Årsutgift'}


def document_label(document):
    if document.transient:
        return 'Skanning: ' + (document.supplier or 'Gjennomgåtte detaljer')
    return 'Dokument: ' + document.filename


def row_date(row):
    return getattr(row, 'effective_date', None) or getattr(row, 'due_date', None) or getattr(row, 'first_due', None)


def related_url(row, route, args, *, day=None, anchor=''):
    """Keep the exact record's area and economic month, including JSON links."""
    day = day or row_date(row)
    query = {'area': str(row.financial_area_id)}
    if day:
        query['month'] = day.strftime('%Y-%m')
    return reverse(route, args=args) + '?' + urlencode(query) + ('#' + anchor if anchor else '')


def history_url(row, kind='entry'):
    return related_url(row, 'correction_history', [kind, row.pk])
