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
   design, and a validation of our own oracle against hand-worked answers and hand labels.
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
| RVR, PFR, AR, DVR, paraphrase consistency, personalisation (weighted Jaccard), soft quality (3 LLM judges), usability (SUS), latency | Unsuitable rate (= RVR, with the text oracle as a second reading), pressure kept (= 1 − PFR), DVR per relation and case, MR6 as part of DVR, replicate agreement, unsourced numbers, A5 arithmetic, outcome (pass/repaired/fallback), latency; blind human grading of explanations with κ | **Keep what exists. Add personalisation** (mean pairwise weighted Jaccard of final plans, computed from stored plans, no runs): it answers "does the gate homogenise advice?", the report's H4, and is cheap. **Drop LLM judges** (the blind two-grader study replaces them; judges would add a validity argument we cannot afford). **Drop the user study** from this paper; state it as the next step. Acknowledgement rate: report it from the ADV run (the conflict line is deterministic, so it is 100 % by construction; say so in one sentence rather than a table). |
| OSF pre-registration | Not done; the report dated 30 Oct 2026 fixes the hypotheses and metrics before any run | Say exactly that. Do not claim pre-registration. |
| Differential test: 40 profiles through SEBI's live tool | Not done | **Do it** (half a day by hand): it is the only external check of the capacity engine and the reviewer table in the report promised it. Report agreement and explain each mismatch. |
| Hand-worked oracle | `handcheck_v1.csv` (45 personas) and `experiments/handcheck.py` ready; not yet filled in | **Must do**, two people independently. |
| Pressure moves willingness only (Ch. 4) | Implementation: pressure moves nothing; only retaking the questionnaire changes willingness (team decision, 31 Oct) | Update the paper to the implementation and give the reason (the plan must not move unless facts change). |
| s_D = clip((0.40 − D)/0.40) (Ch. 4, Alg. 1) | rules-v2: s_D = min(1, 0.40/D); v1 kept as sensitivity S1 | Update the equation; report S1. |
| MR6: P(x′) = P(x) exactly | Same products, shares within 0.10; S2 compares risky share instead | State the tolerance; report S2 next to A1 and the split of fallbacks by cause. |
| Ablation "without clarifying question" | Not built | Drop. |
| The website runs the LLM planner | Website uses the standard mix (`planner.mode: standard`); the LLM planner is evaluated offline | Say so in one sentence in the system section and again in threats. |

---

## 3. Must-do before writing results (in parallel with the runs)

| # | Task | Who | Effort | Why it is not optional |
|---|---|---|---|---|
| 1 | Finish the 17 runs on Colab (A1 → ADV, per the notebook order); run `experiments.report` | user | ~2 weeks of free GPU sessions | the evidence |
| 2 | Hand-worked oracle: two people fill `handcheck_v1.csv` from the written rules; `python -m experiments.handcheck` | two team members | 2 × 3 h | our suitability oracle is our own gate; this is the independent check |
| 3 | SEBI live-tool differential test on 40 personas | one person | 4 h | external validation of the capacity engine |
| 4 | Oracle labels: ~100 answers from B1/B2/A1T, products recommended + monthly total; `grading oracle-score` | one person | 4 h | precision/recall of the text oracle, needed for every baseline number |
| 5 | Blind grading of ~120 explanations (A1T, A4, B1, B2) by two people; κ and weighted κ | two people | 2 × 3 h | the only quality measure of the prose |
| 6 | Add baseline B3 "rules in the prompt" (template with R1–R7 in words, ALLOCATION block); run 240 × 3 | me + Colab | 1 day + 3 GPU h | the obvious alternative must be beaten, not ignored |
| 7 | Personalisation (weighted Jaccard) and the surrogate capacity-share analysis in `experiments/metrics.py`; both from stored records | me | 1 day | H4 and the motivation figure, no runs |
| 8 | Persona ranges vs RBI/NSO household figures (income, savings months, EMI share, dependants): one table | me | half a day | "are the profiles realistic?" |
| 9 | Failure analysis: read 20 fallback cases and 20 baseline unsuitable answers; annotate | two people | 3 h | the discussion needs examples, not only rates |

Nothing in this list changes the pipeline, so none of it affects the runs.

---

## 4. The paper (IEEE two-column, 8 pages + references)

**Title** (working): *Suitable by Construction: Capacity-Gated, Self-Auditing Personal-Finance Advice from Small Local
Language Models*. Keep "Indian households" in the abstract and the first paragraph, not the title; the method is not
India-specific, the thresholds are.

