"""Read-only presentation summaries of already calculated budget totals."""
from django import template

register = template.Library()


@register.filter
def savings_assets(assets):
    """Select the existing savings summaries without querying or changing them."""
    return [item for item in assets if item['row'].kind == 'savings']


@register.simple_tag
def budget_distribution(totals):
    """Never turn missing or negative money into a misleading positive chart."""
    keys = ('ordinary', 'bills', 'savings', 'debt', 'funds', 'available')
    values = {key: totals.get(key) for key in keys}
    complete = all(isinstance(value, int) and not isinstance(value, bool) for value in values.values())
    commitments = sum(values[key] for key in ('bills', 'savings', 'debt', 'funds')) if complete else None
    amounts = [values['ordinary'], commitments, values['available']]
    chartable = complete and all(value >= 0 for value in amounts) and sum(amounts) > 0
    total = sum(amounts) if chartable else 0
    return {
        'chartable': chartable,
        'parts': [
            {'label': label, 'amount': amount, 'kind': kind, 'weight': amount if chartable else 0}
            for label, amount, kind in zip(('Forbruk', 'Forpliktelser', 'Igjen'), amounts, ('spent', 'committed', 'available'))
        ],
        'total': total,
    }
