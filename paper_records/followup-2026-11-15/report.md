# FinAdvisor experiment report

The unit is the persona: n counts personas (DVR: personas whose checks are pooled; adversarial: turns). Intervals are 95%: Wilson with one observation per persona, or a persona-level cluster bootstrap (marked *) when replicates or several checks per persona are pooled. 'Replicate 0' is the first replicate alone (Wilson). 'Text oracle' judges every run's answer text the same way as the baselines.

| Run | Model | Personas | Reps | Unsuitable (final) | Unsuitable (replicate 0) | Unsuitable (text oracle) | Unsuitable (first plan) | Unsourced numbers | Pass | Fallback | Pressure kept | Replicate agreement | Median latency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1N7_no_anchor_7b | qwen2.5:7b | 240 | 3 | 0.0% [0.0%, 1.6%] (n=240) | 0.0% [0.0%, 1.6%] (n=240) | — | 1.7% [0.3%, 3.3%]* (n=240) | — | 27.9% [22.8%, 33.3%]* (n=240) | 51.1% [45.1%, 56.8%]* (n=240) | 99.0% [92.9%, 99.9%] (n=68) | 92.1% [88.0%, 94.9%] (n=240) | 17.1 s |
| A1N_no_anchor | qwen2.5:3b | 240 | 3 | 0.0% [0.0%, 1.6%] (n=240) | 0.0% [0.0%, 1.6%] (n=240) | — | 1.8% [0.6%, 3.5%]* (n=240) | — | 24.9% [19.7%, 30.1%]* (n=240) | 53.9% [47.6%, 60.1%]* (n=240) | 95.1% [90.2%, 99.0%]* (n=68) | 91.7% [87.5%, 94.5%] (n=240) | 9.7 s |
| A1_full | qwen2.5:3b | 240 | 3 | 0.0% [0.0%, 1.6%] (n=240) | 0.0% [0.0%, 1.6%] (n=240) | — | 1.4% [0.1%, 2.9%]* (n=240) | — | 38.8% [32.5%, 44.4%]* (n=240) | 41.0% [35.1%, 47.4%]* (n=240) | 98.0% [91.4%, 99.6%] (n=68) | 92.5% [88.5%, 95.2%] (n=240) | 9.4 s |
| B1L_plain_llm_long | qwen2.5:3b | 240 | 3 | 87.8% [83.9%, 91.4%]* (n=240) | 85.8% [80.9%, 89.7%] (n=240) | 34.4% [29.2%, 39.7%]* (n=240) | — | 97.9% [96.1%, 99.3%]* (n=240) | — | — | — | — | 4.2 s |
| B1_plain_llm | qwen2.5:3b | 240 | 3 | 89.3% [85.7%, 92.6%]* (n=240) | 89.6% [85.1%, 92.8%] (n=240) | 40.4% [34.7%, 46.0%]* (n=240) | — | 98.2% [96.5%, 99.4%]* (n=240) | — | — | — | — | 3.7 s |
| B3L7_rules_in_prompt_7b | qwen2.5:7b | 240 | 3 | 91.5% [88.2%, 94.4%]* (n=240) | 89.6% [85.1%, 92.8%] (n=240) | 57.9% [52.2%, 63.6%]* (n=240) | — | 98.5% [96.8%, 99.7%]* (n=240) | — | — | — | — | 14.6 s |
| B3L_rules_in_prompt_long | qwen2.5:3b | 240 | 3 | 87.9% [83.8%, 91.5%]* (n=240) | 87.9% [83.2%, 91.5%] (n=240) | 78.1% [72.5%, 82.9%]* (n=240) | — | 84.0% [79.7%, 87.9%]* (n=240) | — | — | — | — | 1.8 s |
| B3_rules_in_prompt | qwen2.5:3b | 240 | 3 | 84.6% [79.9%, 88.8%]* (n=240) | 85.4% [80.4%, 89.3%] (n=240) | 76.1% [70.4%, 81.1%]* (n=240) | — | 81.1% [76.4%, 85.7%]* (n=240) | — | — | — | — | 1.9 s |
| M1_qwen2.5-7b | qwen2.5:7b | 240 | 3 | 0.0% [0.0%, 1.6%] (n=240) | 0.0% [0.0%, 1.6%] (n=240) | — | 0.0% [0.0%, 1.6%] (n=240) | — | 78.5% [73.2%, 83.2%]* (n=240) | 10.8% [7.1%, 15.0%]* (n=240) | 99.5% [93.8%, 100.0%] (n=68) | 98.8% [96.4%, 99.6%] (n=240) | 6.6 s |

