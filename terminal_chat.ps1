param([int]$Port = 8765, [string]$Model = '')
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' }
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
$previous = $env:DEEPSEEK_API_KEY
$code = 0
Push-Location $PSScriptRoot
try {
    $path = Join-Path $PSScriptRoot '.local/deepseek-key.xml'
    if (-not $env:DEEPSEEK_API_KEY -and (Test-Path -LiteralPath $path)) {
        $secret = Import-Clixml -LiteralPath $path
        $env:DEEPSEEK_API_KEY = ([PSCredential]::new('deepseek', $secret)).GetNetworkCredential().Password
    }
    $params = @('-u', 'terminal_chat.py', '--port', $Port)
    if ($Model) { $params += @('--model', $Model) }
    & $python @params
    $code = $LASTEXITCODE
} finally { $env:DEEPSEEK_API_KEY = $previous; Pop-Location }

exit $code
