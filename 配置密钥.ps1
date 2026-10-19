$ErrorActionPreference = 'Stop'
# Export-Clixml uses Windows DPAPI for SecureString, bound to this Windows user.
$folder = Join-Path $PSScriptRoot '.local'
$path = Join-Path $folder 'deepseek-key.xml'
Write-Host '本工具将新密钥加密保存在本机，供后续自动测试使用。文件已排除Git。'
Write-Host '请使用已重新生成的密钥；输入不会回显。'
$key = Read-Host '输入 DeepSeek 新密钥' -AsSecureString
if ($key.Length -eq 0) { Write-Host '未输入密钥，已结束。'; exit 2 }
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$key | Export-Clixml -LiteralPath $path
Write-Host '本机加密配置已保存。告诉我“已配置”，后面的测试由我执行。'
