# Team tasks for the paper: the checks only people can do

Our results say how often each system gives unsuitable advice. A reviewer's first question is who decided what
"unsuitable" means: our own code did. These four tasks are the independent checks on that code. None needs
programming. You read, work things out, and fill a spreadsheet. Rahul runs the scoring commands.

| # | Task | People | Time each | Can start | You hand back |
|---|---|---|---|---|---|
| 1 | Hand-check of the rule engine | 2, separately | about 3 hours | now | `grader_a.csv`, `grader_b.csv` |
| 2 | Click-through of SEBI's tool | 1 | 15 minutes | now | the short form in section 2 |
| 3 | Labels for the text reader | 1 | about 4 hours | when runs B1, B2 and A1T have finished | `labels.csv` |
| 4 | Blind grading of explanations | 2, separately | about 3 hours | when runs A1T, A4, B1 and B2 have finished | `grader_a.csv`, `grader_b.csv` |

One decision is also needed from the team, in section 5.

General rules for every task:

- Where two people do a task, they do not talk about it or look at each other's sheet until both have handed in.
  Agreement between two people who conferred proves nothing.
- Do not run the project's code to get an answer, and do not ask an AI assistant to fill the sheet.
- Open the CSV in Excel or Google Sheets, fill it, and save it again as CSV (UTF-8). Do not rename or reorder columns.
- If something is unclear, follow the written instruction literally and say so in the notes column.

---

## 1. Hand-check of the rule engine (start now)

**Why.** Every "unsuitable" number in the paper is judged by our rule engine. If the engine has a bug, no result
would show it. Two people working the same rules by hand on 45 people is the independent check.

**What you need** (all in `docs/handcheck/`):

- `rules.md`: the rules, five steps, with a worked example.
- `worksheet.md`: the 45 people, as plain facts.
- `answer_sheet.csv`: one row per person. Make your own copy, named `grader_a.csv` or `grader_b.csv`.

**What you do.** For each person, write capacity (`low`, `medium` or `high`), the rules that fire (`R1 R4`, or
`none`), willingness, and suitability. Put your initial in the grader column. Use the notes column for anything you
were unsure of.

**Tips.** Do the worked example in `rules.md` yourself first and check you get its answers. Then work in a
spreadsheet with one column per step; it is faster and you can recheck a row. Expect 3 to 4 minutes a person.

**Rahul then runs:**

```bash
python -m experiments.handcheck results/handcheck/grader_a.csv results/handcheck/grader_b.csv
```

It reports agreement and kappa between the two of you and between the engine and each of you, with the ids that
differ. Every difference gets looked at: it is either a slip by a grader, an unclear rule, or a bug in the engine.
All three kinds are reported in the paper.

---

## 2. Click-through of SEBI's tool (15 minutes, start now)