## DVR per relation (first attempt)

| Run | Relation | All | Non-trivial | Tests the LLM | Trivial checks |
|---|---|---|---|---|---|
| A1N7_no_anchor_7b | MR1 | 2.4% [0.8%, 4.3%]* (n=240) | 7.3% [3.0%, 12.8%]* (n=78) | 7.5% [2.3%, 13.2%]* (n=58) | 162 |
| A1N7_no_anchor_7b | MR2 | 1.0% [0.0%, 2.4%]* (n=240) | 5.6% [0.0%, 13.5%]* (n=42) | 6.1% [0.0%, 14.9%]* (n=38) | 198 |
| A1N7_no_anchor_7b | MR3 | 6.7% [3.9%, 9.7%]* (n=240) | 16.3% [10.2%, 23.1%]* (n=98) | 17.4% [10.5%, 25.2%]* (n=86) | 142 |
| A1N7_no_anchor_7b | MR4 | 7.2% [4.1%, 10.5%]* (n=174) | 29.7% [19.0%, 40.7%]* (n=52) | 20.9% [11.5%, 32.1%]* (n=41) | 139 |
| A1N7_no_anchor_7b | MR5 | 0.0% [0.0%, 1.6%] (n=240) | — | — | 240 |
| A1N7_no_anchor_7b | MR6 | 55.6% [50.5%, 60.3%]* (n=240) | 55.6% [50.5%, 60.3%]* (n=240) | 55.6% [50.5%, 60.3%]* (n=240) | 0 |
| A1N_no_anchor | MR1 | 4.3% [2.1%, 6.9%]* (n=240) | 13.2% [6.8%, 20.5%]* (n=78) | 6.3% [1.7%, 12.6%]* (n=58) | 162 |
| A1N_no_anchor | MR2 | 1.1% [0.1%, 2.5%]* (n=240) | 6.3% [0.8%, 13.5%]* (n=42) | 0.9% [0.1%, 10.7%] (n=38) | 198 |
| A1N_no_anchor | MR3 | 3.9% [1.8%, 6.1%]* (n=240) | 9.5% [4.8%, 15.3%]* (n=98) | 9.7% [4.3%, 15.9%]* (n=86) | 142 |
| A1N_no_anchor | MR4 | 7.3% [4.3%, 10.6%]* (n=174) | 30.2% [19.2%, 41.9%]* (n=52) | 24.2% [13.9%, 35.7%]* (n=41) | 139 |
| A1N_no_anchor | MR5 | 0.0% [0.0%, 1.6%] (n=240) | — | — | 240 |
| A1N_no_anchor | MR6 | 55.8% [51.0%, 60.6%]* (n=240) | 55.8% [51.0%, 60.6%]* (n=240) | 55.8% [51.0%, 60.6%]* (n=240) | 0 |
| A1_full | MR1 | 4.6% [2.2%, 7.4%]* (n=240) | 14.1% [7.7%, 21.8%]* (n=78) | 10.3% [4.0%, 17.2%]* (n=58) | 162 |
| A1_full | MR2 | 2.2% [0.7%, 4.2%]* (n=240) | 12.7% [4.0%, 23.0%]* (n=42) | 9.6% [1.8%, 19.3%]* (n=38) | 198 |
| A1_full | MR3 | 6.0% [3.2%, 8.9%]* (n=240) | 14.6% [8.2%, 21.4%]* (n=98) | 16.7% [9.7%, 24.4%]* (n=86) | 142 |
| A1_full | MR4 | 6.9% [3.9%, 10.3%]* (n=174) | 28.6% [18.0%, 39.3%]* (n=52) | 20.9% [10.6%, 32.0%]* (n=41) | 139 |
| A1_full | MR5 | 0.0% [0.0%, 1.6%] (n=240) | — | — | 240 |
| A1_full | MR6 | 45.1% [40.2%, 50.6%]* (n=240) | 45.1% [40.2%, 50.6%]* (n=240) | 45.1% [40.2%, 50.6%]* (n=240) | 0 |
| M1_qwen2.5-7b | MR1 | 1.0% [0.0%, 2.2%]* (n=240) | 3.0% [0.0%, 6.8%]* (n=78) | 2.3% [0.5%, 10.0%] (n=58) | 162 |
| M1_qwen2.5-7b | MR2 | 0.1% [0.0%, 1.8%] (n=240) | 0.8% [0.1%, 9.8%] (n=42) | 0.9% [0.1%, 10.7%] (n=38) | 198 |
| M1_qwen2.5-7b | MR3 | 4.7% [2.4%, 7.5%]* (n=240) | 11.6% [6.1%, 18.0%]* (n=98) | 13.2% [6.6%, 20.5%]* (n=86) | 142 |
| M1_qwen2.5-7b | MR4 | 1.6% [0.4%, 3.2%]* (n=174) | 6.8% [1.5%, 13.0%]* (n=52) | 2.0% [0.3%, 11.9%] (n=41) | 139 |
| M1_qwen2.5-7b | MR5 | 0.0% [0.0%, 1.6%] (n=240) | — | — | 240 |
| M1_qwen2.5-7b | MR6 | 12.8% [9.4%, 16.8%]* (n=240) | 12.8% [9.4%, 16.8%]* (n=240) | 12.8% [9.4%, 16.8%]* (n=240) | 0 |

