# FinAdvisor: the plan for a calm place to manage your money

Written 11 Nov 2026 after reading the whole website and the evidence we have about how it is used. The goal is not
more features. It is that a young Indian earner can keep all of their money in one place, see where they stand in a
glance, always know the next step, and get a straight answer to any question, without ever feeling managed by the
app. Everything below is judged against that, and the second half of this document is the list of things we decided
*not* to build.

Project rules still hold: free only, the model never computes a number, personal advice goes through the pipeline,
no individual securities, the disclaimer wherever advice appears. Items marked **[pipeline]** change what the paper's
experiments measure; they wait until the runs finish.

---

## 1. The four jobs the site must do

1. **Where do I stand?** One screen: what I own, what I owe, what is left each month, whether I'm safe.
2. **What should I do next?** One plan, a few steps in order, each one trackable, re-made when my facts change.
3. **Answer my question.** Any money question gets a direct answer in my numbers, or an honest "I need one fact".
4. **Keep it current without work.** Holdings, loans, insurance and SIPs stay up to date with as little typing as
   possible, and prices refresh whether or not our laptop is on.

How the site serves them today:

| Job | Works | Missing |
|---|---|---|
| Where do I stand | Net worth, value chart, allocation, returns, health score | The monthly picture (take-home → EMIs → SIPs → expenses → what is left) is nowhere; health score has no history; goals aren't on the home page; facts live on a separate "Profile" tab away from the things they describe |
| What to do next | Plan card, done/skipped on each step | Steps are a list, not a path through time; nothing says "you're on step 2 of 5" or "your profile changed, re-plan"; the plan hides under "Details" |
| Answer my question | 16 deterministic intents, question-first replies, evidence, why | Follow-ups ("and with a car loan?") start over; a missing fact sends you to a 20-field form; tax questions are refused; anything outside the 16 intents gets the generic plan |
| Keep it current | CAS import, FD/RD accrual, gold reference, loans, insurance, watchlist | SIPs aren't tracked; price jobs stop when the laptop is off; nothing nudges you when data or facts go stale |

---

## 2. Design principles (what "pleasant" means here)

- **One home, three answers.** The home page answers jobs 1 and 2 and offers job 3 in one input. No second dashboard.
- **One plan.** There is always exactly one current plan. New facts don't add a card; they update the plan and say what
  changed.
- **Ask once.** A missing fact is asked as one question, in the chat, and remembered. Never a form in reply to a question.
- **Nothing typed that can be imported or derived.** SIPs are found from transactions; facts are filled from holdings;
  CAS import is offered before manual entry.
- **Every number has a source you can see.** Already true; keep it visible rather than hidden in "Why".
- **Quiet by default.** Four kinds of nudge only (stale prices, step due, profile old, SIP missed), in-app, each one
  switch-offable. No streaks, no badges, no confetti.
- **Say less.** A reply is: the answer, what to do, why. Everything else is one tap away, not on screen.

---

## 3. The plan (three phases, about seven weeks)

### Phase 1: One home (2 weeks)

**Restructure, not add.** Four tabs: **Home · Advisor · My money · Settings**. The Profile tab goes; its facts move to
where they belong.

- **Home** becomes three blocks, in this order:
  1. *Where you stand*: net worth (as now) next to a **monthly cash flow** strip: take-home → EMIs → SIPs → expenses →
     left over. All from the profile and holdings; the "left over" is the surplus the plan uses, so the number people
     see is the number the advice uses. Health score with a small history line (the snapshots exist).
  2. *Your plan*: the current plan as a **timeline** (priority steps as bars over months, investing after), the next
     step highlighted with its amount, "step 2 of 5 done", and a *Re-plan* prompt when the profile version is newer
     than the plan's. Goals as funded-% bars under it.
  3. *Ask*: one input that opens the advisor with the question.
- **My money** holds everything owned, owed and insured, and the facts: Stocks · Funds · Deposits & other · Loans ·
  Insurance · Facts (take-home, expenses, dependants, experience, questionnaire). "Fill from what I track" runs
  automatically here: when a loan or policy is added, the facts update with one confirm.
- **Mobile**: card rows for holdings below `md`; the bottom nav gets the four tabs.
- Effort: dashboard 3 days, My money merge 3 days, timeline 2 days, mobile 1 day, tests 1 day.
- *Verify*: `tsc`, vitest, an axe pass; five people asked to find "how much is left each month" and "what's my next
  step" without help.

### Phase 2: A straight answer, every time (3 weeks)

- **Follow-ups are what-ifs.** "And if I add a car loan of 12k?", "with two dependants?", "if I save 5k more?" after a
  plan run the what-if engine on the last plan and answer in one paragraph with a *Make this my profile* button.
  Deterministic (`followup.py` reading the earlier turns `pressure.read` already keeps). 3 days.
