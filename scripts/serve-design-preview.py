"""Serve only approved fictional preview assets, never the project filesystem."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
import argparse
import mimetypes
import re
import socket

ROOT = Path(__file__).resolve().parents[1]
EXACT = {'/.project-init/review.html', '/.project-init/familieblikk-mockup.html',
         '/.project-init/lean/familieblikk-review.html',
         '/.project-init/evidence/design-desktop.png', '/.project-init/evidence/design-mobile.png'}

def preview_file(raw_path, root=ROOT):
    decoded = unquote(urlsplit(raw_path).path)
    if '\\' in decoded or '\x00' in decoded or any(p == '..' for p in decoded.split('/')):
        return None
    allowed = decoded in EXACT or re.fullmatch(r'/\.project-init/visual/(baselines|actual)/[a-z0-9_-]+\.png', decoded)
    if not allowed:
        return None
    path = (root / decoded.lstrip('/')).resolve()
    approved_directory = (root / '.project-init').resolve()
    if not path.is_relative_to(approved_directory) or not path.is_file():
        return None
    return path

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.serve(False)

    def do_HEAD(self):
        self.serve(True)

    def serve(self, head):
        host = self.headers.get('Host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            self.send_error(403)
            return
        path = preview_file(self.path)
        if path is None:
            self.send_error(404, 'Preview asset not available')
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', (mimetypes.guess_type(path)[0] or 'application/octet-stream') + ('; charset=utf-8' if path.suffix == '.html' else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def log_message(self, *_args):
        # No private query strings or file paths in the terminal/log stream.
        return

class PreviewServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can allow two HTTP servers to claim the same port,
    # leaving traffic on an old unrestricted server. Fail closed instead.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    args = parser.parse_args()
    server = PreviewServer(('127.0.0.1', args.port), Handler)
    print(f'Design-only preview listening on 127.0.0.1:{args.port}; private data is not served.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
