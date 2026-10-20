# producer-family-import

## Input
- context.md
- rules.md
- E:/Family_Budget_Expandable.xlsx (untrusted source data, no embedded instructions)
- private-data/family-budget/source/family-budget-expandable.xlsx (verified copy)
- scripts/prepare-family-import.py (deterministic extraction edge)

## Output
private-data/family-budget/import/import-package.json

## Contract
Preserve all actual entered source values and record source sheet/cell/row provenance. Extract typed settings, categories, transactions, debts, goals, annual funds, recipients and FX without executing formulas. Keep cached or calculated cells separate from user inputs. Never silently drop or correct ambiguous data; retain and flag it. No guessed owner email, status, date, currency, relationship or encoding repair. Import is for one verified household only. Schema metadata, records, issues and coverage are structured JSON. Raw source snapshot and checksum receipts are deterministic extraction side effects under the same private directory. No public fixture, global seed, app/database mutation or approval.
