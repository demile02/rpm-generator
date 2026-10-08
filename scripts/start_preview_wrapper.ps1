# Wrapper: runs the preview launcher and saves the printed pid to a file.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $root '.freebuff/preview.pid'
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_preview_server.ps1') 2>&1
$out | Out-File -FilePath $pidFile -Encoding ascii
Write-Output "launcher done"
