$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot '.desktop-venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        python -m venv .desktop-venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
    }
    & $python -m pip install -r requirements-desktop.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & $python -m PyInstaller desktop.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
    Copy-Item -LiteralPath 'docs/DESKTOP_QUICKSTART.txt' -Destination 'dist/众见/使用说明.txt' -Force
    $zip = Join-Path $PSScriptRoot 'dist/众见-Windows-0.3.0.zip'
    Compress-Archive -LiteralPath 'dist/众见' -DestinationPath $zip -Force
    Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
} finally { Pop-Location }
