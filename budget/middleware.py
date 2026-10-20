class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith('/static/') and request.path not in ['/manifest.webmanifest', '/offline/', '/sw.js']:
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Vary'] = 'Cookie'
        response['Referrer-Policy'] = 'same-origin'
        response['X-Frame-Options'] = 'DENY'
        return response
