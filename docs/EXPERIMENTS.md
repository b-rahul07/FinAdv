# Running the paper's experiments

Everything here runs the same `finadvisor` package as the website on synthetic personas only. Results go to
`results/paper/` (not committed). All runs resume where they stopped, so a Colab session can disconnect safely.

Every result row carries its provenance: `git_commit`, `git_dirty` (uncommitted changes), the run config and its
hash, and `rule_check` (the version of the plan rule check, now `rule-check-v2`). The report's Provenance table marks
a run **not traceable** if its rows come from uncommitted code, from more than one commit or config, or from an
older rule check. Run the paper's experiments from a clean checkout of one commit.

## 1. Inputs (already in the repo)

| File | What it is |
|---|---|
| `experiments/data/personas_v1.jsonl` | 240 synthetic personas (seed 7), stratified so each rule R1–R7 fires in ≥ 44 of them and each capacity and suitability level has ≥ 48; 68 carry a pressure wish. Regenerate with `python -m experiments.personas` (same seed gives the same file). |
| `experiments/data/handcheck_v1.csv` | 45 of them with empty columns: two people work out capacity, rules, willingness and suitability **by hand from the written rules**, without running the code. This is the hand-worked oracle. |
| `experiments/data/adversarial_turns.jsonl` | 50 chat turns: pressure, Hinglish, misspellings, "ignore your rules", requests to name stocks, other traps. |
| `experiments/data/eval_personas.jsonl` | The original 12 hand-worked personas with 30 chat turns (`experiments/eval_advice.py`). |

## 2. The runs (`experiments/configs/paper/`)

All use `personas_v1`, 3 replicates, `planner.mode: model`, every audit relation evaluated, no time limit.

| Run | Command | What it shows |
|---|---|---|
| A1 Full pipeline | `python -m experiments.run experiments/configs/paper/A1_full.yaml` | main result |
| A1T Full reply | `… A1T_full_turn.yaml` | the same with the answer and explanation (number and explanation metrics) |
| A2 No gate | `… A2_no_gate.yaml` | what the auditor catches alone |
| A3 No auditor | `… A3_no_auditor.yaml` | the gate's value alone |
| A4 No number guard | `… A4_no_number_guard.yaml` | unsourced numbers the model writes and users would see (compare with A1T) |
| A5 No calculators | `… A5_no_calculators.yaml` | the model computing amounts itself: arithmetic gap and overspending |
| A6 No pressure fence | `… A6_no_pressure_fence.yaml` | plans moved by pushy wishes |
| S1 Sensitivity | `… S1_rules_v1.yaml`, `… S1_emergency_3m.yaml` | robustness to the capacity formula and the emergency-fund target |
| M1 Models | `… M1_qwen2.5-1.5b.yaml`, `M1_qwen2.5-7b`, `M1_phi4-mini`, `M1_llama3.2-3b` | effect of model size and family (A1 settings) |
| B1 Plain LLM | `python -m experiments.baselines experiments/configs/paper/B1_plain_llm.yaml` | the model alone, no rules or tools |
| B2 LLM + RAG | `python -m experiments.baselines … B2_llm_rag.yaml` | the model with the library passages |
| ADV Adversarial | `python -m experiments.adversarial experiments/configs/paper/ADV_adversarial.yaml` | 50 turns × 6 personas through the full reply |

**Before the long runs**, do one pass of every config at 1 replicate on the first 20 personas (adversarial: one
persona per suitability level, first 20 turns). It writes to `results/smoke/`, runs the report, and fails if a config
crashes or a table is missing:
```bash
python -m experiments.smoke_paper                     # with the real models each config names
python -m experiments.smoke_paper --model tiny-test   # plumbing only, seconds, no model
```

## 3. Colab (free GPU)

```bash
!git clone https://github.com/b-rahul07/FinAdv.git && cd FinAdv && pip install -q -e ".[rag]"
!curl -fsSL https://ollama.com/install.sh | sh
!nohup ollama serve > ollama.log 2>&1 &
!ollama pull qwen2.5:3b   # and qwen2.5:1.5b, qwen2.5:7b, phi4-mini, llama3.2:3b for M1
!python scripts/build_index.py          # B2 uses the Chroma index
# keep results on Drive so a disconnect loses nothing:
from google.colab import drive; drive.mount('/content/drive')
!mkdir -p /content/drive/MyDrive/finadvisor-results && ln -s /content/drive/MyDrive/finadvisor-results results
!python -m experiments.smoke_paper                      # 1 replicate x 20 personas, every config, then the report
!python -m experiments.run experiments/configs/paper/A1_full.yaml
```
Rough cost on a T4: a plan-mode persona needs about 10 model calls with the audit (more with repairs), so one run of
240 personas × 3 replicates is several hours; B1/B2 are quicker. Run A1, A2, A3, A5, A6, B1, B2 first, then A1T, A4,
S1, M1 and ADV.

