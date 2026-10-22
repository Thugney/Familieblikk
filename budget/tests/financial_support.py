"""Explicit area capabilities for the pre-existing financial regression fixtures."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from django.test import Client
from budget.financial_areas import area_scope
from budget.models import Membership

class FinancialClient(Client):
    def __init__(self, *args, area_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.area_id = area_id
    def request(self, **request):
        from contextvars import Context
        return Context().run(super().request, **request)
    def force_login(self, user, backend=None):
        if hasattr(user, 'test_area'):
            self.area_id = user.test_area.pk
        return super().force_login(user, backend)
    def generic(self, method, path, *args, **kwargs):
        if self.area_id:
            if kwargs.get('query_params'):
                kwargs['query_params'] = {**kwargs['query_params']}
                kwargs['query_params'].setdefault('area', str(self.area_id))
            if kwargs.get('QUERY_STRING'):
                query = parse_qsl(kwargs['QUERY_STRING'], keep_blank_values=True)
                if not any(k == 'area' for k, v in query): query.append(('area', str(self.area_id)))
                kwargs['QUERY_STRING'] = urlencode(query)
            parts = urlsplit(path)
            query = parse_qsl(parts.query, keep_blank_values=True)
            if not any(k == 'area' for k, v in query):
                query.append(('area', str(self.area_id)))
            path = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        return super().generic(method, path, *args, **kwargs)

def enter_fixture_area(case, user, area=None):
    from budget.financial_test_helpers import install_area
    area = install_area(case, Membership.objects.get(user=user), area=area or user.test_area)
    case.client = FinancialClient(area_id=area.pk)
    return area
