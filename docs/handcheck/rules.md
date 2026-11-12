# Hand-check rules (rules-v2, gl13-in-v1)

You are checking our rule engine by working the same rules out by hand. For each person on the worksheet, write four answers in your copy of the answer sheet: capacity, rules fired, willingness, suitability.

## Before you start

- Work alone. Do not compare with the other grader until both sheets are handed in.
- Do not run the project's code and do not open `experiments/data/personas_v1.jsonl`; it holds the engine's answers.
- A calculator or a spreadsheet for the arithmetic is fine.
- If a rule seems unclear for a person, apply it as written here and say so in the notes column. Those notes are results too.
- Do not round before comparing with a limit. Exactly on a limit: read the wording ("below", "above", "at least").

## Step 1: five scores, each from 0 to 1

1. **Emergency.** Months = emergency savings ÷ monthly expenses. Score = months ÷ 6, but never above 1.
2. **EMIs.** Share = all EMIs added together ÷ monthly take-home. Score = 1 if the share is 40% or less; otherwise 0.40 ÷ share.
3. **Life cover.** With no dependants the score is 1. Otherwise score = life cover ÷ (15 × annual take-home), never above 1. Annual take-home is 12 × monthly take-home.
4. **Health cover.** Needed = the larger of ₹5,00,000 and 50% of annual take-home. Score = health cover ÷ needed, never above 1.
5. **Costly debt.** Score = 0 if the credit-card bill is not paid in full every month, or the person has a personal loan or pay-later (BNPL) dues, or has any other loan without security (education loan, other loan) at 14% a year or more. Otherwise 1. Home, car, gold and two-wheeler loans are secured and never count here. A credit-card balance in the loans list does not count by itself; only the "paid in full" line does.

## Step 2: capacity

Capacity score = the smallest of the five scores. **Low** if it is below 0.5; **High** if it is exactly 1 (all five scores are 1); otherwise **Medium**.

## Step 3: rules fired

- **R1** months of emergency savings below 6.
- **R2** life-cover score below 1.
- **R3** health-cover score below 1.
- **R4** costly-debt score is 0.
- **R5** EMI share above 40%.
- **R6** capacity is Low, or investing experience is "none".
- **R7** any goal less than 3 years away.

Write them as `R1 R4 R7`. If no rule fires, write `none` (an empty cell counts as not answered).

## Step 4: willingness

Look up each questionnaire answer in the table and add the thirteen numbers (questions 9 and 10 are both added).

| Question | a | b | c | d |
|---|---|---|---|---|
| 1 | 4 | 3 | 2 | 1 |
| 2 | 1 | 2 | 3 | 4 |
| 3 | 1 | 2 | 3 | 4 |
| 4 | 1 | 2 | 3 | – |
| 5 | 1 | 2 | 3 | – |
| 6 | 1 | 2 | 3 | 4 |
| 7 | 1 | 2 | 3 | 4 |
| 8 | 1 | 2 | 3 | 4 |
| 9 | 1 | 3 | – | – |
| 10 | 1 | 3 | – | – |
| 11 | 1 | 2 | 3 | 4 |
| 12 | 1 | 2 | 3 | – |
| 13 | 1 | 2 | 3 | 4 |

Total 22 or less is **Low**; 23 to 28 is **Medium**; 29 or more is **High**. If investing experience is "none", willingness is at most Medium.

## Step 5: suitability

Suitability = the lower of capacity and willingness.

## Worked example (this person is not on the sheet)

- Take-home ₹80,000 a month · expenses ₹40,000 a month · emergency savings ₹1,60,000
- Dependants 2 · life cover ₹1,00,00,000 · health cover ₹5,00,000
- Loans: car loan, ₹4,00,000 outstanding at 9.5% a year, EMI ₹12,000 a month; education loan, ₹3,00,000 outstanding at 9% a year, EMI ₹8,000 a month
- Credit-card bill paid in full every month: yes
- Goals: Car in 2 years; Retirement in 25 years
- Investing experience: beginner
- Questionnaire answers: 1 b · 2 c · 3 b · 4 c · 5 b · 6 c · 7 b · 8 c · 9 b · 10 b · 11 b · 12 b · 13 b

1. Emergency: 1,60,000 ÷ 40,000 = 4 months; score 4 ÷ 6 = 0.67.
2. EMIs: 12,000 + 8,000 = 20,000; share 20,000 ÷ 80,000 = 25%; score 1.
3. Life cover: annual take-home 9,60,000; needed 15 × 9,60,000 = 1,44,00,000; score 1,00,00,000 ÷ 1,44,00,000 = 0.69.
4. Health cover: needed = larger of 5,00,000 and 4,80,000 = 5,00,000; score 1.
5. Costly debt: card paid in full, no personal loan, education loan at 9% (under 14%); score 1.

Capacity score = 0.67, so capacity is **Medium**. Rules: R1 (4 months), R2 (life score below 1), R7 (car in 2 years); R6 does not fire (capacity is not Low, experience is not "none"). Questionnaire: 3+3+2+3+2+3+2+3+3+3+2+2+2 = 33, so willingness is **High**. Suitability = lower of Medium and High = **Medium**.

Answer-sheet row: `medium`, `R1 R2 R7`, `high`, `medium`.