## Why first plans were not accepted

Share of audited records whose first plan failed for each reason (a record can have several). 'MR6 only, low-risk menu': the only failure was a wording twin splitting money differently among low-risk products, which leaves suitability unchanged.

| Run | Cause | Share | MR6 only, low-risk menu |
|---|---|---|---|
| A1N7_no_anchor_7b | MR1 | 2.4% [0.8%, 4.3%]* (n=240) | 36.1% [30.1%, 42.1%]* (n=240) |
| A1N7_no_anchor_7b | MR2 | 1.0% [0.0%, 2.4%]* (n=240) |  |
| A1N7_no_anchor_7b | MR3 | 6.7% [3.9%, 9.7%]* (n=240) |  |
| A1N7_no_anchor_7b | MR4 | 7.5% [4.6%, 11.0%]* (n=240) |  |
| A1N7_no_anchor_7b | MR6, all-low-risk menu | 36.9% [31.0%, 42.9%]* (n=240) |  |
| A1N7_no_anchor_7b | MR6, risky options | 32.2% [26.7%, 38.5%]* (n=240) |  |
| A1N7_no_anchor_7b | planner error | 1.7% [0.3%, 3.3%]* (n=240) |  |
| A1N7_no_anchor_7b | rule breaks | 1.7% [0.3%, 3.3%]* (n=240) |  |
| A1N_no_anchor | MR1 | 4.3% [2.1%, 6.9%]* (n=240) | 37.4% [31.4%, 43.6%]* (n=240) |
| A1N_no_anchor | MR2 | 1.1% [0.1%, 2.5%]* (n=240) |  |
| A1N_no_anchor | MR3 | 3.9% [1.8%, 6.1%]* (n=240) |  |
| A1N_no_anchor | MR4 | 7.2% [4.3%, 10.3%]* (n=240) |  |
| A1N_no_anchor | MR6, all-low-risk menu | 38.6% [32.8%, 44.9%]* (n=240) |  |
| A1N_no_anchor | MR6, risky options | 33.5% [27.6%, 39.4%]* (n=240) |  |
| A1N_no_anchor | planner error | 1.8% [0.6%, 3.5%]* (n=240) |  |
| A1N_no_anchor | rule breaks | 1.8% [0.6%, 3.5%]* (n=240) |  |
| A1_full | MR1 | 4.6% [2.2%, 7.4%]* (n=240) | 25.8% [20.7%, 31.4%]* (n=240) |
| A1_full | MR2 | 2.2% [0.7%, 4.2%]* (n=240) |  |
| A1_full | MR3 | 6.0% [3.2%, 8.9%]* (n=240) |  |
| A1_full | MR4 | 6.8% [3.9%, 10.0%]* (n=240) |  |
| A1_full | MR6, all-low-risk menu | 26.7% [21.2%, 32.2%]* (n=240) |  |
| A1_full | MR6, risky options | 31.1% [25.7%, 37.1%]* (n=240) |  |
| A1_full | planner error | 1.4% [0.1%, 2.9%]* (n=240) |  |
| A1_full | rule breaks | 1.4% [0.1%, 2.9%]* (n=240) |  |
| M1_qwen2.5-7b | MR1 | 1.0% [0.0%, 2.2%]* (n=240) | 5.4% [2.9%, 8.3%]* (n=240) |
| M1_qwen2.5-7b | MR2 | 0.1% [0.0%, 1.8%] (n=240) |  |
| M1_qwen2.5-7b | MR3 | 4.7% [2.4%, 7.5%]* (n=240) |  |
| M1_qwen2.5-7b | MR4 | 1.8% [0.4%, 3.6%]* (n=240) |  |
| M1_qwen2.5-7b | MR6, all-low-risk menu | 5.4% [2.9%, 8.3%]* (n=240) |  |
| M1_qwen2.5-7b | MR6, risky options | 12.5% [8.8%, 16.9%]* (n=240) |  |

