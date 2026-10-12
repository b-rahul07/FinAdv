# 🚀 AI Financial Advisor (Ledgerly) — Teammate Setup Guide

Welcome to the **AI Financial Advisor** project! This repository contains the complete end-to-end multi-agent financial guidance system, including the FastAPI backend, ChromaDB vector database, FinBERT sentiment engine, and modern React frontend.

---

## 📋 System Prerequisites

Before running the setup script, ensure your laptop has the following three tools installed:

1. **Python (3.10 or 3.11 recommended):**
   * Download: [https://www.python.org/downloads/](https://www.python.org/downloads/)
   * ⚠️ **CRITICAL:** When running the installer, **check the box** that says **"Add python.exe to PATH"**.

2. **Node.js (v18 or v20 LTS):**
   * Download: [https://nodejs.org/](https://nodejs.org/)
   * Includes `npm` (Node Package Manager).

3. **Ollama (Local LLM Runtime):**
   * Download for Windows: [https://ollama.com/download/windows](https://ollama.com/download/windows)
   * Run the installer so that `ollama` is accessible from the command line.

---

## ⚡ Method 1: 1-Click Automated Setup (Recommended)

1. Clone or download this repository to your computer:
   ```bash
   git clone https://github.com/b-rahul07/FinAdv.git
   cd FinAdv
   ```
2. Double-click the file:
   👉 **`setup.bat`** (or open PowerShell in the project folder and run `.\setup.ps1`)

### What the setup script automatically does:
* ✅ Verifies Python, Node.js, and Ollama installations.
* ✅ Pulls the local AI model (`ollama pull phi4-mini`) (~2.3 GB).
* ✅ Installs all Python libraries (`pip install -r requirements.txt`).
* ✅ Installs all React frontend dependencies (`npm install` in `trace-wise-advisor-main`).
* ✅ Configures the `.env` settings and ChromaDB knowledge base.

---

## 🚀 How to Run the Application

Once setup is complete, launching the entire system takes just 1 click:

👉 Double-click **`start_app.bat`** (or run `.\start_app.ps1` in PowerShell).

This script automatically:
1. Starts the **Ollama server** in the background (`http://localhost:11434`).
2. Starts the **FastAPI backend** (`http://127.0.0.1:8000`).
3. Starts the **React frontend dev server** (`http://localhost:8080`).
4. **Automatically opens your web browser** to `http://localhost:8080`.

To stop the servers, simply close the opened command prompt windows.

---

## 🛠️ Method 2: Manual Setup (Alternative)

If you prefer to run commands manually in your terminal:

### 1. Install Backend Dependencies
```bash
# In the project root (FinAdv/)
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Pull the Ollama AI Model
```bash
ollama serve
ollama pull phi4-mini
```

### 3. Install Frontend Dependencies
```bash
cd trace-wise-advisor-main
npm install
cd ..
```

### 4. (Optional) Rebuild Knowledge Base Vectors
The ChromaDB vector store is already pre-indexed in `./data/chroma_db`. If you add new documents to `retrieval/documents/`, you can re-index anytime with:
```bash
python reindex.py
```

### 5. Launch the Servers Manually
* **Terminal 1 (Backend):**
  ```bash
  python -m uvicorn orchestrator.api:app --host 127.0.0.1 --port 8000
  ```
* **Terminal 2 (Frontend):**
  ```bash
  cd trace-wise-advisor-main
  npm run dev
  ```
* Open your browser at `http://localhost:8080`.

---

## 🌐 Default Ports & Endpoints

| Service | Address | Role |
| :--- | :--- | :--- |
| **Frontend Web App** | `http://localhost:8080` | Interactive React chat UI |
| **Backend API** | `http://127.0.0.1:8000` | REST API endpoints & Multi-Agent Pipeline |
| **API Health Check** | `http://127.0.0.1:8000/health` | Returns `{"status":"ok"}` when server is ready |
| **Local Ollama** | `http://localhost:11434` | Local LLM inference engine (`phi4-mini`) |

---

## ❓ Troubleshooting

* **"Python is not recognized as an internal or external command"**:
  Re-run the Python installer, select **Modify**, and ensure **"Add Python to environment variables"** is checked.
* **Port 8000 or 8080 already in use**:
  Simply run `start_app.bat` — it automatically kills any leftover orphan processes occupying those ports.
* **Ollama model generation feels slow**:
  `phi4-mini` runs locally on CPU. First response on cold start takes ~1-2 minutes while loading model weights into RAM. Subsequent generations are fast.
