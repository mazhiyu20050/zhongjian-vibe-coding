import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from download_server import make_server


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        for name, raw in [('index.html', b'<h1>Download</h1>'), ('site.css', b'body{}'),
                          ('site.js', b'"use strict";'), ('release.json', b'{"version":"0.3.0"}'),
                          ('Zhongjian-Setup-0.3.0-x64.exe', b'synthetic installer test bytes')]:
            (self.root / name).write_bytes(raw)
        (self.root / 'private.txt').write_text('not downloadable')
        self.server = make_server(self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def get(self, path, **headers):
        return self.opener.open(urllib.request.Request(self.url + path, headers=headers), timeout=5)

    def test_page_and_assets(self):
        for path in ['/', '/site.css', '/site.js', '/release.json']:
            with self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_installer_is_attachment_and_exact_bytes(self):
        with self.get('/Zhongjian-Setup-0.3.0-x64.exe') as response:
            self.assertIn('attachment;', response.headers['Content-Disposition'])
            self.assertEqual(response.read(), b'synthetic installer test bytes')

    def test_no_listing_private_files_or_traversal(self):
        for path in ['/private.txt', '/../private.txt', '/%2e%2e/private.txt', '/nested/', '/missing.exe']:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_untrusted_host_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get('/', Host='example.org')
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_loopback_binding(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_installer_preserves_user_data_by_design(self):
        text = (Path(__file__).parent / 'installer' / 'zhongjian.iss').read_text(encoding='utf-8-sig')
        self.assertIn('PrivilegesRequired=lowest', text)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\Zhongjian', text)
        self.assertNotIn('[UninstallDelete]', text)
        self.assertIn('skipifsilent', text)


if __name__ == '__main__':
    unittest.main()