| § | Content | Length |
|---|---|---|
| 1 Introduction | The failure (appetite-only advice, sycophancy, invented numbers), why it matters in India (F&O losses, SEBI suitability), the idea in one paragraph, the three contributions, the headline numbers | 0.9 p |
| 2 Related work | Heuristic collapse and sycophancy in LLM advice; guardrail approaches (prompt rules, post-hoc projection, verification); metamorphic testing of LLMs; risk-tolerance measurement. One compact table (the report's Table 2.1 cut to 8 rows). | 0.8 p |
| 3 FinAdvisor | Pipeline figure; capacity (five scores, weakest link, levels); willingness (G&L, experience cap); gate (riskometer ceiling, R1–R7 table with sources); planner (chooses weights only; calculators); auditor (MR1–MR6 table, repair, fallback, the *case* of each check); number guard; what the website runs. Algorithms as short pseudo-code or omitted in favour of the tables. | 2.2 p |
| 4 Evaluation setup | Personas (how stratified, ranges vs RBI/NSO); systems (B1, B2, B3, A1, ablations A2–A6, S1, S2, M1, ADV); metrics with one-line definitions; statistics (persona as unit, Wilson / cluster bootstrap, McNemar + Holm, replicates at T = 0 as kernel spread); oracle validation (handcheck agreement, SEBI tool, text-oracle precision/recall, grader κ) | 1.3 p |
| 5 Results | 5.1 main table (unsuitable, text oracle, unsourced numbers, pressure kept, pass/fallback, latency) with one figure of unsuitable rate by system with intervals; 5.2 ablations and what each component does (A2 vs A3 is the key pair); 5.3 DVR per relation and case, why first plans fail (MR6 split, S2); 5.4 model size and family; 5.5 pressure and adversarial turns; 5.6 costs: fallbacks, repairs, latency; 5.7 personalisation and the capacity-share figure; 5.8 explanation quality (blind grading); 5.9 failure analysis with 3–4 short examples | 2.2 p |
| 6 Discussion and threats | What the gate does vs what the auditor does; MR6 strictness vs wording robustness; our own oracle; synthetic personas; small models and one hardware class; website uses the standard mix; non-commercial model licence; no user study yet | 0.5 p |
| 7 Conclusion | Three sentences | 0.1 p |

Figures (4): pipeline; unsuitable rate by system (CIs); DVR by relation and case; fallback causes with S2. Tables (5):
rules, relations, main results, ablations/models, oracle validation. Everything else goes to a supplementary file
with the full report tables (`experiments.report` output) and the persona-range table.

**Writing rules.** Every number in the paper is copied from `results/paper/report.json` by a script that writes the
LaTeX tables (`experiments/paper_tables.py`, to add), never typed. Intervals on every rate. "Fallback" is reported as a
cost, never hidden in "pass". The words "guarantee" and "safe" are not used about the model; "by construction" is used
only for what the gate and calculators enforce.

---

## 5. Reviewer risks and the answer we will have

| Risk | Answer |
|---|---|
| "Your oracle is your own gate." | Agreement of the gate with two hand-workers on 45 personas (κ per field); 40 personas through SEBI's live tool; the text oracle's precision/recall on 100 hand labels; all three in §4. |
| "Why not put the rules in the prompt?" | B3 is exactly that, same model, same format; the result table shows the gap. |
| "Synthetic personas." | Stratified by rule, ranges compared with RBI/NSO figures; the limitation stated; the adversarial turns are human-written. |
| "Replicates at temperature 0 are not independent." | They are reported as agreement, not pooled; every interval is persona-level. |
| "MR6 is too strict; fallbacks are inflated." | Fallback causes split by relation and menu; S2 shows the rate with a risk-based MR6; both reported. |
| "Only small models." | 1.5B to 7B across three families (M1); the method does not depend on size; larger models are future work, and the point is that small local models become usable. |
| "The website doesn't even run this planner." | Stated; the standard-mix mode is the same gate and calculators with no model choice, and the paper evaluates the design. |
| "No users." | A usability study is the stated next step; the product is live and instrumented for it (consent, analytics). |
| "Is this just a rule engine with an LLM veneer?" | The ablation pair A2 (gate off) vs A3 (auditor off) and the DVR on checks that *test the model* show where the model's choices matter and what the auditor adds beyond the rules; personalisation shows the plans are not one template. |

---

## 6. Venue

Target an IEEE venue whose scope is AI systems and trustworthiness rather than finance alone; the contribution is
the construction and measurement method.

- **Primary: IEEE CAI 2027** (IEEE Conference on Artificial Intelligence, Singapore, 30 Nov–2 Dec 2027). Two
  different submission dates are published (31 March 2027 on the IEEE SPS page; 15 May 2027 on WikiCFP); confirm on
  the official site before planning backwards. Either gives time to finish §3 and write properly.
- **Also fitting:** IEEE SSCI 2027's CiFEr (financial engineering) and CITREx (trustworthy/explainable AI) symposia;
  the late-breaking date has passed, so check the next full-paper round. ACM ICAIF is the natural subject-matter
  home if an ACM venue is acceptable. FinFM 2027 (workshop, 20 Nov 2026) is too soon for results.
- Post an **arXiv preprint** when the results are in (January), so the work is dated before review.

Sources: [IEEE CAI 2027 (SPS)](https://signalprocessingsociety.org/events/2027-ieee-conference-artificial-intelligence-cai),
[CAI 2027 on WikiCFP](http://wikicfp.com/cfp/servlet/event.showcfp?eventid=201206),
[IEEE SSCI 2027 call for papers](https://attend.ieee.org/ssci-2027/submissions/call-for-papers/),
[FinFM 2027](https://finfm.finhorizons.org/), [IEEE SaTML 2027](https://satml.org/).

---

## 7. Timeline

| When | What |
|---|---|
| Now → late Nov | Runs finish on Colab (user). In parallel: handcheck, SEBI differential test, oracle labels, blind grading (team); B3 baseline, personalisation and surrogate analyses, persona-range table, `paper_tables.py` (me). |
| Early Dec | `experiments.report` on everything; failure-analysis reading; results and discussion sections drafted from the generated tables. |
| Mid Dec | Full draft; internal review against §5; the report's Chapters 4 and 6 updated to match the implementation (the deltas in §2). |
| January | arXiv preprint; code, configs, personas and result files released with a DOI (Zenodo, free). |
| Feb–Mar 2027 | Revisions; submit to IEEE CAI 2027 on its confirmed deadline. |

---

## 8. What we will not do for this paper
- No 70B or third-party-API baseline (cost, licence, and the question is answered by M1).
- No LLM-as-judge; human blind grading only.
- No user study in this paper; it is the next paper's centre.
- No new metamorphic relations or threshold changes before submission: the design is frozen at pipeline-v4 /
  rules-v2 for every reported run, with S1/S2 as the sensitivity cases.
- No claim of a benchmark contribution, pre-registration, or survey-matched profiles.
