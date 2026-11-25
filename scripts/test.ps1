$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Backend virtual environment not found at $PythonExe. Run 'python -m venv .venv' and install requirements-dev.txt first."
}

Push-Location $BackendDir
try {
    Write-Host "==> Running pytest..." -ForegroundColor Cyan
    & $PythonExe -m pytest -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Running ruff..." -ForegroundColor Cyan
    & $PythonExe -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> Running mypy..." -ForegroundColor Cyan
    & $PythonExe -m mypy app tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "All checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
