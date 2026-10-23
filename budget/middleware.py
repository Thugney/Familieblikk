from django.http import HttpResponseBadRequest
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from .work_limits import FinancialWorkLimit, financial_work_scope


class PrivateResponseMiddleware(MiddlewareMixin):
    async_capable = False

    def __init__(self, get_response):
        super().__init__(get_response)

    def __call__(self, request):
        with financial_work_scope():
            return super().__call__(request)

    def process_exception(self, request, exception):
        if isinstance(exception, FinancialWorkLimit):
            return HttpResponseBadRequest(exception.messages[0], content_type='text/plain; charset=utf-8')

    def process_response(self, request, response):
        if not request.path.startswith('/static/') and request.path not in ['/manifest.webmanifest', '/offline/', '/sw.js']:
            response['Cache-Control'] = 'private, no-store, max-age=0'
            patch_vary_headers(response, ['Cookie'])
        response['Referrer-Policy'] = 'same-origin'
        response['X-Frame-Options'] = 'DENY'
        response.setdefault('Content-Security-Policy', (
            "default-src 'self'; script-src 'self'; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; "
            "connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-src 'none'; frame-ancestors 'none'; form-action 'self'"
        ))
        response['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=(), payment=(), usb=()'
        return response
