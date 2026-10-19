$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
Push-Location $PSScriptRoot
try { & $python 'check_api.py' } finally { Pop-Location }