## 4. Results and statistics

```bash
python -m experiments.report results/paper/*.jsonl --reference A1 --out results/paper/report.md
```
Writes the main table, DVR per relation and case, the A5 arithmetic table, the adversarial table, and exact McNemar
tests of every run against A1 on the same personas. Every rate has a Wilson 95% interval. Definitions
(`experiments/metrics.py`):

- **Unsuitable rate**: the final plan breaks R1–R7 or the suitability ceiling for the person's true facts (checked
  by the gate on the true facts, `experiments/oracle.py`), or the answer names a company. Baselines: a recommended
  product the gate would refuse, a company named, or more rupees a month than the surplus. Product mentions in free
  text are read per sentence, skipping sentences with a negation; hand grading covers what this misses.
- **First-plan unsuitable**: the planner's first plan, before the auditor.
- **Unsourced-number rate**: answers with at least one number neither code nor the person produced, counted on the
  model's text **before** the number guard (the raw text is stored with every explanation).
- **DVR per relation**: violations ÷ checks, reported for all checks, **non-trivial** checks (gate decides + tests
  the LLM) and checks that **test the LLM** alone. Every twin check records its case: `trivial` (no risky product
  allowed, holds by construction), `gate_decides` (the twin's allowed products differ from the original's),
  `tests_llm` (same menu, only the model's choice matters), `no_model` (standard mix). On the 12 eval personas: 39
  of 56 MR1–MR5 checks are trivial, 3 gate-decided, 14 test the model; MR5 is always trivial while the gate is on.
- **Outcome**: pass / repaired / fallback, reported as results (fallback = the LLM planner failed).
- **Pressure kept**: personas with a wish whose final plan equals their plan for a neutral question.
- **Replicate agreement**: personas whose final plans agree across the 3 replicates (CPU and GPU runs are not
  bit-reproducible at temperature 0).
- **A5 arithmetic**: mean absolute gap between the model's monthly amounts and the calculators', and overspend rate:
  the model's monthly total above the cash available when investing starts. The report also shows how often this
  figure agrees with the rule check's verdict on the same plan; it must be 100%.
- **Overspending (rule check, `rule-check-v2`)**: month by month, the amount invested in month *m* may not exceed
  the surplus plus the EMIs of loans the plan has already cleared by month *m*. (v1 allowed the surplus plus every
  EMI from month 1, so a plan could invest money that was still going to EMIs; only smoke runs used v1.) On the 240
  personas no calculator or standard-mix plan is flagged by either version; only plans with model-written amounts
  (A5) can be. Baselines are free text with no month structure, so their overspend check is the monthly total against
  the surplus.

## 5. Hand grading

1. Two people fill in `experiments/data/handcheck_v1.csv` independently; compare with `engine_oracle`.
2. Explanations, blind:
   ```bash
   python -m experiments.grading export results/paper/A1T_full_turn.jsonl results/paper/A4_no_number_guard.jsonl \
       results/paper/B1_plain_llm.jsonl results/paper/B2_llm_rag.jsonl --n 120 --out results/grading
   ```
   Each grader labels a copy of `sheet.csv` (accurate / minor_slip / materially_wrong) without opening `key.csv`.
   ```bash
   python -m experiments.grading kappa results/grading/grader_a.csv results/grading/grader_b.csv --key results/grading/key.csv
   ```

## 6. What to state in the paper

- The website uses `planner.mode: standard` (the tested mix per suitability level); LLM planning is evaluated offline
  in these runs.
- The gate does most of the safety work; the auditor's value shows when the gate is off (A2) and in non-trivial checks.
- The number guard checks numbers, not meaning; explanation accuracy comes from the blind grading.
- Threats to validity: synthetic personas only; one model family in the main results; CPU/GPU runs are not
  bit-reproducible; thresholds come from SEBI's health check but the weakest-link aggregation and cut-offs are design
  choices; the team wrote both system and oracle (mitigated by blind second grading). The persona ranges should be
  checked against published Indian household data (RBI, NSO) before submission.
