# Kill any process listening on port 5000.
$conns = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) {
  if ($p -and $p -ne 0) {
    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    Write-Output "stopped $p"
  }
}
