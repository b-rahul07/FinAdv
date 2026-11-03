# FinAdvisor — documentation and changelog

Living document. Newest entries first in the changelog. Decisions record *why*, so they can be revisited.

## Architecture

```
React + TS SPA (web/)  ── Cloudflare Pages (planned)
  │  supabase-js for sign-in only (email + Google); dev sign-in locally
  │  HTTPS + bearer token; answers stream as Server-Sent Events over POST
  ▼
FastAPI (finadvisor/api)  ── Oracle Always Free Arm VM (planned)
  ├─ finadvisor/advisor   one pipeline, used by the API and experiments/run.py
  ├─ finadvisor/calc      XIRR, goal SIP, EMI, FD/RD accrual, tax (unit-tested)
  ├─ finadvisor/llm       Ollama client (self-hosted), fake client for tests
  └─ Ollama               qwen2.5:3b, localhost only
  ▼
Database: SQLite locally (data/finadvisor.db, git-ignored) · Supabase Postgres in production
```

**Every number comes from Python.** The dashboard, holdings and advisor call the same calculators, so values
reconcile by construction. The frontend only formats (`web/src/lib/format.ts`).

**The frontend talks only to the API for data**, never directly to Supabase tables. All tables have row-level
security enabled with no policies (`supabase/schema.sql`), so the public Data API exposes nothing even if a key leaks.

### Advisor pipeline (report Ch. 4, `finadvisor/advisor/`)
| Stage | Module | LLM? |
|---|---|---|
| Router: Learn / Plan / Check / chat | `router.py` | no (regex, biased to the pipeline) |
| Profile extraction → card → user confirms | `extract.py`, `/api/profile` | yes (proposal only) |
| Capacity engine (Algorithm 1) | `capacity.py` | no |
| Willingness: Grable & Lytton 13 items + experience | `willingness.py` | no |
| Suitability = min(capacity, willingness); gate (Algorithm 2) | `gate.py` | no |
| Pressure fencing (Algorithm 3): six types, conflict line | `pressure.py` | no |
| Planner chooses product mixes; calculators build the plan | `planner.py`, `plan.py` | chooses only |
| Metamorphic auditor MR1–MR6, ≤2 repairs, safe fallback (Alg. 4) | `auditor.py` | twin runs |
| Explanation, sentence-level number guard | `pipeline.py`, `numbers.py` | yes (prose only) |

