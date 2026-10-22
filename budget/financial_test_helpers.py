"""Explicit area fixtures for pre-area workflow regression contracts."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from contextvars import Context
from django.test import Client
from .financial_areas import area_scope, create_area


class AreaClient(Client):
    def __init__(self, area, **kwargs):
        super().__init__(**kwargs)
        self.area = area

    def request(self, **request):
        # A browser request starts without the test's direct-service capability.
        # The real URL boundary must resolve this request's actor and area itself.
        return Context().run(super().request, **request)

    def generic(self, method, path, *args, **kwargs):
        parts = urlsplit(str(path))
        query = parse_qsl(parts.query, keep_blank_values=True)
        if 'QUERY_STRING' in kwargs:
            query += parse_qsl(kwargs.pop('QUERY_STRING'), keep_blank_values=True)
        if kwargs.get('query_params'):
            query += parse_qsl(urlencode(kwargs.pop('query_params'), doseq=True), keep_blank_values=True)
        if not any(key == 'area' for key, _ in query):
            query.append(('area', str(self.area.pk)))
        path = urlunsplit(parts._replace(query=urlencode(query)))
        return super().generic(method, path, *args, **kwargs)


def install_area(test, member, editors=(), area=None):
    test.area = area or create_area(member, 'Synthetic workflow budget',
        editor_ids=[editor.pk for editor in editors], kind='shared' if editors else 'personal')
    scope = area_scope(member, test.area.pk)
    scope.__enter__()
    test.addCleanup(scope.__exit__, None, None, None)
    test.client = AreaClient(test.area)
    return test.area
