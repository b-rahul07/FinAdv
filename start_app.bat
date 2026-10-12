@echo off
setlocal enabledelayedexpansion
title AI Financial Advisor - Launcher

echo ==============================================================================
echo                 STARTING AI FINANCIAL ADVISOR (LEDGERLY)
echo ==============================================================================
echo.

:: 1. Clear any stuck ports
echo [1/4] Checking and clearing old processes on ports 8000, 8080, 11434...
for %%P in (8000 8080 11434) do (
    for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
)

:: 2. Start Ollama Server
echo [2/4] Starting local Ollama server on port 11434...
start "Ollama AI Server" cmd /k "ollama serve"
timeout /t 3 /nobreak > nul

:: 3. Start FastAPI Backend
echo [3/4] Starting FastAPI backend on http://127.0.0.1:8000...
start "FastAPI Backend" cmd /k "python -m uvicorn orchestrator.api:app --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak > nul

:: 4. Start Vite React Frontend
echo [4/4] Starting React frontend on http://localhost:8080...
cd trace-wise-advisor-main
start "Vite React Frontend" cmd /k "npm run dev"
cd ..

timeout /t 4 /nobreak > nul

:: Open browser automatically
start http://localhost:8080

echo.
echo ==============================================================================
echo                       ALL SERVICES ARE NOW RUNNING!
echo ==============================================================================
echo - Web Application UI: http://localhost:8080
echo - FastAPI Backend API: http://127.0.0.1:8000
echo - Local Ollama Model:  http://localhost:11434
echo.
echo Keep the opened terminal windows open while using the application.
echo To stop everything, simply close the opened terminal windows.
echo ==============================================================================
echo.
pause