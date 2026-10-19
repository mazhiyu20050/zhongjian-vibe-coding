param([switch]$UseSavedKey)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
Push-Location $PSScriptRoot
try {
    if ($UseSavedKey) {
        $path = Join-Path $PSScriptRoot '.local/deepseek-key.xml'
        if (-not (Test-Path -LiteralPath $path)) { throw '尚未配置本机加密密钥。' }
        $secret = Import-Clixml -LiteralPath $path
        $credential = New-Object System.Management.Automation.PSCredential('deepseek', $secret)
        $previous = $env:DEEPSEEK_API_KEY
        try {
            $env:DEEPSEEK_API_KEY = $credential.GetNetworkCredential().Password
            & $python 'evaluate.py' '--live' '--configured'
        } finally {
            $env:DEEPSEEK_API_KEY = $previous
            $credential = $null
        }
    } else {
        & $python 'evaluate.py' '--live'
    }
} finally { Pop-Location }
