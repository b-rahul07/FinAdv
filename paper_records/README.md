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
B3L (a 1,200-token answer budget), B3L7 (rules in the prompt, qwen2.5 7B), and A1N and A1N7 (no standard mix as a
starting point, 3B and 7B). Their `report.json` and `analysis.json` also include A1, B1, B3 and M1 7B for comparison.
Those four runs' records are in `final-2026-11-14/`.

To re-derive every table and figure in the paper:
```bash
cd paper_records/final-2026-11-14 && xz -dk *.xz && cd ../..
python -m experiments.report $(ls paper_records/final-2026-11-14/*.jsonl | grep -v STD_) --reference A1_full --out /tmp/report.md
python -m experiments.paper_assets paper_records/final-2026-11-14 --followup paper_records/followup-2026-11-15 --out /tmp/paper_assets
```
Some records were written before the repository's history was edited on 12 Nov 2026. Those carry earlier commit
ids; `experiments/commit_aliases.json` maps them to today's ids.
