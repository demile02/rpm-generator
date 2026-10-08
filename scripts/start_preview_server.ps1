# Preview server launcher - loads the 9Router API key at RUNTIME from the
# router DB (never stored in this repo, never printed), then starts the
# Flask server detached with logs redirected to separate files.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$key = & python -X utf8 -c "import sqlite3; conn = sqlite3.connect(r'C:\Users\User\AppData\Roaming\9router\db\data.sqlite'); row = conn.execute('SELECT key FROM apiKeys WHERE isActive = 1 LIMIT 1').fetchone(); print(row[0] if row else '')"
if (-not $key) { Write-Error 'No active 9Router API key found in router DB'; exit 1 }
$env:NINE_ROUTER_API_KEY = $key

$proc = Start-Process -FilePath 'python.exe' `
  -ArgumentList 'src/app.py' `
  -WorkingDirectory $root `
  -RedirectStandardOutput (Join-Path $root '.freebuff/preview-aab14663-2150-40e7-ad63-39534c95b6fb.log') `
  -RedirectStandardError (Join-Path $root '.freebuff/preview-aab14663-2150-40e7-ad63-39534c95b6fb.log.err') `
  -WindowStyle Hidden -PassThru
$proc.Id