Check route: gate verdict → "Not yet" card with what would need to change (`check.py`).
What-if sliders: deterministic re-run with the safe mix, instant, labelled illustrative (`cards.what_if`).

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-10-31 | New `web/` app (Vite SPA, TanStack Router/Query, Tailwind 4, shadcn/Radix, Recharts 3) instead of the Lovable TanStack Start app | SSR adds nothing behind sign-in and complicates Cloudflare Pages; old app kept untouched |
| 2026-10-31 | One installable package `finadvisor/` (pyproject) with configs in `configs/` | Colab/Kaggle install the same code with `pip install -e .`; experiments and website share it |
| 2026-10-31 | SQLAlchemy models, SQLite in dev/tests, Postgres in prod; schema SQL generated from models | No Docker locally; one source of truth for tables; RLS added in generated SQL |
| 2026-10-31 | Dev sign-in (HS256 local tokens) when Supabase is not configured; refused when `APP_ENV=prod` | The Supabase project was unreachable (paused); lets the whole app run locally |
| 2026-10-31 | Grable & Lytton items/key from Kuzniak et al. 2015 App. A; adapted to India (₹50 per $1 keeps ratios; Indian product names); items 9+10 summed (13–47); bands ≤22 Low, 23–28 Medium, ≥29 High (Rutgers grid); no experience caps willingness at Medium | User-provided source; CC BY-NC 4.0 with attribution; every change logged per item in `configs/willingness/gl13_in_v1.yaml` |
| 2026-10-31 | Pressure does not move the measured willingness level (`pressure.willingness_adjustment: none`) | Brief: the plan stays put unless *facts* change; report Alg. 3 leaves `adjust_willingness` open. Retaking the questionnaire is the way to change willingness |
| 2026-10-31 | rho = share of investing money in products rated Moderately High or above (report §3.1) | As defined in the report |
| 2026-10-31 | Planner output = per-bucket product weights only (`"sdebt:6,liq:4"`), short product codes | Output tokens dominate CPU latency (340 → ~75 tokens); LLM never writes amounts |
| 2026-10-31 | Website model qwen2.5:3b (Q4_K_M, Ollama) | Measured on the dev laptop (CPU only): ~10–22 s per planner call vs ~30–45 s for phi4-mini; similar choice quality. Licence: Qwen Research License (non-commercial), fine for this project |
| 2026-10-31 | Auditor `early_exit: true` and `time_budget_s: 240` on the website; experiments set `early_exit: false`, no budget | CPU hosting cannot afford 3 attempts × 8 calls; on timeout the deterministic safe plan is shown (never an unaudited plan). Recorded in every result |
| 2026-10-31 | Relations evaluated in order MR6, MR1–MR5 | MR6 fails most often with small models, so failing attempts are found with fewest calls |
| 2026-10-31 | Savings account not plannable (emergency-fund vehicle); EPF/VPF limited to retirement goals | Kept small models from filling plans with savings accounts |
| 2026-10-31 | Priority order: health cover → term cover → card dues → costly loans (highest rate first) → emergency fund; a cleared loan's EMI is added back to the surplus | Deterministic, explainable; report does not fix an order |
| 2026-10-31 | Categorical palette = dataviz reference palette, validated on our surfaces (light #ffffff, dark #171b23); light mode needs labels/legend (3 slots < 3:1) | Colour-blind-safe in both themes; 8 slots = 8 asset classes |

## Free resources in use
| Need | Choice | Limits |
|---|---|---|
| Database/auth | Supabase free (planned) | 500 MB DB, 50k MAU, pauses after 7 days idle — the daily data job will keep it awake |
| LLM hosting | Ollama on Oracle Always Free Arm (planned; user is signing up) | 2 OCPU / 12 GB; expect ≥ the laptop timings below |
| Frontend | Cloudflare Pages (planned) | free static hosting, commercial use allowed |
| Fonts | Manrope via @fontsource (self-hosted, no Google request) | — |

## Measured latency (dev laptop, CPU only, qwen2.5:3b)
- One planner call: 9–22 s (≈600 prompt tokens, ≈75 output tokens).
- Plan answer end to end in the browser: 69 s (audit fell back to the safe plan, see open question 1).
- Pressure turn on the same profile: 18 s (identical prompts are cached in-process).
- Learn answer (Chroma + cross-encoder + streaming): 85 s on first use (models load), faster afterwards.

## Methodology decisions (2026-10-31, delegated by the team)
1. **Capacity EMI score (rules-v2).** The report's s_D = clip((0.40 − D)/0.40) equals 1 only with *no* EMIs, so a
   person whose EMIs pass SEBI's 40 % check could never reach High capacity, unlike every other component, which
   reaches 1 exactly when its SEBI check passes. rules-v2 uses s_D = min(1, 0.40 / D): 1 while the check passes,
   then proportional (D = 0.8 → 0.5 → Low). Design rule: **High capacity ⇔ all five SEBI checks pass.** rules-v1
   (report formula) is kept for the sensitivity analysis. *Update the paper's Eq. for s_D and Algorithm 1.*
2. **MR6 "same plan" (pipeline-v2).** Strict equality of weights treated a 6:4 vs 5:5 split as a different plan, so
   small models failed MR6 on nearly every input. pipeline-v2 defines the same plan as the same products in every
   bucket with each share within 0.10 (one weight part). Changing products still fails. Raw mix signatures are logged
   in every result, so strict MR6 (tolerance 0) can be recomputed for the paper; report both.
3. **Run-to-run variability.** llama.cpp on CPU is not bit-reproducible at temperature 0, even with a fixed seed.
   Website: identical prompts are memoised within the process, so a repeated question gets the same answer.
   Experiments: `replicates: N` in a run config disables the memo and repeats each profile N times; report the
   agreement rate across replicates next to every metric. State this limitation in the paper.

## Supabase (project ciryesycfcxhzdblsyhs, eu-west-3)
- Connected through the **session pooler** `aws-1-eu-west-3.pooler.supabase.com:5432` (the direct `db.*` host is IPv6-only).
- `supabase/schema.sql` applied; RLS on for all 28 tables, no policies; the anon key reads nothing from the Data API.
- Auth: email on, confirmation required, Google off. User tokens are ES256, verified locally from the project's JWKS.
- Postgres found two column-length bugs SQLite hid (`instruments.option` up to 83 chars; `prices_daily.source`).
  Both widened and altered live; a before-flush length check now enforces VARCHAR limits in SQLite too.
- Without the service-role key, deleting an account removes all FinAdvisor data but not the Supabase sign-in itself.

## Changelog

### 2026-11-03 — Setup guide for friends; fresh-clone fixes
`docs/SETUP.md`: step-by-step local setup (Windows first, Mac/Linux notes), optional example accounts, every key and
token the project uses and whether it is needed or secret, optional real sign-in with the project's public Supabase
URL and anon key (data stays local), troubleshooting. The production `DATABASE_URL` (database password), service key,
Google client secret and Oracle key are deliberately not in it: they give access to real users' data or accounts.
Tested by cloning the GitHub repo into an empty folder and following the guide, which found four bugs that only a
fresh machine hits (all fixed): an empty `DATABASE_URL=` with a trailing comment in `.env.example` was read as the
URL (comments moved to their own lines; settings now ignore empty values); Windows has no time-zone database, so IST
failed (`tzdata` dependency); `data/` doesn't exist in a fresh clone, so the first data job couldn't open the database
(`make_engine` creates it); `python-multipart` (CAS upload form) was missing from the dependencies.

### 2026-11-02 — Repository cleanup
Removed the earlier prototype (team request): `orchestrator/`, `preference/`, `persistence/`, `recommend_audit/`,
`sentiment/` (replaced by `finadvisor/market/news.py`), the old `trace-wise-advisor-main/` frontend, prototype
launchers, `requirements.txt`, `config.py`, old guides and schemas, and `data/advisor_history.db`. All remain in git
history. The prototype's retrieval moved into the package as `finadvisor/retrieval/` (documents + `chroma.py`);
`reindex.py` became `scripts/build_index.py`. `data/` (dev database, price cache, search index) is no longer tracked.
This file moved to `docs/`; new `README.md`; `pyproject.toml` gained `news`, `oracle` and `all` extras. The report
folder stays local and untracked.

### 2026-11-02 — Chat opens at once, answers in ~1 s, question-first replies (user report)
**Report:** clicking a prompt or sending a question didn't open the chat; answers lagged; replies were profile-heavy,
generic and didn't answer the question.
- **Chat didn't open:** `/chat` and `/chat/$id` are separate routes, so creating the chat remounted the page and the
  in-flight answer lived in the unmounted one (the start screen came back until the answer was saved). Live answers
  now live in a module store keyed by chat id (`useChat.ts`). Question visible in 0.2–0.5 s.
- **Lag (measured: 116 s per plan; 6 planner calls, MR6 failed three times, fell back to the standard mix anyway).**
  Team decision: `planner.mode: standard` on the website (tested standard mix per suitability level; the auditor still
  checks MR1–MR5 against twins, MR6 holds by construction); experiments set `planner: {mode: model}` (smoke.yaml).
  Also: extraction runs only when a message can state a fact (an amount, dependants, experience, card dues), not for
  every question mentioning "savings" or "goals"; news refresh runs in a separate process (FinBERT/PyTorch inside the
  API stalled the first answers for 25–50 s); Ollama `keep_alive: 30m`. Result: answer on screen in ~1–3 s from a cold
  start; the short model recap streams in after.
- **Question-first replies** (`advisor/compose.py`, template `compose-v1`): direct answer with the person's numbers
  per intent (emergency fund, retirement, mutual funds, how much, insurance, debt, plan), "What you already have" from
  real holdings (`portfolio/shelf_map.py`; flags the share rated above the person's risk level), "What to do" (numbered
  steps with amounts), "Why this suits you" (≤3 reasons), follow-up buttons, and the model recap under "In plain words".
  Full plan, goals, health check, what-if and audit sit under a "See the …" disclosure (`card.show = main | details`).
- Fixed: "How much should I save for retirement?" said "no retirement goal" when the goal existed but got ₹0 this month.
- 173 backend tests; `tsc` clean; browser flow re-run.
**Known:** the model recap still sometimes sequences things that happen together ("then consider adding gold" when
gold is in the mix from month 1); it is labelled as a recap and carries no numbers.

### 2026-11-01 — Long-history test account
`scripts/seed_test_user.py` seeds "Arjun (test account)" (`arjun@finadvisor.example`, dev sign-in, marked as example
data): Nifty 50 index SIP since Apr 2021 with step-ups, flexi-cap SIP with a 3-month pause, March ELSS top-ups,
small-cap bought on a tip and half sold after the fall, liquid fund partly redeemed, and from Jan 2024 shares (Reliance
and HDFC Bank held through their 1:1 bonuses, TCS and Asian Paints sold), Gold BeES, FD/RD/EPF/PPF/jewellery, a car loan,
term and health cover, and four dated profile versions with health snapshots. All trade prices are real closes/NAVs.
Run it with `DATABASE_URL` pointing at the dev SQLite file (the root `.env` points at production). Stock history
starts in Jan 2024 because NSE's UDiFF bhavcopy (our stock source) starts then; older stocks would need the legacy format.
Verified: both bonuses derived from prices (30 and 40 shares), realised gains on the fund sales, value chart from 2021
with the Nifty comparison. Found and fixed: signed amounts wrapped the sign onto its own line (`.num` is now nowrap).
**Gap found:** sold stocks (TCS, Asian Paints) and their realised gains/losses appear on no screen.

### 2026-11-01 — Full test pass and advice evaluation
**Advice evaluation** (`experiments/eval_advice.py`, `experiments/eval_summary.py`, personas in
`experiments/data/eval_personas.jsonl`): 12 synthetic personas × 30 chat turns through `Advisor.turn` with qwen2.5:3b,
Chroma retrieval and the news desk. Each persona carries hand-worked expected capacity, rules, suitability and first
step (oracle from `configs/rules/v2.yaml`); each turn its expected route and advice severity. Automatic checks: engine,
route, gate, step order, numbers, security names, framing, promises, evidence. Then every answer was read and graded.
Results in `results/eval/advice-2026-11-01*.jsonl` (gitignored).

| | round 1 | round 2 (fixes below) |
|---|---|---|
| turns passing every automatic check | 26/30 | 29/30 (one Learn answer without inline citations) |
| engine / gate / order / numbers / names | 30/30 | 30/30 |
| plan explanations materially wrong (graded by hand) | ~11/18 | 6/17 (+ product guard added after) |
| plan audit: pass / repaired / fallback | 8 / 1 / 9 | 7 / 3 / 7 |
| median latency plan / check / learn | 65 s / 0.6 s / 31 s | 54 s / 0.5 s / 18 s |

**Bugs found and fixed**
- Extraction invented facts (age 25, expenses ₹6,000, "intermediate") from "should I buy a phone on EMI of 6000",
  sending people to a profile card instead of an answer. `extract.py` now keeps a field only if the message talks
  about it and states its value; "never invested" forces experience none; insurance is never a goal; the EMI being asked
  about is never an existing debt. Wrong conversions (10 lakh read as 1 lakh) are dropped. `tests/test_extract_grounding.py`.
- Wish wording said "no goal that far off" to a person with 8- and 30-year goals; now uses goal horizons.
- Plan summary said EPF is held back for risk; it is for salaried employees only.
- Router sent "Is an index fund right for me?" / "Does NPS suit me?" to Plan; now Check.
- Keyword retrieval found nothing for "What is ELSS?" (stop-words counted toward the 2-word minimum); now ignores
  stop-words, needs one content word for one-word questions, ranks title matches first.
- Learn citations [3]/[4] had no matching chip (chunks of one document); now one numbered source per document.
- Library guides showed rates without a date; the viewer now shows "Guide last updated …" and a rates-change warning.
- Evidence documents ignored the advice; retrieval now adds the topics of triggered rules (emergency fund, cover, …).
- "Which mutual funds" got no direct answer; the summary now lists the fund categories in the plan.
- "We'll revisit the small-cap funds" passed the promise filter; filter extended.
- `documents_in_prompt` off: with passages in the prompt the explainer named a "flexi-sweep FD" not in the plan.
- Product guard: explanation sentences naming a shelf product outside the plan and the request are dropped (the
  model told a Low-capacity person to "start investing in a balanced advantage or flexi-cap fund"). Re-run live: dropped.
- "based on the PLAN FACTS" (prompt jargon) is rewritten to "based on your plan".

**Other checks:** 162 backend tests; web tests, `tsc`, production build (main chunk 749 kB, code-splitting pending).
Browser (Edge, Playwright): every page in light, dark and 390 px; axe finds no serious/critical violations; no console
errors; no horizontal scroll; focus rings on every focused control; Escape closes dialogs; evidence card persists after
reload. Daily market job OK. 52-week check vs NSE (30 Oct): 84.0% both ends within 0.5%, 91.1% within 2% (residual:
undetected splits on a few small caps, e.g. AVROIND 10×). Research export: no emails or names, opt-in only.
`experiments/run.py` smoke on pipeline-v4: 2 pass, 1 fallback, all six relations evaluated.

**Decision (team, 2026-11-01): number-free explanation.** Round 2 showed the explainer misattributing approved numbers
("covers 51% of the ₹4,08,93,494 needed" where 51% is of the monthly need) and skipping key steps; the number guard
checks provenance, not meaning. The team chose number-free prose over fixed narration or a larger model.
- `configs/pipeline/default.yaml` `explainer.numbers: none` (stored with every result; `approved` restores the
  report's original guard). Template `explain_words-v1` gets the plan steps in words (`pipeline.step_words`), with no
  amounts anywhere in its prompt; any sentence with a number, ₹ or % is dropped; amounts appear only on the plan card.
- Product guard tightened: a requested product may be named only if the plan uses it (round 3: "after that, we'll
  start investing in mid- and small-cap funds"). Leading "Then, / After that," is tidied after a dropped sentence.

| plan explanations, graded by hand | R1 | R2 | R3 (number-free) | R4 (+ steps in words) |
|---|---|---|---|---|
| accurate | ~7/18 | 9/17 | ~7/17 | 13/17 |
| minor slip or fragment | – | 2 | ~7 | 2 |
| materially wrong | ~11 | 6 | 3 | 2 (gold "added later"; 60 % index mix called "safer funds and gold") |
| median plan latency | 65 s | 54 s | 55 s | 36 s |

R4: 28/30 turns pass every automatic check (two Learn answers without inline citations; the source chips still show).
165 backend tests; browser regression clean.

**Still open (team):** P12-type profiles (parent, under-insured) get an all-fixed-income plan until term cover is bought;
a what-if for "after buying cover" would show what changes. The `low` safe mix puts ~31 % of 5-year goal money in liquid
funds (shelf v2 candidate). Audit falls back to the safe plan for 6–9 of 17 plans with qwen2.5:3b.

### 2026-11-01 — Answer the request first; "What I looked at" (pipeline-v4)
**Request (team):** when someone asks "which stocks should I buy", answer what they asked, then advise ("here is what you
want, but I strongly advise you focus on this"), instead of replacing the request with our plan. Also show the
documents retrieved and headlines read, as the prototype did.

**Changed**
- `advisor/wishes.py` (template `wish-v1@<hash>`, recorded in `templates.wish`): every Plan/Check answer about a
  specific product opens with a deterministic answer to the request (stocks: why no stock names, how index funds fit,
  how to pick shares sensibly, tracking in Holdings; F&O: the SEBI loss fact; crypto: unregulated), then
  "**My advice:**" graded by severity: *strong* (R1–R5 or Low capacity), *recommend* (R6 or a risk-level block),
  *suggest* (nothing blocks). Peer/rally/finfluencer pressure adds a fixed "recent gains don't predict" line.
  Still never names a security. The check card's Algorithm 3 `conflict` line is still built and stored, but no longer
  shown in the UI or the reply.
- Check answers no longer call the explainer: the 3B model repeated the advice and once promised "we can explore
  individual stocks" later. Plan answers drop sentences that promise future suitability (`PROMISE_WORDS`).
- Evidence card (`type: "evidence"`, stored in `advice_runs.record.evidence`): up to 3 library passages (one per
  document) on the products in the answer, readable in full via `GET /api/library/{file}`, and up to 6 market headlines
  with FinBERT mood. `configs/pipeline/default.yaml` → pipeline-v4 with an `evidence` block (`documents`,
  `documents_in_prompt`, `headlines`; 0 switches each off). Passages may inform the explainer's wording, but their
  numbers are not approved, so the number guard drops them. Headlines never reach the planner or the explainer.
- `market/news.py` NewsDesk: ET Markets + Moneycontrol RSS (the prototype's feeds), FinBERT (`ProsusAI/finbert`,
  the prototype's model), cached in `data/news/latest.json`, and refreshed in a background thread when older than 3 h,
  so answers never wait for it. No user data is sent (feeds are fetched without queries). `NEWS=off` disables it.

**Verified:** 148 backend tests (new `tests/test_wishes.py`: framing per severity, evidence card, numbers from passages
dropped, promise filter, Check has no model prose, news cache/topic filter); `tsc` clean; web tests pass. Live, against
the dev API with qwen2.5:3b: "what stocks should I invest in" for a stretched profile gives answer → strong advice →
Not-yet + health + evidence cards (2 documents, 6 scored headlines, document opens). Live feed fetch + FinBERT: 26
headlines in 22 s on first load.
**Not verified:** the evidence card has not been checked in a browser yet (both themes, keyboard), and the Plan route has
not been run live with headlines (it passed the tests). With keyword retrieval, the documents found are sometimes only
loosely related (e.g. a fixed-deposits guide for a stocks question); Chroma retrieval (port 8000) should match better.

### 2026-11-01 — Chat smoothness and answer quality (from a user report)
**Report:** typing lagged; "which mutual funds should I invest in" for a High-capacity, Medium-willingness profile
(₹2L take-home, ₹12L saved, no goals) returned only FD/RD/liquid/short-debt "for the long term", and the explanation
invented "short-term goals".
**Cause (from the stored advice record):** suitability was correctly Medium (hybrid and gold allowed), but qwen2.5:3b
copied the first products listed; the plan was consistent across rewordings, so the audit passed.
**Changes**
- pipeline-v3: the planner gets the suitability-level standard mix as a "starting point" per bucket (planner prompt v6).
  With qwen2.5:3b the planner still drifts and MR6 then falls back to that standard mix — correct, but ~50 s on CPU.
- Deterministic opening paragraph for every plan: capacity, questionnaire score, risk ceiling, products held back and
  why, a prompt to add goals when there are none, and "categories, not schemes" for fund questions.
- New plan step when savings exceed the emergency-fund target and no priority rule applies: move the extra into the
  long-term mix in 6 parts (amounts from code).
- Explain prompt v3 (2–4 sentences, answer the question, no invented goals) plus a guard that drops model sentences
  mentioning goals/horizons when the profile has none.
- Model unreachable: the plan route now shows the deterministic safe plan (labelled, `fallback_reason:
  model_unavailable`) instead of an error; Learn lists matching documents; errors say the model server is down.
- Web: composer owns its own state (typing no longer re-renders the conversation), messages are memoised, streamed
  text is revealed smoothly per animation frame (instant with reduced motion), scrolling follows only when the reader is
  at the bottom and is never smooth per token, and the question appears immediately (measured: 16 ms after Enter).
- 139 backend tests pass (new regression tests from the reported chat).

### 2026-10-31 — Supabase, methodology v2, landing redesign
- Supabase connected (above); instrument lists loaded (5,743 listed, 14,441 schemes).
- rules-v2 / pipeline-v2 / replicate runs (above); 133 backend tests pass, incl. v1 formulas kept under test.
- New landing and sign-in page after the Ascone (structure, forest-green palette, italic-serif accent, bento hero,
  satin numbers band) and Peach AI Finance (atmospheric dark hero, pill nav, arrow-chip buttons) references, with a
  CSS-3D tilting dashboard card; every number on the page is real or labelled "Example data". App tokens moved to the
  same forest-green direction; chart palette re-validated on the new dark surface.

### 2026-10-31 — Phases 2–5 (holdings, prices, CAS, other assets)
**Built**
- Tables: instruments, prices_daily, corporate_actions, market_days, data_job_runs, transactions, watchlist, sips,
  instrument_notes, cas_uploads, other_assets, insurance_policies, liabilities.
- Portfolio engine (`portfolio/engine.py`): FIFO lots, split/bonus adjustment of quantities and prices, realised and
  unrealised P&L, long-/short-term split (> 12 months), XIRR flows, 52-week range from adjusted highs/lows, daily
  value series. Service layer used by every page so numbers reconcile.
- Daily jobs (`market/jobs.py`): masters, daily update with 7-day gap fill, backfill on first tracking (400 days from
  the cache), MF history from MFapi, gold reference from SGBs, short transactions so the site stays responsive.
- API: instrument search, transactions (refuses oversells and future dates), holdings, watchlist (price when added =
  adjusted close on or before the date added), instrument detail (adjusted chart, buy/sell marks, notes), dashboard
  (net worth = assets − loans, range change excluding contributions, allocation, invested/value/gain, XIRR only after
  a year else simple return, movers, benchmark as "same money on the same dates in Nifty 50"), market status,
  other assets / loans / insurance, profile proposal from tracked data, CAS preview → review → import, history, delete.
- CAS (`finadvisor/cas.py`): casparser in memory; CAMS/KFintech transactions (purchases, SIPs, switches, redemptions,
  stamp duty as charges); NSDL/CDSL snapshots need user cost and date; PII stripped, numbers masked to last 4;
  duplicates skipped on re-import; deleting an upload deletes its transactions.
- Web: dashboard with hero net worth (muted paise, as-of chip, pill actions), value chart with range control and
  benchmark, allocation donut + table, returns with explanations, movers; holdings tabs (stocks, funds, other & loans,
  watchlist) with 52-week range bars, LT/ST tooltips, source/as-of under every price, stale flags; instrument page;
  add-transaction dialog with search; CAS import flow; statements in settings; "Fill from what I track" on profile.

**Verified**
- 126 backend tests pass, including engine tests with hand-checked values, parsers on real file formats, API tests on
  seeded prices (holdings ↔ dashboard reconcile exactly; bonus adjusts qty/price/52-week; oversell refused; watchlist
  change since added; CAS import/dedupe/delete/PII; net worth = assets − liabilities; FD accrual; gold valuation).
- Live sources fetched successfully: NSE and BSE bhavcopy, NSE indices, NSE 52-week report, AMFI NAVAll, MFapi.
- 52-week validation results above.

- Also added: anonymised research export (`scripts/export_research.py`, opted-in users only, salted pseudonyms, no
  names/emails/chat text/comments/account numbers; tested), demo account (`scripts/seed_demo.py`, "Example data" banner,
  excluded from research), route code-splitting (first load 780 kB → 479 kB), `docs/DEPLOY.md`.
- End to end on real data: a test portfolio (RELIANCE, WEBELSOLAR bought before its split, GOLDBEES, Parag Parikh Flexi
  Cap Direct, FD, savings, EPF, physical gold, car loan, health cover) — holdings, instrument page and dashboard
  reconcile; screenshots reviewed in light, dark and phone layouts.

**Not verified**
- Lighthouse/axe audits not run (no tooling installed); manual keyboard/focus/contrast review only.
- CAS import tested only with casparser-shaped data; no real CAS PDF was available. Please try one of yours.
- Expense ratios (TER) not fetched yet (amfipy not integrated); regular-plan cost note is shown without numbers.
- SIP schedules table exists; no SIP UI yet (SIP instalments can be added as purchases or imported from CAS).


### 2026-10-31 — Phase 0 + 1 (foundations, chat with history, advisor core)
**Built**
- Removed `.env` files from the repo and its whole git history (force-pushed); `.env*` now ignored.
- `finadvisor/` package: capacity, willingness, suitability/gate, pressure, planner, plan builder, auditor, check,
  health card, number guard, router, extraction, pipeline; calculators (XIRR, SIP, EMI, FD/RD, tax, ₹ formatting).
- Versioned configs: rules-v1, shelf-v1, assumptions-v1, gl13-in-v1, tax-fy2026-27, pipeline default, models.
- API: dev/Supabase auth, chats (list/search/rename/pin/delete), streaming send/regenerate/stop, feedback, profile
  versions, questionnaire, what-if, advice records ("Why this plan"), recommendations + status events, health check,
  settings, research consent, sessions (list/revoke/all), export JSON, delete account, about, status.
- Experiment runner (`experiments/run.py`): same pipeline, versioned run configs, resumable JSONL, refuses
  non-synthetic inputs.
- Web: sign-in, app shell (sidebar / floating mobile nav), dashboard (honest empty net-worth state, money health,
  latest advice with status), chat (history sidebar grouped by date, search, rename, pin, delete, streaming,
  stop, regenerate, copy, thumbs up/down with comment, starters, stage progress), cards (health check, plan, goal,
  what-if with sliders, not-yet, profile, questionnaire), "Why this plan" panel, profile page, settings, both themes.
- `supabase/schema.sql` generated from models with RLS enabled.

**Verified**
- 100 backend tests pass (`python -m pytest`), incl. report tests T01–T04, T06, T10, threshold boundaries, calculators
  against hand-checked values and month-by-month simulations, audit repair/fallback/time budget, pressure leaving the
  plan unchanged, number guard, privacy refusal, API flows, concurrency of first sign-in, export/delete, opt-in.
- 8 frontend formatting tests pass (`npm test`); `tsc` clean; production build succeeds.
- End to end in Edge (Playwright) against the real local model: sign-in → profile → plan (69 s) → "Why this plan" →
  pressure turn (plan identical, conflict line + Not-yet card) → Learn answer with sources; both themes and a phone
  viewport screenshotted and reviewed. Plan arithmetic checked by hand for one profile.

**Not done / not verified**
- Supabase sign-in, Google OAuth and Postgres not exercised (project unreachable; needs the user, see below).
- Lighthouse/axe audits not run yet (Phase 6). JS bundle is 780 kB (code-splitting in Phase 6).
- Learn answers from the 3B model do not always cite sources inline; sources are always listed under the answer.
- Report tests T05, T07–T09 not identified (table not fully in the report text available).
- The calculators-off ablation raises NotImplementedError (planned with the experiment phase).
- Hosting not set up (Oracle signup pending with the user).

**Needs the user**
- Restore (unpause) the Supabase project, then share the anon key and DB connection string (or apply
  `supabase/schema.sql` in the SQL editor) and enable Google as an auth provider if wanted.
- Decide the open questions above.
