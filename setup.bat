@echo off
setlocal enabledelayedexpansion
title AI Financial Advisor - Automated Setup Script

echo ==============================================================================
echo                AI FINANCIAL ADVISOR - 1-CLICK TEAMMATE SETUP
echo ==============================================================================
echo This script will configure your system and install all dependencies so the app
echo is ready to run.
echo.

:: 1. Check Python
echo [Step 1/5] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please download and install Python 3.10 or 3.11 from https://www.python.org/downloads/
    echo Make sure to CHECK the box "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)
python --version

:: 2. Check Node.js & npm
echo.
echo [Step 2/5] Checking Node.js and npm...
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed or not in your system PATH!
    echo Please download and install Node.js (v18 or v20 LTS) from https://nodejs.org/
    pause
    exit /b 1
)
node --version
npm --version

:: 3. Check Ollama
echo.
echo [Step 3/5] Checking Ollama...
ollama --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Ollama is not installed or not running!
    echo Please download and install Ollama from https://ollama.com/download/windows
    echo Once installed, restart your terminal or reopen this script.
    echo.
) else (
    ollama --version
    echo Pulling AI model 'phi4-mini' (approx 2.3 GB, may take a few minutes)...
    ollama pull phi4-mini
)

:: 4. Install Python Dependencies
echo.
echo [Step 4/5] Installing Python dependencies (requirements.txt)...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install Python dependencies. Please check your internet connection.
    pause
    exit /b 1
)

:: 5. Install Frontend Dependencies
echo.
echo [Step 5/5] Installing Frontend npm packages (trace-wise-advisor-main)...
cd trace-wise-advisor-main
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install npm dependencies.
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo ==============================================================================
echo                           SETUP COMPLETE!
echo ==============================================================================
echo Everything has been installed and configured successfully.
echo.
echo To launch the entire application, simply double-click:
echo     start_app.bat   (or run .\start_app.ps1 in PowerShell)
echo.
echo The app will automatically start Ollama, FastAPI (port 8000), and Vite (port 8080).
echo ==============================================================================
echo.
pause
