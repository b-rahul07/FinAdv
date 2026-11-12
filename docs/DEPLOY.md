# Hosting FinAdvisor (all free)

```
Vercel: the website (web/)  ──HTTPS──▶  Laptop via Tailscale Funnel: FastAPI + Ollama  ──▶  Supabase: Postgres + Auth
https://finadvisor-india.vercel.app      https://finadvisor.tail584bb1.ts.net              project ciryesycfcxhzdblsyhs
```

Why this setup (2026-11-08): Oracle's Always Free compute limits on our account are 0, Azure for Students needs MFA
that the college account can't register, and Hugging Face now charges for Docker Spaces. The advisor and the model
run on the laptop and are online **only while the laptop runs FinAdvisor's public link**; the website on Vercel is
always up and says it can't reach the server otherwise.

## 1. Going online
VS Code → Run and Debug → **FinAdvisor online (public link)** → ▶. It builds `web/`, starts the API with
`SERVE_WEB=true` (the API also serves the built site), `APP_ENV=prod` (the any-email test sign-in is refused) and
`CORS_ORIGINS` set to the Vercel addresses, then runs `tailscale funnel 8000`. The red ■ takes it offline.

First time only: the "Public link" terminal prints a link to enable Funnel for the tailnet; open it, approve, run again.
Tailscale's relays see only encrypted traffic; TLS ends on the laptop.

## 2. Updating
- **Website** (after changing `web/`): `cd web && npx vercel deploy --prod`. Vercel project `finadvisor` (account
  b-rahul07); its production variables are the four public `VITE_*` values with
  `VITE_API_URL=https://finadvisor.tail584bb1.ts.net`. `web/vercel.json` sends every route to `index.html`.
- **API** (after changing `finadvisor/`): stop and start the public link in VS Code.

## 3. Routine jobs (run on the laptop)
| Command | How often | What it does |
|---|---|---|
| `python -m finadvisor.market.jobs` | daily, after 11 pm IST | latest NSE/BSE closes and AMFI NAVs for held or watched instruments |
| `python -m finadvisor.market.jobs masters` | weekly | refresh the stock and fund lists |
| `python -m finadvisor.market.fundfinder` | weekly (~10 min) | fund lists, expense ratios and returns for the fund finder cards; cards say "older than usual" after 10 days |

Supabase pauses a free project after 7 days without activity; the daily job counts as activity.

**Without the laptop.** `.github/workflows/prices.yml` runs the daily job on GitHub's servers at 7:30 pm and
11:30 pm IST on weekdays. To switch it on:
1. GitHub → the repository → Settings → Secrets and variables → Actions → *New repository secret*: name
   `DATABASE_URL`, value the Supabase session-pooler connection string (the same one the API uses).
2. The workflow file must be on the repository's default branch; GitHub runs schedules only from there.
3. Actions → *Daily prices* → *Run workflow* runs it once by hand; the log prints what was stored.
Not yet verified: whether NSE's archive answers GitHub's servers (it refuses some data-centre addresses). If the
log shows `listed_error`, the laptop job remains the source for shares and the workflow still updates fund NAVs.
`.github/workflows/ci.yml` runs the tests, the type-check and the web build on every push.

## 4. Supabase (database and sign-in)
- `supabase/schema.sql` is applied (RLS on, no policies, so the public Data API exposes nothing). Regenerate it with
  `python scripts/gen_postgres_schema.py`; never edit it by hand.
- The API connects through the **session pooler** `aws-1-eu-west-3.pooler.supabase.com:5432` (the direct `db.*`
  host is IPv6-only). No service-role key is needed: deleting an account removes the sign-in via SQL.
- Authentication → URL Configuration: Site URL `https://finadvisor-india.vercel.app`; Redirect URLs
  `https://finadvisor-india.vercel.app/**` and `http://localhost:5173/**`.

### Google sign-in
1. <https://console.cloud.google.com> → project "FinAdvisor" → **Google Auth Platform**. While the app is in
   *Testing*, only the Gmail addresses under **Test users** can sign in.
2. The web client's authorised JavaScript origins are `http://localhost:5173` and
   `https://finadvisor-india.vercel.app`; the redirect URI is `https://ciryesycfcxhzdblsyhs.supabase.co/auth/v1/callback`.
3. The client ID and secret live in Supabase → Authentication → Sign In / Providers → Google (never in the repo).
4. `VITE_GOOGLE_AUTH=true` shows the button (in `web/.env.local` and the Vercel variables).

## 5. Moving to an always-on Linux server later
Any Ubuntu server with 2+ cores and 8+ GB of memory works (the model needs about 3 GB):
```bash
sudo apt update && sudo apt install -y python3-venv git caddy
curl -fsSL https://ollama.com/install.sh | sh && ollama pull qwen2.5:3b
git clone https://github.com/b-rahul07/FinAdv.git && cd FinAdv
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[postgres,cas]"
```
Copy `.env` from the laptop (it holds the database password; never commit it) and set `APP_ENV=prod`,
`AUTH_MODE=supabase`, `RETRIEVAL=keyword`, `NEWS=off` and `CORS_ORIGINS=https://finadvisor-india.vercel.app`.
Run `uvicorn finadvisor.api.app:app --host 127.0.0.1 --port 8000 --workers 1` as a systemd service (one worker on
purpose: the model is the bottleneck and live answers are per process), put Caddy in front
(`<your-domain> { reverse_proxy 127.0.0.1:8000 }` gets an HTTPS certificate by itself), schedule the jobs in section 3
with cron, and point `VITE_API_URL` on Vercel at the new address.

## 6. Experiments (Colab / Kaggle)
```bash
pip install -e .          # same finadvisor package as the website
python -m experiments.run experiments/configs/smoke.yaml
```
Results append to `results/<run>/*.jsonl` and resume after a disconnect. Inputs must be synthetic.

## Limits to remember
- Supabase free: 500 MB database; prices are stored only for instruments someone holds or watches.
- On a laptop CPU a plan answer's text appears in under a second; the model's short explanation takes 4–10 s.
- NSE/BSE archives need a browser user agent; requests are spaced at least 1 s apart and each file is fetched once.
