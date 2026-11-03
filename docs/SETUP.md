# Run FinAdvisor on your own computer

This guide takes you from nothing to the FinAdvisor website running at **http://localhost:5173** on your laptop.
It takes about 30–45 minutes the first time, mostly downloads. Everything is free.

Three things run on your computer:

| What | Where | What it does |
|---|---|---|
| **Ollama** (AI model) | runs in the background | writes the short explanations and answers general questions |
| **API** (Python) | http://localhost:8000 | the advisor, calculations, prices, your data |
| **Website** (React) | http://localhost:5173 | what you open in the browser |

Your data stays on your computer, in `data/finadvisor.db`.

Commands below are for **Windows (PowerShell)**. Mac and Linux differences are noted where they matter.

---

## 1. Install the tools (once)

| Tool | Get it | Check it worked |
|---|---|---|
| Git | https://git-scm.com/downloads | `git --version` |
| Python 3.11, 3.12 or 3.13 | https://www.python.org/downloads/ (Windows: tick **"Add python.exe to PATH"**) | `python --version` |
| Node.js 20 or newer (LTS) | https://nodejs.org | `node --version` |
| Ollama | https://ollama.com/download | `ollama --version` |

Open a **new** terminal after installing, so it sees the new tools.

## 2. Get the code

```powershell
git clone https://github.com/b-rahul07/FinAdv.git
cd FinAdv
```

## 3. Set up the API (Python)

```powershell
python -m venv .venv
.venv\Scripts\activate                # Mac/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[rag,news,cas]"      # 5-10 minutes; downloads PyTorch and the search models
copy .env.example .env                # Mac/Linux: cp .env.example .env
```

You should now see `(.venv)` at the start of your terminal line. The `.env` file works as it is: local sign-in, local
database, no keys needed.

> **Short on time or disk space?** Use `pip install -e ".[cas]"` instead (about 1 minute), then open `.env` and set
> `RETRIEVAL=keyword` and `NEWS=off`. Everything works; document search is simpler and market headlines are hidden.

Then download the stock and mutual fund lists, and build the document search index (skip the second line if you took
the short route):

```powershell
python -m finadvisor.market.jobs masters      # about 10 seconds: 5,900+ stocks and 14,000+ funds
python scripts/build_index.py                 # about 1 minute the first time
```

## 4. Download the AI model

Ollama starts by itself after installing (look for the llama icon in the system tray / menu bar). Then:

```powershell
ollama pull qwen2.5:3b                        # about 1.9 GB
```

## 5. Start the API

In the same terminal (with `(.venv)` showing):

```powershell
python -m uvicorn finadvisor.api.app:app --port 8000
```

Leave this terminal open. It's working when it prints `Application startup complete`.

## 6. Start the website

Open a **second** terminal:

```powershell
cd FinAdv\web
npm install                                   # about 30 seconds
copy .env.example .env.local                  # Mac/Linux: cp .env.example .env.local
npm run dev
```

Open **http://localhost:5173**, click **Get started free**, and sign in with **any email** (no password in local mode).

To try the advisor, open **Advisor** and ask "Make me a money plan". It first asks you to fill in a short profile and
13 risk questions; after that, plans appear in a second or two.

## 7. Example accounts (optional)

To see what a regular user's screens look like, with real prices:

```powershell
python scripts/seed_demo.py                   # demo@finadvisor.example: a few holdings from 2025
python -m finadvisor.market.jobs              # loads recent prices for those holdings
python scripts/seed_test_user.py              # arjun@finadvisor.example: investing since 2021 (30-40 min of downloads)
```

Sign in with those emails. Both accounts are fictional and marked "Example data" on every screen.

---

## Keys and tokens

**You don't need any key to run FinAdvisor locally.** The steps above use local sign-in and a local database.

Here is every key and token the project uses, so you know what each is for:

