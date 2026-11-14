param([string]$Compiler = '')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'dist/众见/众见.exe')) { throw 'Build desktop first: build_desktop.ps1' }
    if (-not $Compiler) {
        $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($found) { $Compiler = $found.Source }
        else { $Compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe' }
    }
    if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Install Inno Setup 6.7+ or pass -Compiler with its full ISCC.exe path.' }
    & $Compiler 'installer/zhongjian.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    $python = Join-Path $PSScriptRoot '.desktop-venv/Scripts/python.exe'
    & $python prepare_download.py
    if ($LASTEXITCODE -ne 0) { throw 'Download page preparation failed' }
} finally { Pop-Location }
