# One-command local startup for the BATMAN Phase-1 real stack (Windows).
#
#   ml-service (:9000)  ->  BATMAN gateway (:8000, proxy + breast-cancer detector)
#
# Usage:  .\scripts\run_stack.ps1
# Stop:   close the two spawned windows, or Ctrl+C in each.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "[batman] ensuring models exist..." -ForegroundColor Yellow
Push-Location $root
if (-not (Test-Path "models\isolation_forest_breast_cancer.joblib")) {
    & $py -m training.prepare
    & $py -m training.train --dataset breast_cancer
}
if (-not (Test-Path "ml-service\model\model.joblib")) {
    Push-Location "ml-service"; & $py -m app.train; Pop-Location
}
Pop-Location

Write-Host "[batman] starting ML service on :9000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$root\ml-service'; & '$py' -m uvicorn app.main:app --host 127.0.0.1 --port 9000"

Start-Sleep -Seconds 4

Write-Host "[batman] starting BATMAN gateway on :8000 (proxy -> :9000) ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$root'; `$env:BATMAN_PROTECTED_MODEL_URL='http://127.0.0.1:9000'; `$env:BATMAN_DETECTOR_PATH='models/isolation_forest_breast_cancer.joblib'; & '$py' -m uvicorn batman.gateway.app:app --host 127.0.0.1 --port 8000"

Write-Host ""
Write-Host "[batman] stack starting." -ForegroundColor Green
Write-Host "  ML service : http://127.0.0.1:9000/health"
Write-Host "  BATMAN     : http://127.0.0.1:8000/v1/health"
Write-Host "  Try:  $py -m experiments.normal_client --requests 60"
Write-Host "        $py -m experiments.attack_client"
