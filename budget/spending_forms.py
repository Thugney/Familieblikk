"""Strict JSON primitives shared by the spending and planning endpoints."""
import re
import uuid
from datetime import date
from django.core.exceptions import ValidationError

MAX_ORE = 9_000_000_000_000


def month_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValidationError('Velg en gyldig måned.')
    try:
        parsed = date.fromisoformat(value + '-01')
        if not 1901 <= parsed.year <= 2198:
            raise ValueError
        return parsed
    except ValueError:
        raise ValidationError('Velg en gyldig måned.')


def uuid_value(value):
    if not isinstance(value, str):
        raise ValidationError('Ugyldig kobling.')
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise ValidationError('Ugyldig kobling.')


def ore_value(value, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or value < 0 or value > MAX_ORE:
        raise ValidationError('Beløp må være hele, ikke-negative øre. Fyll ut alle ukjente beløp.')
    return value


def exact_fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValidationError('Forespørselen mangler felt eller inneholder ukjente felt.')
    return value


def history_values(values, current):
    if not isinstance(values, list) or len(values) > 24:
        raise ValidationError('Velg inntil 24 avsluttede kildemåneder.')
    parsed = [month_value(x) for x in values]
    if len(set(parsed)) != len(parsed) or any(x >= current for x in parsed):
        raise ValidationError('Kildemåneder må være forskjellige og avsluttet.')
    return sorted(parsed)
