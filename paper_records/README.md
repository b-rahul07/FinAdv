# Run records behind the paper

`final-2026-11-14/` holds every record of the 18 reported runs: 240 synthetic personas × 3 replicates per run, and
300 adversarial turns. They are compressed with xz (`xz -dk *.xz`, or Python's `lzma`). Each record stores:
- the persona's facts;
- the configuration and its hash;
- the git commit;
- the model's identity (tag, digest, quantisation, seed);
- the raw model text, the plans, the audit trail and the latency.

| File | What it is |
|---|---|
| `*.jsonl.xz` | one file per run (`experiments/configs/paper/<run>.yaml`). Every persona is synthetic. |
| `STD_standard_mix.jsonl.xz` | the pipeline with no model (`experiments/configs/analysis/STD_standard_mix.yaml`) |
| `report.json`, `report.md` | `python -m experiments.report <records> --reference A1_full --out report.md` |
| `analysis.json` | `python -m experiments.analysis <dir> STD_standard_mix.jsonl` (`docs/PAPER_PLAN.md` §9) |
| `checks/` | `experiments.sebi_check --live` (rules-v2 and rules-v2-unsecured) and `experiments.rules_rework` |

`followup-2026-11-15/` holds the five follow-up runs from the draft review (`docs/PAPER_PLAN.md` §9). They are B1L and
B3L (a 1,200-token answer budget), B3L7 (rules in the prompt, qwen2.5 7B), B1L14 and B3L14 (qwen2.5 14B), and A1N and A1N7 (no standard mix as a
starting point, 3B and 7B). Their `report.json` and `analysis.json` also include A1, B1, B3 and M1 7B for comparison.
Those four runs' records are in `final-2026-11-14/`.

The third review (17 Nov 2026, `docs/PAPER_PLAN.md` §11) added:
- **`followup-2026-11-15/A1H_full_horizon`**: A1 on the corrected planner (`pipeline-v4-horizon`), from Kaggle
  session 5, commit d48d4b6.
- **`followup-2026-11-15/X1_extract_*`**: fact extraction with qwen2.5 3B and phi4-mini (laptop CPU, commits 072abc9
  and d48d4b6, which have the same code) and qwen2.5 7B (Kaggle). They are summarised in `extraction.json` by
  `python -m experiments.extract_report <dir>`.
- **`followup-2026-11-15/X2_extract_*`** (18 Nov 2026): fact extraction with prompt v2, which names the fields. 3B ran
  on a Kaggle CPU session (6d26647), 7B on a teammate's Kaggle account (1c4d347), and phi4-mini on the laptop (9a34fb3
  and 1c4d347, same code). `extraction.json` summarises X1 and X2.
- **`followup-2026-11-15/X3_extract_*`** (19 Nov 2026): the held-out test of extraction prompt v3 on 240 fresh
  personas (`experiments/data/personas_heldout_s8.jsonl`, seed 8). 3B ran on our Kaggle (117eb8f); phi4-mini and 7B ran
  on a teammate's Kaggle (7e5c9d6). `extraction.json` rescores X1--X3 with scoring v2 (an empty loan list reads as 0 EMIs).
- **`final-2026-11-14/projection.json`**: the generate-then-filter baseline P1, from
  `python -m experiments.projection <A2 records> <dir>`. No model is called.
- **`final-2026-11-14/STD_standard_mix_horizon.jsonl.xz`**: the standard mix on the corrected planner.

To re-derive every table and figure in the paper:
```bash
cd paper_records/final-2026-11-14 && xz -dk *.xz && cd ../..
python -m experiments.report $(ls paper_records/final-2026-11-14/*.jsonl | grep -v STD_) --reference A1_full --out /tmp/report.md
python -m experiments.paper_assets paper_records/final-2026-11-14 --followup paper_records/followup-2026-11-15 \
    --std-horizon paper_records/final-2026-11-14/STD_standard_mix_horizon.jsonl --out /tmp/paper_assets
```
Some records were written before the repository's history was edited on 12 Nov 2026. Those carry earlier commit
ids; `experiments/commit_aliases.json` maps them to today's ids.
