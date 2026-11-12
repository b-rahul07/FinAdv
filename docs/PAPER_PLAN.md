# The paper: plan

Written 12 Nov 2026, after reading the Phase-I report (`FinAdvisor_Report_Overleaf/`, 60 pages, 30 Oct 2026), the
experiment code and the runs in progress. The report promised a large evaluation designed before anything was
measured. This document decides what the conference paper claims, which of the report's promises to keep, which to
drop and why, what must still be done, and how the paper is written. The guiding rule is the same as for the product:
one clear contribution with evidence that survives a sceptical reviewer, not a long list of experiments.

---

## 1. The one claim

> A small, local language model can give personal-finance advice that is suitable *by construction*: a deterministic
> capacity engine and product gate decide what is allowed, calculators produce every number, and a run-time
> metamorphic auditor catches and repairs the model's remaining mistakes. On 240 stratified Indian personas the full
> system's unsuitable-advice rate is a small fraction of the same model's unconstrained rate, and ablations show
> which component is responsible for what, at what cost in fallbacks and latency.

Three contributions, in the order a reviewer will weigh them:

1. **The method**: suitability = min(capacity, willingness) with capacity computed from facts under SEBI's published
   thresholds; a gate; a planner that only chooses mixes; a metamorphic auditor (MR1–MR6) with bounded repair and a
   deterministic fallback; a sentence-level number guard. Nothing here depends on the model being large or honest.