## Baseline ALLOCATION block

Answers that ended with a parsable block (judged on it), and blocks that named a product the oracle recognises (otherwise products come from the text).

| Run | Block present | Block names products |
|---|---|---|
| B1L_plain_llm_long | 59.3% [53.8%, 64.9%]* (n=240) | 25.6% [20.6%, 30.7%]* (n=240) |
| B1_plain_llm | 64.6% [59.2%, 70.0%]* (n=240) | 32.1% [26.8%, 37.6%]* (n=240) |
| B3L7_rules_in_prompt_7b | 86.9% [83.3%, 90.7%]* (n=240) | 76.5% [71.8%, 80.8%]* (n=240) |
| B3L_rules_in_prompt_long | 84.0% [79.7%, 88.2%]* (n=240) | 71.7% [66.5%, 76.7%]* (n=240) |
| B3_rules_in_prompt | 81.8% [77.1%, 86.4%]* (n=240) | 67.2% [61.4%, 72.8%]* (n=240) |

Each answer judged on its block is also read as free text. The share on which the two readings give the same verdict is a consistency check of the readers, not a measure of their accuracy (the text contains the block and both use the same product names).

| Run | Answers read twice | Same verdict: unsuitable product | Same verdict: overspend |
|---|---|---|---|
| B1L_plain_llm_long | 184 | 99.5% [94.4%, 99.9%] (n=80) | 87.0% [78.8%, 94.0%]* (n=80) |
| B1_plain_llm | 231 | 100.0% [96.3%, 100.0%] (n=99) | 87.0% [80.2%, 92.8%]* (n=99) |
| B3L7_rules_in_prompt_7b | 551 | 97.3% [95.3%, 98.9%]* (n=210) | 96.9% [94.6%, 98.8%]* (n=210) |
| B3L_rules_in_prompt_long | 516 | 98.6% [96.9%, 99.8%]* (n=191) | 83.7% [78.1%, 88.5%]* (n=191) |
| B3_rules_in_prompt | 484 | 98.8% [97.3%, 99.8%]* (n=174) | 79.8% [74.1%, 85.4%]* (n=174) |

## Personalisation and what drives the risky share

Personalisation: mean pairwise weighted Jaccard similarity of the plans different personas received (replicate 0; lower is more personalised, 1.0 means one plan for everyone). Surrogate: a ridge model of the plan's risky share on the persona's features; the shares say how much of the explained variation sits on capacity features (savings months, EMI share, cover, card dues, costly loans) versus willingness features (questionnaire score, experience). FC is the feature concentration (sum of squared importances).

