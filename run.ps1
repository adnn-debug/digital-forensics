# ==============================================================================
# PS-05 Digital Evidence Verification Platform - PowerShell Automation Helper
# ==============================================================================
param (
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$VenvPytest = Join-Path $PSScriptRoot ".venv\Scripts\pytest.exe"
$VenvRuff = Join-Path $PSScriptRoot ".venv\Scripts\ruff.exe"
$VenvMypy = Join-Path $PSScriptRoot ".venv\Scripts\mypy.exe"

switch ($Command) {
    "setup" {
        Write-Host "==> Creating private storage directories..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force -Path "storage/originals", "storage/artifacts", "storage/reports", "storage/tmp" | Out-Null
        Write-Host "==> Setting up Python virtualenv..." -ForegroundColor Cyan
        python -m venv .venv
        & $VenvPython -m pip install --upgrade pip
        & $VenvPython -m pip install -r services\api\requirements-dev.txt
        Write-Host "==> Installing frontend dependencies..." -ForegroundColor Cyan
        Push-Location apps/web
        npm install
        Pop-Location
        Write-Host "==> Setup complete!" -ForegroundColor Green
    }
    "test" {
        Write-Host "==> Running backend Pytest suite..." -ForegroundColor Cyan
        Push-Location services/api
        & $VenvPython -m pytest -v
        Pop-Location
    }
    "lint" {
        Write-Host "==> Running backend ruff linter..." -ForegroundColor Cyan
        Push-Location services/api
        & $VenvRuff check .
        Pop-Location
        Write-Host "==> Running frontend eslint..." -ForegroundColor Cyan
        Push-Location apps/web
        npm run lint
        Pop-Location
    }
    "typecheck" {
        Write-Host "==> Running backend mypy strict type checker..." -ForegroundColor Cyan
        Push-Location services/api
        & $VenvMypy app tests
        Pop-Location
        Write-Host "==> Running frontend TypeScript compiler check..." -ForegroundColor Cyan
        Push-Location apps/web
        npm run typecheck
        Pop-Location
    }
    "dev" {
        Write-Host "==> Starting backend API on http://localhost:8000..." -ForegroundColor Cyan
        Push-Location services/api
        & $VenvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
        Pop-Location
    }
    "worker" {
        Write-Host "==> Starting background worker process..." -ForegroundColor Cyan
        Push-Location services/api
        & $VenvPython -m app.worker
        Pop-Location
    }
    default {
        Write-Host "PS-05 Digital Evidence Verification Platform - PowerShell Helper" -ForegroundColor Yellow
        Write-Host "Usage: .\run.ps1 [command]"
        Write-Host "Commands: setup, test, lint, typecheck, dev, worker"
    }
}
