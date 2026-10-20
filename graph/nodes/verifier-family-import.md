# verifier-family-import

## Input
- context.md
- rules.md
- scripts/prepare-family-import.py
- private-data/family-budget/source/family-budget-expandable.xlsx
- private-data/family-budget/import/import-package.json
- private-data/family-budget/import/validation.json
- private-data/family-budget/source/source-receipt.json

## Output
private-data/family-budget/import/independent-review.json

## Contract
Fresh context. Re-read the original workbook independently of the producer. Compare source hashes and all nonempty input rows/cells with staged records. Check zero silent loss, duplicates, dates, currencies, loan/goal links, formulas vs cached values, no guessed household binding, no demo mixing, and git/preview protection. Distinguish preserved-but-unresolved from safe-to-load. JSON: schemaVersion, verdict, checks, findings, limitations. Never claim the data is in a live authenticated profile without runtime proof. No other file edits or public data outputs.
