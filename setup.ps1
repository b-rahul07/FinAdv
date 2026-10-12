# ==============================================================================
#                AI FINANCIAL ADVISOR - 1-CLICK TEAMMATE SETUP (POWERSHELL)
# ==============================================================================

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "                AI FINANCIAL ADVISOR - 1-CLICK TEAMMATE SETUP" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "This script will configure your system and install all dependencies so the app`nis ready to run.`n"

# Step 1: Check Python
Write-Host "[Step 1/5] Checking Python installation..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "  Found: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python is not installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/ (Check 'Add to PATH')."
    exit 1
}

# Step 2: Check Node.js & npm
Write-Host "`n[Step 2/5] Checking Node.js and npm..." -ForegroundColor Yellow
try {
    $nodeVer = node --version 2>&1
    $npmVer = npm --version 2>&1
    Write-Host "  Found Node: $nodeVer | npm: $npmVer" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Node.js is not installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please install Node.js (v18 or v20 LTS) from https://nodejs.org/"
    exit 1
}

# Step 3: Check Ollama
Write-Host "`n[Step 3/5] Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaVer = ollama --version 2>&1
    Write-Host "  Found: $ollamaVer" -ForegroundColor Green
    Write-Host "Pulling AI model 'phi4-mini' (approx 2.3 GB, may take a few minutes)..." -ForegroundColor Yellow
    ollama pull phi4-mini
} catch {
    Write-Host "[WARNING] Ollama is not installed or not in PATH!" -ForegroundColor DarkYellow
    Write-Host "Please install Ollama from https://ollama.com/download/windows, then run 'ollama pull phi4-mini'."
}

# Step 4: Install Python Dependencies
Write-Host "`n[Step 4/5] Installing Python dependencies (requirements.txt)..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install Python dependencies." -ForegroundColor Red
    exit 1
}

# Step 5: Install Frontend Dependencies
Write-Host "`n[Step 5/5] Installing Frontend npm packages..." -ForegroundColor Yellow
Set-Location -Path "trace-wise-advisor-main"
npm install
Set-Location -Path ".."
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install npm dependencies." -ForegroundColor Red
    exit 1
}

Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host "                           SETUP COMPLETE!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "To launch the entire application, run:"
Write-Host "    .\start_app.ps1   (or double-click start_app.bat)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Green
