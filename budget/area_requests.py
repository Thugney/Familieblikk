"""Explicit per-request financial capability; never store area selection in a session."""
from functools import wraps
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import html
import json
import re
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import resolve, Resolver404
from . import financial_areas

NONFINANCIAL_PAGES = {'familie', 'varsler', 'mer', 'kalender', 'handlelister'}
FINANCIAL_NAMES = {'documents', 'document_detail', 'document_original', 'shopping_complete', 'shopping_receipt', 'correction', 'correction_history', 'correction_export', 'spending_data', 'planning_data', 'planning_preview', 'planning_save', 'create', 'edit', 'delete', 'pay', 'debt_plan', 'apply_import', 'resolve_import', 'preferences'}
API_NAMES = {'spending_data', 'planning_data', 'planning_preview', 'planning_save'}
WRITE_FORM_NAMES = {'create', 'edit', 'delete', 'pay', 'correction', 'shopping_complete', 'shopping_receipt', 'resolve_import'}
OPTIONAL_NAMES = {'shopping_lists', 'shopping_detail', 'shopping_revision', 'shopping_item'}

def financial_url(value, area_id, current_path='/'):
    value = html.unescape(value)
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or value.startswith('#'):
        return value
    path = parts.path or current_path
    try:
        match = resolve(path)
    except Resolver404:
        return value
    if match.url_name not in FINANCIAL_NAMES | OPTIONAL_NAMES and not (match.url_name == 'page' and (match.kwargs.get('page') not in NONFINANCIAL_PAGES or match.kwargs.get('page') == 'mer')):
        return value
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == 'area' for key, _ in query):
        query.append(('area', str(area_id)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

def propagate(response, request, area):
    if response.has_header('Location'):
        response['Location'] = financial_url(response['Location'], area.pk, request.path)
    if not response.streaming and response.get('Content-Type', '').startswith('text/html'):
        content = response.content.decode(response.charset)
        def attribute(match):
            value = financial_url(match.group(3), area.pk, request.path)
            return match.group(1) + match.group(2) + html.escape(value, quote=True) + match.group(2)
        content = re.sub(r'((?:href|action)=)([\"\'])(.*?)\2', attribute, content)
        # GET forms discard their action query; a hidden input preserves this tab's target.
        content = re.sub(r'(<form\b[^>]*>)', lambda m: m.group(1) + '<input type="hidden" name="area" value="' + str(area.pk) + '">', content)
        response.content = content.encode(response.charset)
        if response.has_header('Content-Length'):
            response['Content-Length'] = len(response.content)
    return response

def area_boundary(view, name):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        required = name in FINANCIAL_NAMES or name == 'page' and kwargs.get('page') not in NONFINANCIAL_PAGES
        optional = name in OPTIONAL_NAMES or name == 'page' and kwargs.get('page') == 'mer'
        if not required and not optional:
            return view(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return view(request, *args, **kwargs)
        from .models import Membership
        member = Membership.objects.filter(user=request.user).first()
        if not member:
            if name in API_NAMES:
                return view(request, *args, **kwargs)
            return redirect('family_gate')
        values = request.GET.getlist('area') + request.POST.getlist('area')
        if request.content_type == 'application/json' and request.body:
            try:
                payload = json.loads(request.body)
                if isinstance(payload, dict) and 'area' in payload:
                    values.append(str(payload['area']))
            except (ValueError, UnicodeDecodeError):
                if not values: raise PermissionDenied('Ugyldig forespørsel.') from None
        if len(set(values)) > 1 or len(request.GET.getlist('area')) > 1 or len(request.POST.getlist('area')) > 1:
            raise PermissionDenied('Motstridende målbudsjett. Last siden på nytt.')
        area_id = values[0] if values else None
        if not area_id:
            if optional:
                return view(request, *args, **kwargs)
            if request.method in ('GET', 'HEAD') and name not in API_NAMES:
                return redirect('/budsjetter/?' + urlencode({'next': request.get_full_path()}))
            raise PermissionDenied('Velg målbudsjett før du lagrer.')
        with financial_areas.area_scope(member, area_id, write=required and (name in WRITE_FORM_NAMES or request.method not in ('GET', 'HEAD', 'OPTIONS'))) as area:
            request.financial_area = area
            request.financial_can_write = financial_areas.can_write(member, area)
            response = view(request, *args, **kwargs)
            return propagate(response, request, area)
    @wraps(view)
    def response_boundary(request, *args, **kwargs):
        try:
            return wrapped(request, *args, **kwargs)
        except PermissionDenied as error:
            if name in API_NAMES:
                return JsonResponse({'error': str(error) or 'Ingen tilgang.'}, status=403)
            raise
    return response_boundary