| Name | Used for | Do you need it? | Secret? |
|---|---|---|---|
| `SUPABASE_URL`, `VITE_SUPABASE_URL` | Real email and Google sign-in (optional, see below) | Only for real sign-in | No, public |
| `SUPABASE_ANON_KEY`, `VITE_SUPABASE_ANON_KEY` | Same | Only for real sign-in | No. Supabase makes this key public by design; the website sends it to every browser, and the database rules stop it from reading any data. |
| `DATABASE_URL` (production) | The live website's database | **No.** Leave it empty: you use your own local database. | **Yes.** It holds the database password and gives access to every real user's data. It is never shared or committed. |
| `SUPABASE_SERVICE_KEY` | Lets "delete account" remove a Supabase sign-in on the live server | No | **Yes**, server only |
| Google OAuth client ID and secret | Google sign-in; stored inside the Supabase dashboard | No, Supabase handles Google for you | The secret is |
| Oracle Cloud API key | Creating the hosting server | No | **Yes** |
| `VITE_API_URL` | Where the website finds the API | Already set to `http://localhost:8000` | No |
| `VITE_GOOGLE_AUTH` | Shows the "Continue with Google" button | Only for real sign-in | No |

Never paste a secret into a chat, an issue or a commit. `.env` and `web/.env.local` are ignored by git, so they stay on
your computer.

### Real sign-in with email or Google (optional)

To sign in with a real account instead of the local sign-in, use our Supabase project's two public values. Your
FinAdvisor data still stays in your local database; only the sign-in goes through Supabase. Your account is added to
the project's sign-in list.

In `.env` (then restart the API):

```ini
AUTH_MODE=supabase
SUPABASE_URL=https://ciryesycfcxhzdblsyhs.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNpcnllc3ljZmN4aHpkYmxzeWhzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM0NjU5NzQsImV4cCI6MjEwOTA0MTk3NH0.0XH4GdEcLq-R_k-p5U8vAKQqa91kFfGbuvHMZmUQrmo
```

In `web/.env.local` (then restart `npm run dev`):

```ini
VITE_SUPABASE_URL=https://ciryesycfcxhzdblsyhs.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNpcnllc3ljZmN4aHpkYmxzeWhzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM0NjU5NzQsImV4cCI6MjEwOTA0MTk3NH0.0XH4GdEcLq-R_k-p5U8vAKQqa91kFfGbuvHMZmUQrmo
VITE_GOOGLE_AUTH=true
```

The website must run at http://localhost:5173 for Google sign-in and email confirmation links to come back to it.
To go back to local sign-in, set `AUTH_MODE=dev` and empty the two `VITE_SUPABASE_*` values.

---

## Next time

You only need the last commands. Terminal 1:

```powershell
cd FinAdv
.venv\Scripts\activate
python -m uvicorn finadvisor.api.app:app --port 8000
```

Terminal 2:

```powershell
cd FinAdv\web
npm run dev
```

To get the latest version first: `git pull`, then `pip install -e ".[rag,news,cas]"` and `npm install` again.

## If something goes wrong

| What you see | Fix |
|---|---|
| `python` or `node` is not recognised | Reinstall with "Add to PATH" ticked, then open a new terminal. |
| `running scripts is disabled` when activating | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use Command Prompt and `.venv\Scripts\activate.bat`. |
| "FinAdvisor's language model isn't reachable" | Start Ollama (open the app), check `ollama list` shows `qwen2.5:3b`. Plans still work without it. |
| The website says it can't reach the server | The API terminal must be running on port 8000. |
| `address already in use` / port 8000 or 5173 busy | Close the old terminal running it, or restart your computer. |
| Stock or fund search finds nothing | Run `python -m finadvisor.market.jobs masters` (needs internet). |
| Prices missing or old | Run `python -m finadvisor.market.jobs`. NSE publishes prices after market close on trading days. |
| Google sign-in fails | Use http://localhost:5173 exactly (not 127.0.0.1 or another port). |

FinAdvisor is for education and planning only. It is not a SEBI-registered investment adviser.