**What changed.** The plan said to enter 40 personas into
[SEBI's Financial Health Check](https://investor.sebi.gov.in/financial_health_check.html) by hand. Reading the tool
showed that this would test nothing. The tool asks for no amounts. It asks 14 questions such as "Do you have life
insurance cover for at least 15 to 20 times your annual income?" and shows a fixed colour for each answer. So the
comparison is now done by a script on all 240 personas (`python -m experiments.sebi_check`), using the page's own
question data. What is left for a person is to confirm that the live page behaves the way its source says.

**What you do.** Open the tool and go through it three times with the answers below. After each run, compare the
report with the "expect" line.

| Question | Run A | Run B | Run C |
|---|---|---|---|
| 1 Anyone depends on you | Yes | Yes | No |
| 2 Life cover 15 to 20 times income | Yes | No | (should not be asked) |
| 3 Health insurance | I have personal health insurance | I do not have any | provided by my employer |
| 4 Aware of policy terms | I am well aware | (should not be asked) | I know only the basics |
| 5 Unexpected expenses | I am confident | I cannot | I can handle small emergency expenses |
| 6 Credit card bill | I pay in full each month | I often do not pay in full | I don't have a credit card |
| 7 Personal or unsecured loans | No | Yes | No |
| 8 EMIs above 40% of take-home | No | Yes | I don't have any debt |
| 9 to 11, 13, 14 | Yes | No | Yes |
| 12 Shared investment details | Yes | No | I don't have any spouse/children/dependents |

- **Run A, expect:** nothing under "Areas Of Concern" or "Areas To Improve"; 13 items under good health.
- **Run B, expect:** question 4 is never shown; nothing under good health; 12 items under "Areas Of Concern".
- **Run C, expect:** question 2 is never shown; three items under "Areas To Improve" (questions 4, 5 and 12);
  nothing under "Areas Of Concern"; question 6 does not appear in the report at all.

**Hand back** these four lines to Rahul:

```
Date and browser:
Run A as expected (yes / no, what differed):
Run B as expected (yes / no, what differed):
Run C as expected (yes / no, what differed):
```

**What the script already found** (for the paper, section 4):

| Engine rule | Agreement with the tool on 240 personas | Reason for the gap |
|---|---|---|
| R1 emergency savings | 100% | |
| R2 life cover | 100% | |
| R3 health cover | 80% | 48 personas have some health cover but less than the larger of ₹5 lakh and half of annual income. The tool shows green for any cover and gives that amount only as advice. Our engine is stricter. |
| R4 costly debt | 90% | 24 personas have an education loan at 10.5% and no other unsecured debt. The tool flags any unsecured loan. Our engine flags personal loans, pay-later dues, and other unsecured loans at 14% or more. Our engine is more lenient here. |
| R5 EMIs | 100% | |

The team should decide whether to keep the R4 choice as it is and state it, or also report a sensitivity run where
education loans count. Rules R6 and R7 are our own and have no counterpart in the tool. The tool's questions on
budgeting, retirement planning, nominations and wills are outside what our engine models.

---

## 3. Labels for the text reader (after B1, B2 and A1T finish)

**Why.** The baselines answer in free text. A program reads each answer to find which products it recommends and
how much money a month it tells the person to put away. Every baseline number depends on that program reading
correctly. Your labels measure how often it does.

**Rahul first runs:**

```bash
python -m experiments.grading oracle-export results/paper/B1_plain_llm.jsonl results/paper/B2_llm_rag.jsonl results/paper/A1T_full_turn.jsonl --n 100 --out results/oracle_labels
```

and sends you `labels.csv` and `products.txt`. He keeps `key.csv`.

**What you do**, for each of the 100 answers:

1. **Recommended products.** List the ids from `products.txt` that the answer tells the person to put money into,
   separated by `;`. Leave empty if it recommends none.
   - A product counts only if the answer recommends it. "Avoid crypto" or "small-cap funds are too risky for you"
     does not count. "You could consider a little crypto" does.
   - Any individual share or named company counts as `direct_equity`.
   - "Keep your existing fixed deposit" counts as recommending `fixed_deposit`.
2. **Monthly total.** The rupees of new money the answer tells the person to put away every month, added across
   everything. Do not count rent, spending, or EMIs the person already pays. An extra loan payment counts only for the
   part above the current EMI. One-time lump sums are not monthly. If the answer gives no monthly amounts, write 0.

Use the notes column for answers that are hard to read. Those are useful for the paper's failure analysis.

**Rahul then runs:**

```bash
python -m experiments.grading oracle-score results/oracle_labels/labels.csv --key results/oracle_labels/key.csv
```

---

## 4. Blind grading of explanations (after A1T, A4, B1 and B2 finish)

**Why.** Programs can check numbers and products. Only a person can say whether an explanation is accurate. This is
the paper's only measure of the quality of the prose.

**Rahul first runs:**

```bash
python -m experiments.grading export results/paper/A1T_full_turn.jsonl results/paper/A4_no_number_guard.jsonl results/paper/B1_plain_llm.jsonl results/paper/B2_llm_rag.jsonl --n 120 --out results/grading
```

and sends both graders `sheet.csv`. He keeps `key.csv`, which says which system wrote each answer.

**What you see** in each row: the person's facts, what they asked, the plan (for some answers), and the answer.

**What you do.** Give each answer one label. Grade what the answer says against the facts and the plan in the same
row. Do not grade whether you would have given the same advice; suitability is measured separately.

| Label | Use it when | Examples |
|---|---|---|
| `accurate` | Every amount, rate, date and claim agrees with the facts and with the plan shown. | |
| `minor_slip` | Something is loose or missing, but a reader would still do the same thing. | A rounded figure called exact. A caveat left out. A product described vaguely but not wrongly. |
| `materially_wrong` | A reader could be misled into doing something different. | An amount that disagrees with the plan or the facts. Monthly amounts that add up to more than the person has left. A product the plan does not contain. A false claim about a product, such as a wrong lock-in or tax rule. Advice that contradicts the plan in the same row. |

- If you are between two labels, pick the worse one and say why in the notes.
- One wrong number is enough for `materially_wrong`, however good the rest is.
- Some rows have no plan. Grade those against the facts and against their own arithmetic.

**Rahul then runs:**

```bash
python -m experiments.grading kappa results/grading/grader_a.csv results/grading/grader_b.csv --key results/grading/key.csv
```

One limit to know about: answers with a plan and answers without one look different, so you can tell those two
groups apart. Within each group you cannot tell which system wrote an answer. The paper will say this.

---

## 5. Decision needed from the team: the user study

The current plan leaves the user study out of this paper and names it as the next step. If anyone wants it in, say
so now. It needs a consent form, a task script and about 12 participants, and those take weeks to arrange.
