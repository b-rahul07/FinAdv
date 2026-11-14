Rules: rules-v2-unsecured

Tool: https://investor.sebi.gov.in/financial_health_check.html, read 2026-11-12 (page sha256 6f6075094e48…).

| Rule | The tool flags it when | Both flag | Both pass | Engine only | Tool only | Agreement |
|---|---|---|---|---|---|---|
| R1 | question 5 not green (the fund is under six months of expenses) | 93 | 147 | 0 | 0 | 100.0% |
| R2 | question 2 red (dependants, and life cover under 15 times annual income) | 52 | 188 | 0 | 0 | 100.0% |
| R3 | question 3 red (no health insurance) | 28 | 164 | 48 | 0 | 80.0% |
| R4 | question 6 red (card bill not paid in full) or question 7 red (a personal or unsecured loan) | 68 | 172 | 0 | 0 | 100.0% |
| R5 | question 8 red (EMIs above 40% of take-home pay) | 51 | 189 | 0 | 0 | 100.0% |

- R3, 48 personas: has health cover, but under the larger of ₹5 lakh and half of annual take-home: the tool colours any cover green and gives that amount only as advice; the engine uses the amount as the pass mark. (S7-003, S7-011, S7-015, S7-030, S7-031, S7-038…)
- No mismatch outside the stated design choices.

Against rules-v2, of 240 personas: capacity level changes for 18, the rules fired for 24, suitability for 12 {'medium -> low': 7, 'high -> low': 5}.
