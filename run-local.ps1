$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Virtual environment Python not found at $pythonExe"
}

# Keep auto-reload focused on application source only; ignore test and log directories.
# Using plain directory excludes is stable in this PowerShell + uvicorn setup.
& $pythonExe -m uvicorn app.main:app --reload --reload-dir app --reload-exclude tests --reload-exclude logs --host 127.0.0.1 --port 8011
