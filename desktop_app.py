"""Windows desktop shell. Local HTTP only; credentials protected with Windows DPAPI."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import urllib.request

from web_server import LocalServer, Handler, ROOT, create_server, configure_server

VERSION = '0.3.0'


def user_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Zhongjian'


def protect(raw, decrypt=False):
    if sys.platform != 'win32':
        raise RuntimeError('windows_required')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), 'Zhongjian API key', None, None, None, 1, ctypes.byref(output))
    fn.restype = wintypes.BOOL
    if not fn(*args):
        raise OSError('credential_protection_failed')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class Settings:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / 'settings.json'
        self.key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        self.model = os.environ.get('DEEPSEEK_MODEL', '').strip() or 'deepseek-flash'
        self.warning = ''
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                self.key = protect(base64.b64decode(data['encrypted_key'], validate=True), True).decode()
                self.model = data['model']
            except (OSError, ValueError, KeyError, UnicodeError):
                self.warning = '本机配置读取失败，请重新填写密钥。'

    def save(self, key, model):
        if not isinstance(key, str) or not isinstance(model, str):
            raise ValueError('请填写密钥与模型名称。')
        key = key.strip() or self.key
        model = model.strip()
        if not re.fullmatch(r'[A-Za-z0-9_\-]{8,256}', key):
            raise ValueError('请填写有效的 API 密钥。')
        if not re.fullmatch(r'[A-Za-z0-9_.\-]{1,80}', model):
            raise ValueError('模型名称格式有误。')
        payload = {'version': 1, 'model': model,
                   'encrypted_key': base64.b64encode(protect(key.encode())).decode()}
        self.folder.mkdir(parents=True, exist_ok=True)
        # Atomic replacement: interrupted writes leave the previous file intact.
        fd, temp = tempfile.mkstemp(prefix='settings-', suffix='.tmp', dir=self.folder)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle)
            os.replace(temp, self.path)
        finally:
            Path(temp).unlink(missing_ok=True)
        self.key, self.model, self.warning = key, model, ''


class DesktopHandler(Handler):
    def send(self, status, value, content_type='application/json; charset=utf-8'):
        if content_type.startswith('text/html'):
            value = value.replace(b'</head>', b'<link rel="stylesheet" href="/desktop.css"><script src="/desktop.js" defer></script></head>')
        super().send(status, value, content_type)

    def do_GET(self):
        if not self.trusted_host():
            return self.send(403, {'error': 'host_rejected'})
        if self.path in ('/desktop.js', '/desktop.css'):
            mime = 'text/javascript' if self.path.endswith('.js') else 'text/css'
            return self.send(200, (ROOT / 'desktop' / self.path[1:]).read_bytes(), mime + '; charset=utf-8')
        if self.path == '/api/desktop/settings':
            if not self.authorized():
                return
            config = self.server.settings
            return self.send(200, {'configured': bool(config.key), 'model': config.model,
                                   'version': VERSION, 'warning': config.warning})
        super().do_GET()

    def do_POST(self):
        if self.path != '/api/desktop/settings':
            return super().do_POST()
        if not self.trusted_host():
            return self.send(403, {'error': 'host_rejected'})
        if not self.authorized():
            self.close_connection = True
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.close_connection = True
                return self.send(415, {'error': 'json_required'})
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                self.close_connection = True
                return self.send(413, {'error': 'request_too_large'})
            self.connection.settimeout(10)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('设置格式有误。')
            # Lock out new queries and avoid replacing the agent mid-conversation.
            acquired = 0
            try:
                for _ in range(2):
                    if not self.server.slots.acquire(blocking=False):
                        return self.send(409, {'message': '请等本次回答结束后再保存设置。'})
                    acquired += 1
                config = self.server.settings
                config.save(data.get('key', ''), data.get('model', ''))
                configure_server(self.server, config.key, config.model, config.folder)
                return self.send(200, {'saved': True, 'ready': True})
            finally:
                for _ in range(acquired):
                    self.server.slots.release()
        except (ValueError, UnicodeError):
            return self.send(400, {'message': '请检查 API 密钥和模型名称。'})
        except Exception:
            return self.send(500, {'message': '设置保存失败，请检查用户目录的写入权限。'})


class DesktopServer(LocalServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = DesktopHandler


def start_backend(config):
    server = create_server(0, config.key, config.model, config.folder, DesktopServer)
    server.settings = config
    thread = threading.Thread(target=server.serve_forever, name='zhongjian-http', daemon=True)
    thread.start()
    return server, thread


def self_test(folder):
    """Frozen executable smoke check; never calls the paid provider."""
    config = Settings(folder)
    config.key = ''
    server, thread = start_backend(config)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = f'http://127.0.0.1:{server.server_port}'
        session = json.load(opener.open(url + '/api/session'))
        assert session['records'] > 2000 and not session['ready']
        assert b'desktop.js' in opener.open(url).read()
        assert b'pywebview' not in opener.open(url + '/desktop.js').read()
        from person_skills import load_skills
        from presentation import simplified
        assert simplified('學習') == '学习'
        result = {'passed': True, 'version': VERSION, 'records': session['records'],
                  'skills': len(load_skills()), 'checks': ['bundled_assets', 'corpus', 'skill_hashes', 'opencc', 'loopback_http']}
        (Path(folder) / 'desktop-self-test.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', metavar='OUTPUT_DIR')
    parser.add_argument('--ui-smoke-test', metavar='OUTPUT_DIR')
    args = parser.parse_args()
    if args.self_test:
        Path(args.self_test).mkdir(parents=True, exist_ok=True)
        self_test(args.self_test)
        return
    import webview
    temp = tempfile.TemporaryDirectory() if args.ui_smoke_test else None
    config = Settings(temp.name if temp else user_directory())
    if temp:
        config.key = ''
    server, thread = start_backend(config)
    window = webview.create_window('众见', f'http://127.0.0.1:{server.server_port}/',
                                   width=1120, height=820, min_size=(520, 560),
                                   background_color='#fafaf8', text_select=True)
    def open_conversation_window(cid):
        webview.create_window('众见 · 历史对话',
                              f'http://127.0.0.1:{server.server_port}/?conversation={cid}',
                              width=1020,height=760,min_size=(520,560),text_select=True)
    server.open_conversation_window=open_conversation_window
    if args.ui_smoke_test:
        def smoke():
            import time
            out = Path(args.ui_smoke_test)
            out.mkdir(parents=True, exist_ok=True)
            try:
                for _ in range(60):
                    if window.evaluate_js("!!document.querySelector('#desktop-dialog[open]')"):
                        break
                    time.sleep(.25)
                checks = window.evaluate_js("({title:document.title,settings:!!document.querySelector('#desktop-dialog[open]'),input:!!document.querySelector('textarea'),password:document.querySelector('#desktop-key').type,overflow:document.documentElement.scrollWidth>innerWidth,buttonFits:document.querySelector('#desktop-save').getBoundingClientRect().width>70})")
                assert checks['settings'] and checks['input'] and checks['password'] == 'password'
                assert not checks['overflow'] and checks['buttonFits']
                (out / 'desktop-ui-test.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
                try:
                    from PIL import Image
                    # Capture only our window, never the user's desktop/background.
                    user32 = ctypes.windll.user32
                    boxes = []
                    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                    def own_window(hwnd, _):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value == os.getpid() and user32.IsWindowVisible(hwnd):
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            boxes.append((hwnd, rect.right-rect.left, rect.bottom-rect.top))
                        return True
                    user32.EnumWindows(callback_type(own_window), 0)
                    if boxes:
                        hwnd, width, height = max(boxes, key=lambda b: b[1]*b[2])
                        # PrintWindow renders only this HWND even if another app overlaps it.
                        gdi = ctypes.windll.gdi32
                        user32.GetDC.restype = wintypes.HDC
                        gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
                        gdi.CreateCompatibleDC.restype = wintypes.HDC
                        gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                                       ctypes.c_void_p, wintypes.HANDLE, wintypes.DWORD]
                        gdi.CreateDIBSection.restype = wintypes.HBITMAP
                        gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
                        gdi.SelectObject.restype = wintypes.HANDLE
                        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
                        gdi.DeleteDC.argtypes = [wintypes.HDC]
                        user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
                        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
                        class Header(ctypes.Structure):
                            _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG),
                                        ('height', wintypes.LONG), ('planes', wintypes.WORD),
                                        ('bitcount', wintypes.WORD), ('compression', wintypes.DWORD),
                                        ('image_size', wintypes.DWORD), ('x', wintypes.LONG),
                                        ('y', wintypes.LONG), ('used', wintypes.DWORD), ('important', wintypes.DWORD)]
                        header = Header(40, width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0)
                        screen = user32.GetDC(hwnd)
                        dc = gdi.CreateCompatibleDC(screen)
                        bits = ctypes.c_void_p()
                        bitmap = gdi.CreateDIBSection(screen, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
                        old = gdi.SelectObject(dc, bitmap)
                        try:
                            if user32.PrintWindow(hwnd, dc, 2):
                                raw = ctypes.string_at(bits, width*height*4)
                                Image.frombytes('RGB', (width,height), raw, 'raw', 'BGRX').save(out / 'desktop-ui.png')
                        finally:
                            gdi.SelectObject(dc, old)
                            gdi.DeleteObject(bitmap)
                            gdi.DeleteDC(dc)
                            user32.ReleaseDC(hwnd, screen)
                except ImportError:
                    pass
            finally:
                window.destroy()
        window.events.loaded += lambda: threading.Thread(target=smoke, daemon=True).start()
    try:
        # Use the Windows-installed Edge runtime, not a bundled Chromium copy.
        webview.start(gui='edgechromium', private_mode=True, storage_path=str(config.folder / 'webview'))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if temp:
            temp.cleanup()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Avoid exporting personal inputs or credentials through exception text.
        if '--self-test' in sys.argv:
            import traceback
            index=sys.argv.index('--self-test')
            if index+1<len(sys.argv):
                folder=Path(sys.argv[index+1]);folder.mkdir(parents=True,exist_ok=True)
                (folder/'self-test-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            sys.exit(1)
        if sys.platform == 'win32':
            ctypes.windll.user32.MessageBoxW(None,
                '启动未完成。请确认已完整解压文件夹，并已安装 Microsoft Edge WebView2 Runtime。', '众见', 16)
        sys.exit(1)
