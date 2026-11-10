# Saakh: one-command setup & run (Windows PowerShell)
#   .\run.ps1            setup (first time) + train (if needed) + build UI + start on http://127.0.0.1:8000
#   .\run.ps1 -Test      run the test-suite
param([switch]$Test, [switch]$Retrain)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
  python -m venv (Join-Path $root ".venv")
  & $py -m pip install --upgrade pip
  & $py -m pip install -r (Join-Path $root "backend\requirements.txt")
}
Push-Location (Join-Path $root "backend")
$env:PYTHONIOENCODING = "utf-8"
if ($Test) { & $py -m pytest -q; Pop-Location; exit $LASTEXITCODE }
if ($Retrain -or -not (Test-Path "saakh\risk\artifacts\scorecard.json")) { & $py -m saakh.risk.train }
Pop-Location

$dist = Join-Path $root "frontend\dist\index.html"
if (-not (Test-Path $dist)) {
  Push-Location (Join-Path $root "frontend")
  npm install --no-audit --no-fund
  npm run build
  Pop-Location
}
& $py -m uvicorn saakh.api.main:app --app-dir (Join-Path $root "backend") --host 127.0.0.1 --port 8000
