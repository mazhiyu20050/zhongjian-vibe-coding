import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from desktop_app import Settings, protect, start_backend, user_directory


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'DEEPSEEK_API_KEY': '', 'DEEPSEEK_MODEL': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = Settings(self.temp.name)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows DPAPI')
    def test_dpapi_roundtrip_and_ciphertext(self):
        key = 'sk-synthetic-test-not-a-real-key'
        self.config.save(key, 'deepseek-flash')
        raw = self.config.path.read_text()
        self.assertNotIn(key, raw)
        loaded = Settings(self.temp.name)
        self.assertEqual(loaded.key, key)
        self.assertEqual(loaded.model, 'deepseek-flash')
        loaded.save('', 'deepseek-chat')
        self.assertEqual(Settings(self.temp.name).key, key)

    def test_invalid_settings_do_not_write(self):
        for key, model in [('', 'deepseek-flash'), ('bad key\n', 'abc'), ('sk-synthetic-test', '../model'), (42, 'abc')]:
            with self.assertRaises(ValueError):
                self.config.save(key, model)
        self.assertFalse(self.config.path.exists())

    def test_corrupt_settings_can_be_reentered(self):
        self.config.path.write_text('{broken', encoding='utf-8')
        self.assertTrue(Settings(self.temp.name).warning)

    def test_storage_is_per_user_not_bundle(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name}):
            self.assertEqual(user_directory(), Path(self.temp.name) / 'Zhongjian')

    def start(self):
        self.server, self.thread = start_backend(self.config)
        def close():
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        self.addCleanup(close)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body=None, token=True, **headers):
        if token:
            headers['X-Zhongjian-Token'] = self.server.nonce
        raw = json.dumps(body).encode() if body is not None else None
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        return self.opener.open(urllib.request.Request(self.url + path, data=raw, headers=headers), timeout=5)

    def test_assets_session_and_no_key_readback(self):
        self.start()
        self.assertIn(b'desktop.js', self.request('/').read())
        self.assertIn(b'desktop-dialog', self.request('/desktop.js').read())
        status = json.load(self.request('/api/desktop/settings'))
        self.assertEqual(status['configured'], False)
        self.assertNotIn('key', status)
        self.assertGreater(json.load(self.request('/api/session'))['records'], 2000)

    def test_settings_require_token_and_trusted_origin(self):
        self.start()
        for headers, token in [({}, False), ({'Origin': 'https://example.org'}, True)]:
            with self.assertRaises(urllib.error.HTTPError) as c:
                self.request('/api/desktop/settings', token=token, **headers)
            self.assertEqual(c.exception.code, 403)
            c.exception.close()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows DPAPI')
    def test_save_activates_backend_without_provider_call(self):
        self.start()
        with patch('desktop_app.configure_server', wraps=__import__('web_server').configure_server):
            result = json.load(self.request('/api/desktop/settings', {'key':'sk-synthetic-only-test', 'model':'deepseek-flash'}))
        self.assertTrue(result['ready'])
        self.assertTrue(json.load(self.request('/api/session'))['ready'])
        self.assertNotIn('sk-synthetic', json.dumps(json.load(self.request('/api/desktop/settings'))))
        self.assertTrue((Path(self.temp.name)/'collections.sqlite3').exists())

    def test_busy_save_preserves_settings(self):
        self.start()
        self.server.slots.acquire()
        try:
            with self.assertRaises(urllib.error.HTTPError) as c:
                self.request('/api/desktop/settings', {'key':'sk-synthetic-only-test', 'model':'deepseek-flash'})
            self.assertEqual(c.exception.code, 409)
            c.exception.close()
            self.assertFalse(self.config.path.exists())
        finally:
            self.server.slots.release()
        self.assertTrue(self.server.slots.acquire(blocking=False))
        self.assertTrue(self.server.slots.acquire(blocking=False))
        self.server.slots.release(); self.server.slots.release()

    def test_oversized_save_is_rejected(self):
        self.start()
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.request('/api/desktop/settings', {'key':'x'*5000})
        self.assertEqual(c.exception.code, 413)
        c.exception.close()

    def test_bad_settings_do_not_enable_service(self):
        self.start()
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.request('/api/desktop/settings', {'key':'bad', 'model':'../x'})
        self.assertEqual(c.exception.code, 400)
        c.exception.close()
        self.assertFalse(json.load(self.request('/api/session'))['ready'])


if __name__ == '__main__':
    unittest.main()
