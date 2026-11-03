# FinAdvisor

A free personal-finance website for young Indian earners: an **advisor chat** that only gives suitable advice, and a
**money tracker** for stocks, mutual funds, deposits, gold and loans. It is also the system evaluated in our research
paper.

Advice goes through a fixed pipeline: **capacity for loss → willingness (Grable & Lytton) → suitability → product gate →
plan → audit**. Every rupee amount comes from tested code, never from the language model, and FinAdvisor never names
individual stocks. It is not a SEBI-registered adviser; it gives education and planning only.

## Repository layout

| Path | What it is |
|---|---|
| `finadvisor/advisor/` | Pipeline: capacity, willingness, gate, planner, metamorphic auditor, router, answer composer |
| `finadvisor/calc/` | Calculators: goals, loans, deposits, XIRR, tax |
| `finadvisor/api/` | FastAPI backend (chat streaming, profile, holdings, library) |
| `finadvisor/db/` | SQLAlchemy models (SQLite locally, Supabase Postgres in production) |
| `finadvisor/market/` | NSE/BSE/AMFI prices, corporate actions, news headlines with FinBERT mood |
| `finadvisor/portfolio/` | Holdings, FIFO lots, XIRR, value series, other assets |
| `finadvisor/retrieval/` | Document library (Indian product and regulation guides) and search |
| `finadvisor/llm/` | Model clients (Ollama, test fake) |
| `configs/` | Versioned rules, product shelf, assumptions, tax, questionnaire, pipeline flags |
| `web/` | React + TypeScript frontend (Vite, TanStack Router/Query, Tailwind) |
| `experiments/` | Headless research runner and the advice evaluation |
| `scripts/` | Tools: demo/test accounts, search index, schema, data validation, research export |
| `tests/` | Backend tests (pytest) |
| `supabase/schema.sql` | Production database schema (generated) |
| `docs/` | `documentation.md` (changelog and decisions), `DEPLOY.md` (hosting) |

## Run it locally

**Step-by-step guide for running it on your own computer: [docs/SETUP.md](docs/SETUP.md)** (no keys needed).

Short version, for people who have done this before. Needs Python 3.11+, Node 20+ and [Ollama](https://ollama.com) with
the model in `configs/models.yaml` (`ollama pull qwen2.5:3b`).

```bash
# backend
pip install -e ".[rag,news,cas]"
cp .env.example .env                     # AUTH_MODE=dev for local sign-in
python -m finadvisor.market.jobs masters # instrument lists (first run)
python scripts/build_index.py            # document search index
python -m uvicorn finadvisor.api.app:app --port 8000

# frontend (another terminal)
cd web
npm install
cp .env.example .env.local
npm run dev                              # http://localhost:5173
```

Optional example accounts (local database only, marked as example data):
`python scripts/seed_demo.py` (demo@finadvisor.example) and `python scripts/seed_test_user.py`
(arjun@finadvisor.example, investing since 2021).

## Tests and research

```bash
python -m pytest                                    # backend
cd web && npm test && npx tsc -p tsconfig.json --noEmit
python -m experiments.run experiments/configs/smoke.yaml
python -m experiments.eval_advice experiments/data/eval_personas.jsonl results/eval/run.jsonl
```

Experiment inputs must be synthetic; real users' data never goes to a third-party model.

## Deployment

Frontend on Cloudflare Pages, API and model on a free VM, database and sign-in on Supabase. See `docs/DEPLOY.md`.