- **Ask one question.** When an answer needs one missing fact (a goal's target or date, rent paid, gross salary), the
  reply is a single-field card; the answer is saved as a profile version. 2 days.
- **Tax, answered.** An income-tax calculator (`calc/income_tax.py`, slabs and deductions in `configs/tax/`): both
  regimes from the facts, the cheaper one named with the rupee difference, and the two comparisons people actually
  ask (FD vs debt fund after tax; ELSS/PPF/NPS under each regime). The profile gets three optional fields: gross
  salary, rent paid, 80C/80D amounts, asked only when needed (previous item). 5 days. This is the one new calculator;
  it is the most asked question we refuse today.
- **"Am I on track?"** answers from the plan progress, goal funded-% and health history built in Phase 1. 1 day.
- **Retirement without a goal**: when someone asks about retirement and has no target, the single-question card asks
  for monthly spending wanted in today's money; the corpus and SIP follow from existing calculators. 1 day.
- **Shorter replies.** The plan card is always visible; health check, what-if and evidence sit behind one "More"
  link. "What changed since your last plan" is one line at the top when a plan is re-made. 2 days.
- **The eval grows with it**: 20 turns added to `experiments/eval_advice.py` for follow-ups, clarifications and tax,
  using the checks that already exist (route, numbers from code, no names, framing). 1 day.
- *Verify*: the eval stays green; the share of real questions (opted-in users) that get a specific answer rather than
  the generic plan, measured before and after.

### Phase 3: It stays current by itself (2 weeks)

- **Prices refresh off the laptop.** `finadvisor.market.jobs daily` needs only the database and the internet: run it
  on a **GitHub Actions schedule** against Supabase (`DATABASE_URL` as a secret). The weekly fund finder and the news
  cache move from local files to tables so they run there too. 2 days.
- **SIPs found, not typed.** Recurring buys of the same scheme (same amount ± 1 %, roughly monthly) are detected from
  transactions and shown as SIPs with the next expected date; a missed instalment is one of the four nudges. The
  `sips` table stores the detected ones and any the person confirms or corrects. 3 days.
- **Four nudges, in-app only**: prices stale > 4 days, a plan step due this month, profile older than 6 months, a SIP
  instalment missed. Inbox icon in the shell; the existing settings switches control them. 2 days.
- **Capital-gains statement** for the financial year (realised short/long-term, estimated tax, CSV) so tax season
  needs nothing else. `calc/tax.py` exists. 2 days.
- **CI**: pytest, `tsc`, vitest, build, on every push. 0.5 day.
- *Verify*: price age at 9 am IST for a week with the laptop off; SIP detection on the long-history test account.

### After the paper runs finish **[pipeline]**
- Indian money phrases in extraction ("12 LPA", "50k in hand", "do lakh").
- Card dues cleared with interest and a card's minimum-due EMI freed afterwards (new plan version tag).
- An Apache/MIT-licensed model for the website, chosen from the M1 results.
- Hinglish replies for the fixed wording, if the usability sessions show people writing in Hinglish (the adversarial
  set suggests they will). The templates are ours, so this is translation, not model work.

---

## 4. What we will not build (and why)

| Dropped | Why |
|---|---|
| Budgeting / expense categories / bank-statement import | A second product. One honest "expenses per month" number plus the cash-flow strip is enough for the plan; transaction-level budgeting would dominate the UI and the upkeep. |
| Rent-vs-buy, affordability, step-up and other calculators | Each is a page people use once. The tax calculator stays because it is asked constantly and changes what the plan should do. |
| Hindi/Hinglish full translation now | Large, and the first users are English-writing; revisit with evidence (above). |
| Voice input, PWA, offline mode | Nice, not asked for; nothing in the four jobs needs them. |
| Sector/market-cap allocation for stocks | No free, reliable sector source; a half-right chart is worse than none. |
| Dividends/IDCW tracking | Direct-Growth is the default we show; add only if CAS imports show payout plans in practice. |
| Demo mode, plan PDF, plan history page | Low use; "Why this plan" and the export already exist. |
| Streaks, badges, scores beyond the health check | Against the quiet-by-default principle. |
| More chat intents beyond follow-ups, clarifications, tax, on-track | Coverage comes from understanding follow-ups and asking one question, not from more templates. |

---

## 5. What we measure
- Time to the first plan for a new user (target under 5 minutes, questionnaire included).
- Share of questions answered specifically rather than with the generic plan (target over 80 %).
- Share of users who mark a step done or re-plan within 30 days.
- Price age each morning once jobs run from GitHub Actions (≤ 1 trading day).
- Safety, unchanged: no unapproved number shown, no company named, the disclaimer on every advice reply, the advice
  evaluation green on every release.
