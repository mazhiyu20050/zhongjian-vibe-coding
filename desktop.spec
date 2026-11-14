# Build from the repository root with: python -m PyInstaller desktop.spec --noconfirm
from pathlib import Path
import ssl
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
datas = [(str(root / 'web'), 'web'), (str(root / 'desktop'), 'desktop'),
         (str(root / 'skills' / 'people'), 'skills/people'),
         (str(root / 'data' / 'people'), 'data/people')]
# Explicit runtime data only: never package .local, private logs, source snapshots or keys.
for item in (root / 'data' / 'processed').glob('*'):
    if item.name.endswith('.jsonl') or item.name.startswith('thoughts_') and item.suffix == '.json':
        datas.append((str(item), 'data/processed'))
datas += collect_data_files('opencc')
# This Python distribution's ssl.py loads its certificate policy beside itself.
# Preserve that runtime asset rather than weakening verification or patching SSL.
certificate_policy=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if certificate_policy.is_file():
    datas.append((str(certificate_policy), '.'))
a = Analysis([str(root / 'desktop_app.py')], pathex=[str(root)], datas=datas,
             hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
             excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'matplotlib', 'numpy', 'PIL'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='众见', debug=False,
          strip=False, upx=False, console=False, icon=str(root / 'desktop' / 'zhongjian.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='众见')