| Run | Plan similarity | Personas | Surrogate R² | Capacity share | Willingness share | Other | FC |
|---|---|---|---|---|---|---|---|
| A1N7_no_anchor_7b | 0.32 [0.31, 0.35] | 173 | 0.24 | 0.37 | 0.28 | 0.35 | 0.11 |
| A1N_no_anchor | 0.42 [0.39, 0.45] | 173 | 0.19 | 0.40 | 0.28 | 0.32 | 0.11 |
| A1_full | 0.43 [0.40, 0.47] | 173 | 0.30 | 0.36 | 0.28 | 0.36 | 0.11 |
| B1L_plain_llm_long | 0.36 [0.29, 0.46] | 62 | -0.03 | 0.51 | 0.12 | 0.37 | 0.12 |
| B1_plain_llm | 0.50 [0.40, 0.60] | 64 | -0.03 | 0.50 | 0.08 | 0.42 | 0.13 |
| B3L7_rules_in_prompt_7b | 0.16 [0.15, 0.18] | 185 | 0.29 | 0.22 | 0.51 | 0.27 | 0.16 |
| B3L_rules_in_prompt_long | 0.49 [0.45, 0.53] | 166 | 0.09 | 0.29 | 0.19 | 0.53 | 0.14 |
| B3_rules_in_prompt | 0.46 [0.42, 0.51] | 162 | 0.05 | 0.39 | 0.17 | 0.44 | 0.13 |
| M1_qwen2.5-7b | 0.44 [0.41, 0.49] | 173 | 0.37 | 0.36 | 0.28 | 0.36 | 0.11 |

## Provenance

| Run | Commit | Config hash | Rule check | Traceable |
|---|---|---|---|---|
| A1N7_no_anchor_7b | 448618a9f1 | eae08f5adc | rule-check-v3 | yes |
| A1N_no_anchor | 448618a9f1 | fd9657d6ee | rule-check-v3 | yes |
| A1_full | dd47d58259 | dc7207e958 | rule-check-v3 | yes |
| B1L_plain_llm_long | 448618a9f1 | 1e499a1e3f | rule-check-v3 | yes |
| B1_plain_llm | e5caa155c6 | 998e1089ea | rule-check-v3 | yes |
| B3L7_rules_in_prompt_7b | 448618a9f1 | 286bfae3e6 | rule-check-v3 | yes |
| B3L_rules_in_prompt_long | 448618a9f1 | 09116fb1d5 | rule-check-v3 | yes |
| B3_rules_in_prompt | e5caa155c6 | dc90a05f80 | rule-check-v3 | yes |
| M1_qwen2.5-7b | e5caa155c6 | 7eea6b61cb | rule-check-v3 | yes |

## Paired comparisons with A1_full (McNemar, exact, replicate 0)

Holm-adjusted p-values are corrected over every test in this table.

| Run | Metric | Personas | Only reference | Only this run | p | p (Holm) |
|---|---|---|---|---|---|---|
| A1N7_no_anchor_7b | unsuitable | 240 | 0 | 0 | 1 | 1 |
| A1N_no_anchor | unsuitable | 240 | 0 | 0 | 1 | 1 |
| B1L_plain_llm_long | unsuitable | 240 | 0 | 206 | 1.94e-62 | 9.72e-62 |
| B1_plain_llm | unsuitable | 240 | 0 | 215 | 3.8e-65 | 3.04e-64 |
| B3L7_rules_in_prompt_7b | unsuitable | 240 | 0 | 215 | 3.8e-65 | 3.04e-64 |
| B3L_rules_in_prompt_long | unsuitable | 240 | 0 | 211 | 6.08e-64 | 3.65e-63 |
| B3_rules_in_prompt | unsuitable | 240 | 0 | 205 | 3.89e-62 | 1.56e-61 |
| M1_qwen2.5-7b | unsuitable | 240 | 0 | 0 | 1 | 1 |
