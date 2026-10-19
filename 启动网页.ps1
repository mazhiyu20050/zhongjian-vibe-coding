param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
Push-Location $PSScriptRoot
$previous = $env:DEEPSEEK_API_KEY
try {
    $path = Join-Path $PSScriptRoot '.local/deepseek-key.xml'
    if (Test-Path -LiteralPath $path) {
        $secret = Import-Clixml -LiteralPath $path
        $credential = New-Object System.Management.Automation.PSCredential('deepseek', $secret)
        $env:DEEPSEEK_API_KEY = $credential.GetNetworkCredential().Password
    }
    & $python '-u' 'web_server.py' '--port' $Port
} finally {
    $env:DEEPSEEK_API_KEY = $previous
    $credential = $null
    Pop-Location
}