2. **The measurement**: label-free safety metrics (unsuitable rate against the true facts, direction-violation rate
   per relation with each check's *case*, unsourced-number rate, pressure resistance), a persona-level statistical
   design, and automated checks of our own oracle (the written rules reworked without the engine's code; a
   rule-by-rule comparison with SEBI's tool), with its limits stated.
3. **The evidence**: full system vs the same model plain and with RAG; five ablations (gate, auditor, calculators,
   number guard, pressure fence); four models; sensitivity to the capacity formula, the emergency-fund target and the
   MR6 definition; 50 adversarial turns.

Everything in the paper serves these three. The benchmark personas are released with the code, but the paper does
**not** claim a benchmark as a contribution (see §3: it is 240 stratified synthetic personas, not the survey-matched
IndiaSuit the report described).

---

## 2. What the report promised vs what exists

| Report (Ch. 6) | Built | Decision |
|---|---|---|
| IndiaSuit: ~1,000 LHS profiles + ~500 matched to SEBI/RBI marginals, 3 paraphrases, 6 pressure types | 240 stratified personas (each rule fires ≥ 44×, each level ≥ 48), 68 with a wish; MR6 uses 2 paraphrase styles; 50 adversarial turns of 5 kinds | **Keep 240.** Power is adequate for the main contrast (Wilson width ≈ ±6 pp at n = 240; the A1-vs-B1 gap is tens of points). Say plainly that personas are stratified for rule coverage, not survey-matched, and check their ranges against RBI/NSO household figures (one table). Drop the 1,500-persona plan. |
| Baselines B0 (plain), B1 (old prototype), B2 (rules in prompt), B3 (cap projection), B4 (input filter), B5 (~70B) | B1 plain model, B2 model + library RAG | **Add one: rules in the prompt** (the report's B2). It is the first thing a reviewer asks: "why not just tell the model the rules?" It costs a template and ~3 GPU hours (`experiments/baselines.py`, no pipeline change). Drop the prototype, the cap projection, the input filter and the 70B: each answers a secondary question, the 70B needs a third-party API, and the model-size question is already covered by M1 (1.5B → 7B). |
| RQ0/RQ1: Ross & Lo replication, feature concentration (FC), capacity share via surrogates | Nothing | **Keep a light form, no new runs.** On the baselines' ALLOCATION blocks (already parsed), regress the recommended risky share on the persona's features (ridge, 5-fold R²) and report the importance share of the willingness score vs the capacity features. Half a day of analysis; it turns the introduction's "heuristic collapse" from a citation into a figure on our own personas. Do not call it a replication. |
| RVR, PFR, AR, DVR, paraphrase consistency, personalisation (weighted Jaccard), soft quality (3 LLM judges), usability (SUS), latency | Unsuitable rate (= RVR, with the text oracle as a second reading), pressure kept (= 1 − PFR), DVR per relation and case, MR6 as part of DVR, replicate agreement, unsourced numbers, A5 arithmetic, outcome (pass/repaired/fallback), latency | **Keep what exists. Add personalisation** (mean pairwise weighted Jaccard of final plans, computed from stored plans, no runs): it answers "does the gate homogenise advice?", the report's H4, and is cheap. **Drop LLM judges and the blind grading by people** (decision of 12 Nov: no hand tasks). The paper therefore makes no claim about the accuracy of the explanations beyond the unsourced-number rate, and says so. **Drop the user study** from this paper; state it as the next step. Acknowledgement rate: report it from the ADV run (the conflict line is deterministic, so it is 100 % by construction; say so in one sentence rather than a table). |
| OSF pre-registration | Not done; the report dated 30 Oct 2026 fixes the hypotheses and metrics before any run | Say exactly that. Do not claim pre-registration. |
| Differential test: 40 profiles through SEBI's live tool | **Replaced, 12 Nov.** The tool asks for no amounts and computes nothing: 14 questions, a fixed colour per answer. Entering personas by hand would only test the person's own arithmetic. `experiments/sebi_check.py` instead compares, for all 240 personas, the colour the tool gives the answer a truthful person would pick with whether our rule fires | **Report the table**: R1, R2, R5 agree 100 %; R3 80 % (the engine uses the tool's advised amount as the pass mark; the tool colours any cover green); R4 90 % (24 personas whose only unsecured loan is an education loan at 10.5 %: the tool flags them, the engine does not). State both differences as design choices. **R4 decided (12 Nov): keep rules-v2, no new model run.** Report the label sensitivity instead: with any unsecured loan counted as costly (`rules-v2-unsecured`), R4 agrees with the tool on all 240 personas and suitability falls for 12 of them (7 medium to low, 5 high to low). Describe the tool correctly in the paper: its thresholds are our source, it is not a calculator. `--live` re-reads the page and compares it with the saved copy. |
| Hand-worked oracle | Tools ready (`handcheck_v1.csv`, `experiments/handcheck.py`, `docs/handcheck/`); not filled in | **Dropped (12 Nov: no hand tasks).** In its place `experiments/rules_rework.py`: the written rules worked in plain arithmetic, without the engine's code, agree with the engines on 240 of 240 personas in all four fields. The paper states that suitability is judged by the system's own rule engine and that this check is against the written rules, not by independent people. |
| Pressure moves willingness only (Ch. 4) | Implementation: pressure moves nothing; only retaking the questionnaire changes willingness (team decision, 31 Oct) | Update the paper to the implementation and give the reason (the plan must not move unless facts change). |
| s_D = clip((0.40 − D)/0.40) (Ch. 4, Alg. 1) | rules-v2: s_D = min(1, 0.40/D); v1 kept as sensitivity S1 | Update the equation; report S1. |
| MR6: P(x′) = P(x) exactly | Same products, shares within 0.10; S2 compares risky share instead | State the tolerance; report S2 next to A1 and the split of fallbacks by cause. |
| Ablation "without clarifying question" | Not built | Drop. |
| The website runs the LLM planner | Website uses the standard mix (`planner.mode: standard`); the LLM planner is evaluated offline | Say so in one sentence in the system section and again in threats. |

---

## 3. What is left before writing results

No task here needs work by hand. Nothing in this list changes the pipeline, so none of it affects the runs.

| # | Task | Status | Why |
|---|---|---|---|
| 1 | Finish the runs on Colab (A1 → ADV, in the notebook's order); run `experiments.report` | in progress | the evidence |
| 2 | Baseline B3 "rules in the prompt" | built; runs on Colab after B2 | the obvious alternative must be beaten, not ignored |
| 3 | Written rules against the engines (`python -m experiments.rules_rework`) | done: 240 of 240 in all four fields | the rules the paper describes are the rules the code runs |
| 4 | SEBI's tool rule by rule (`python -m experiments.sebi_check --live`) | done; rerun with the final report | where the engine matches its source and where it departs |
| 5 | The two readings of each baseline answer (block and free text) in the report | done; numbers come with the baseline runs | a consistency check of the reader the baseline numbers rest on |
| 6 | Personalisation and the capacity-share surrogate | done | H4 and the motivation figure |
| 7 | Persona ranges against published household figures | done (`docs/EXPERIMENTS.md` §4) | "are the profiles realistic?" |
| 8 | LaTeX tables from `report.json` (`experiments/paper_tables.py`) | done | no number typed |

**Dropped on 12 Nov (no hand tasks), and what the paper says instead.** None of these is needed for acceptance at an
Indian IEEE conference; each costs a sentence in the threats section.

| Dropped | The paper says |
|---|---|
| Two people working 45 personas by hand | Suitability is judged by the system's own rule engine; a second working of the written rules agrees on all personas; no independent person re-derived the answers. |
| Clicking through SEBI's tool | The comparison uses the page's own question data, saved with its date and hash. |
| Hand labels for the free-text reader (precision and recall) | Baselines are judged on their ALLOCATION block; agreement of the block and free-text readings is reported; the reader was not scored against labels. |
| Blind grading of explanations | No claim about the accuracy of the prose. |
| Annotated reading of failures | Three or four examples are quoted from the stored records. |

The tools for all of these stay in the repository (`experiments/handcheck.py`, `experiments/grading.py`,
`docs/handcheck/`), so a later, longer version of the paper can add them without new code.

---

## 4. The paper (IEEE two-column; 6 pages for most Indian IEEE conferences, 8 where allowed)

**Title** (working): *Suitable by Construction: Capacity-Gated, Self-Auditing Personal-Finance Advice from Small Local
Language Models*. Keep "Indian households" in the abstract and the first paragraph, not the title; the method is not
India-specific, the thresholds are.

| § | Content | Length |
|---|---|---|
| 1 Introduction | The failure (appetite-only advice, sycophancy, invented numbers), why it matters in India (F&O losses, SEBI suitability), the idea in one paragraph, the three contributions, the headline numbers | 0.9 p |
| 2 Related work | Heuristic collapse and sycophancy in LLM advice; guardrail approaches (prompt rules, post-hoc projection, verification); metamorphic testing of LLMs; risk-tolerance measurement. One compact table (the report's Table 2.1 cut to 8 rows). | 0.8 p |
| 3 FinAdvisor | Pipeline figure; capacity (five scores, weakest link, levels); willingness (G&L, experience cap); gate (riskometer ceiling, R1–R7 table with sources); planner (chooses weights only; calculators); auditor (MR1–MR6 table, repair, fallback, the *case* of each check); number guard; what the website runs. Algorithms as short pseudo-code or omitted in favour of the tables. | 2.2 p |
| 4 Evaluation setup | Personas (how stratified, ranges vs RBI/NSO); systems (B1, B2, B3, A1, ablations A2–A6, S1, S2, M1, ADV); metrics with one-line definitions; statistics (persona as unit, Wilson / cluster bootstrap, McNemar + Holm, replicates at T = 0 as kernel spread); checks of the oracle (written rules against the engines, SEBI tool rule by rule, the two readings of each baseline answer) | 1.2 p |
| 5 Results | 5.1 main table (unsuitable, text oracle, unsourced numbers, pressure kept, pass/fallback, latency) with one figure of unsuitable rate by system with intervals; 5.2 ablations and what each component does (A2 vs A3 is the key pair); 5.3 DVR per relation and case, why first plans fail (MR6 split, S2); 5.4 model size and family; 5.5 pressure and adversarial turns; 5.6 costs: fallbacks, repairs, latency; 5.7 personalisation and the capacity-share figure; 5.8 three or four short examples of failures taken from the stored records | 2.1 p |
| 6 Discussion and threats | What the gate does vs what the auditor does; MR6 strictness vs wording robustness; our own oracle, checked only by programs; the text reader not scored against labels; explanations not graded; synthetic personas; small models and one hardware class; website uses the standard mix; non-commercial model licence; no user study yet | 0.7 p |
| 7 Conclusion | Three sentences | 0.1 p |

Figures (4): pipeline; unsuitable rate by system (CIs); DVR by relation and case; fallback causes with S2. Tables (5):
rules, relations, main results, ablations/models, checks of the oracle. Everything else goes to a supplementary file
with the full report tables (`experiments.report` output) and the persona-range table.

**Writing rules.** Every number in the paper is copied from `results/paper/report.json` by a script that writes the
LaTeX tables (`experiments/paper_tables.py`), never typed. Intervals on every rate. "Fallback" is reported as a
cost, never hidden in "pass". The words "guarantee" and "safe" are not used about the model; "by construction" is used
only for what the gate and calculators enforce.

---

## 5. Reviewer risks and the answer we will have

| Risk | Answer |
|---|---|
| "Your oracle is your own gate." | Stated in the paper, not argued away. What we have: the written rules reworked without the engine's code agree on all 240 personas; rule-by-rule agreement with SEBI's tool, with the two departures stated; unit tests at every threshold. What we do not have and say so: an independent person re-deriving the answers. |
| "How do you know the reader of the baselines' free text is right?" | Baseline answers end in a fixed ALLOCATION block and are judged on it; the report gives how often the block was present and how often the block and the free-text reading reach the same verdict. The reader was not scored against labels; stated as a limitation. |
| "Are the explanations any good?" | Not claimed. The paper measures unsuitable products, overspending and unsourced numbers; the quality of the prose is future work. |
| "Why not put the rules in the prompt?" | B3 is exactly that, same model, same format; the result table shows the gap. |
| "Synthetic personas." | Stratified by rule, ranges compared with RBI/NSO figures; the limitation stated. |
| "Replicates at temperature 0 are not independent." | They are reported as agreement, not pooled; every interval is persona-level. |
| "MR6 is too strict; fallbacks are inflated." | Fallback causes split by relation and menu; S2 shows the rate with a risk-based MR6; both reported. |
| "Only small models." | 1.5B to 7B across three families (M1); the method does not depend on size; larger models are future work, and the point is that small local models become usable. |
| "The website doesn't even run this planner." | Stated; the standard-mix mode is the same gate and calculators with no model choice, and the paper evaluates the design. |
| "No users." | A usability study is the stated next step; the product is live and instrumented for it (consent, analytics). |
| "Is this just a rule engine with an LLM veneer?" | The ablation pair A2 (gate off) vs A3 (auditor off) and the DVR on checks that *test the model* show where the model's choices matter and what the auditor adds beyond the rules; personalisation shows the plans are not one template. |

---

## 6. Venue

Decision of 12 Nov: **any IEEE conference held in India whose proceedings go to IEEE Xplore** is the target. Pick
the first one with an AI or computing track whose deadline falls after the results are in (mid December at the
earliest). Requirements to check on the conference's own site before submitting: IEEE conference record number (the
event is listed on `conferences.ieee.org`), page limit (usually 6 pages, two-column), the similarity-check limit, and
the registration fee.

Candidates to look up (dates below are from aggregator listings and are **not confirmed**):

- **IEEE CONECCT 2027** (Bengaluru, IEEE Bangalore Section): one listing gives 15 Dec 2026 for submissions and March
  2027 for the conference. Tight but possible if the runs finish in November.
- **IEEE INDISCON 2027**, **IEEE INDICON 2027** (IEEE India Council; deadlines usually March to July).
- **ICCCNT 2027**, **IEEE I2CT 2027**, **IEEE PuneCon 2027**, and the section conferences (Delhi, Kolkata, Hyderabad,
  Kerala) as they announce.

Most Indian IEEE conferences allow 6 pages, so the paper in §4 is cut to 6: related work to half a page, the
sensitivity runs and model table to one combined table, examples to two.

Sources: [CONECCT listing](https://www.myhuiban.com/conference/4809), [CONECCT 2026 site](https://2026.connect.ieeebangalore.org/).

---

## 7. Timeline

| When | What |
|---|---|
| Now → late Nov | Runs finish on Colab. |
| Early Dec | `experiments.report` on everything; `sebi_check --live`; tables generated; results and discussion drafted. |
| Mid Dec | Full 6-page draft; check against §5; submit to the first confirmed Indian IEEE conference. |
| After | The report's Chapters 4 and 6 updated to match the implementation (the deltas in §2). |

---

## 8. What we will not do for this paper
- No 70B or third-party-API baseline (cost, licence, and the question is answered by M1).
- No LLM-as-judge and no grading by people: no claim about the quality of the prose.
- No hand-worked checks (decision of 12 Nov); the oracle is checked by programs and the limit is stated.
- No user study in this paper; it is the next paper's centre.
- No new metamorphic relations or threshold changes before submission: the design is frozen at pipeline-v4 /
  rules-v2 for every reported run, with S1/S2 as the sensitivity cases.
- No claim of a benchmark contribution, pre-registration, or survey-matched profiles.
