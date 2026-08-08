$ErrorActionPreference = "Stop"

function Test-CommandExists {
  param([string]$CommandName)

  return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

$hasUv = Test-CommandExists "uv"
if (-not $hasUv) {
  Write-Warning "uv command not found in PATH. Will attempt to use local python environment if available."
}

if (-not (Test-CommandExists "pnpm")) {
  Write-Error "Missing required command: pnpm"
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start each service in its own PowerShell window so logs remain visible.
if (Test-CommandExists "livekit-server") {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repoRoot'; livekit-server --dev"
} else {
  Write-Warning "livekit-server was not found. Skipping local LiveKit startup and using your configured LIVEKIT_URL instead."
}

if ($hasUv) {
  $backendCmd = "uv run python src/agent.py dev"
} elseif (Test-Path "$repoRoot\backend\.venv\Scripts\python.exe") {
  $backendCmd = ".\.venv\Scripts\python.exe src/agent.py dev"
} else {
  $backendCmd = "python src/agent.py dev"
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repoRoot\backend'; $backendCmd"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repoRoot\frontend'; pnpm dev"

Write-Host "Started backend and frontend in separate PowerShell windows."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repoRoot\backend'; uv run python src/agent.py dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repoRoot\frontend'; pnpm dev"

Write-Host "Started backend and frontend in separate PowerShell windows."
