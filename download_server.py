"""Optional loopback-only download preview; explicit file allowlist, no directory listing."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
from urllib.parse import urlsplit

FILES = {'/': ('index.html', 'text/html; charset=utf-8'),
         '/index.html': ('index.html', 'text/html; charset=utf-8'),
         '/site.css': ('site.css', 'text/css; charset=utf-8'),
         '/site.js': ('site.js', 'text/javascript; charset=utf-8'),
         '/release.json': ('release.json', 'application/json; charset=utf-8'),
         '/SHA256.txt': ('SHA256.txt', 'text/plain; charset=utf-8'),
         '/Zhongjian-Setup-0.3.0-x64.exe': ('Zhongjian-Setup-0.3.0-x64.exe', 'application/octet-stream')}


class DownloadHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403)
            return
        target = FILES.get(urlsplit(self.path).path)
        if not target:
            self.send_error(404)
            return
        file = self.server.folder / target[0]
        if not file.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', target[1])
        self.send_header('Content-Length', str(file.stat().st_size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        if file.suffix == '.exe':
            self.send_header('Content-Disposition', f'attachment; filename="{file.name}"')
        self.end_headers()
        with file.open('rb') as stream:
            while block := stream.read(256*1024):
                self.wfile.write(block)


def make_server(folder, port=0):
    server = ThreadingHTTPServer(('127.0.0.1', port), DownloadHandler)
    server.daemon_threads = True
    server.folder = Path(folder).resolve()
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--folder', default=str(Path(__file__).resolve().parent.parent / '众见下载'))
    args = parser.parse_args()
    server = make_server(args.folder, args.port)
    print(f'http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
