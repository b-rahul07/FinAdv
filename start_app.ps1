# ==============================================================================
#                 STARTING AI FINANCIAL ADVISOR (LEDGERLY) - POWERSHELL
# ==============================================================================

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "                 STARTING AI FINANCIAL ADVISOR (LEDGERLY)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Clear ports 8000, 8080, 11434 if in use
Write-Host "[1/4] Checking and clearing old processes on ports 8000, 8080, 11434..." -ForegroundColor Yellow
$ports = @(8000, 8080, 11434)
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

# 2. Start Ollama Server
Write-Host "[2/4] Starting local Ollama server..." -ForegroundColor Yellow
Start-Process "cmd.exe" -ArgumentList "/k", "ollama serve"
Start-Sleep -Seconds 3

# 3. Start FastAPI Backend
Write-Host "[3/4] Starting FastAPI backend on http://127.0.0.1:8000..." -ForegroundColor Yellow
Start-Process "cmd.exe" -ArgumentList "/k", "python -m uvicorn orchestrator.api:app --host 127.0.0.1 --port 8000"
Start-Sleep -Seconds 3

# 4. Start Vite React Frontend
Write-Host "[4/4] Starting React frontend on http://localhost:8080..." -ForegroundColor Yellow
Start-Process "cmd.exe" -ArgumentList "/k", "cd /d `"$PSScriptRoot\trace-wise-advisor-main`" && npm run dev"
Start-Sleep -Seconds 4

# Open browser automatically
Start-Process "http://localhost:8080"

Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host "                       ALL SERVICES ARE NOW RUNNING!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "- Web Application UI: http://localhost:8080"
Write-Host "- FastAPI Backend API: http://127.0.0.1:8000"
Write-Host "- Local Ollama Model:  http://localhost:11434`n"
Write-Host "Keep the opened terminal windows open while using the application."
Write-Host "To stop everything, simply close the opened terminal windows."
Write-Host "==============================================================================" -ForegroundColor Green
