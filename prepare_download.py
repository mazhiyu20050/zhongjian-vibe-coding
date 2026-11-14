"""Build a local-only download folder. No credentials, telemetry or public publishing."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
NAME = 'Zhongjian-Setup-0.3.0-x64.exe'


def prepare(destination=None):
    installer = ROOT / 'dist' / 'installer' / NAME
    raw = installer.read_bytes()
    output = Path(destination) if destination else ROOT.parent / '众见下载'
    output.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'site.css', 'site.js'):
        shutil.copy2(ROOT / 'download' / name, output / name)
    shutil.copy2(installer, output / NAME)
    manifest = {'version': '0.3.0', 'filename': NAME, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'signed': False, 'hosting': 'local-only'}
    (output / 'release.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'SHA256.txt').write_text(manifest['sha256'] + '  ' + NAME + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    print(prepare())
