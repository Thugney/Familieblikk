# Money control and calculation repairs

The overview now includes **Hvor ble pengene av?** with recorded spending, refunds, unpaid ordinary bills and category limits. It flags overspending, missing limits, uncategorized activity and plans that exceed available money. The breakdown keeps savings transfers, debt payments and annual expenses separate from ordinary consumption.

**Igjen å bruke** still needs to cover the remaining category plans. The report explains that relationship and reserves unpaid bills only once. A missing limit is shown as unknown, rather than as zero. A positive remainder is not a guarantee that it can safely be spent or saved: unrecorded purchases and unknown future costs are outside this app's data. Compare records with the bank statement when investigating missing money.

## Repaired calculations

- Readers and editors use the same projected carried plans, recurring bills and fund top-ups, including before an editor opens and prepares a month.
- Current and annual actual totals exclude future-dated transactions. Those records remain available in the records list; expected income remains a separate forecast.
- Changing a fund's opening date is blocked once financial history exists, avoiding an accidental double count. Unused funds can still be corrected.
- An explicit monthly fund override remains a monthly amount instead of reverting to annual rounding in subsequent months.
- Debt planning reallocates freed minimum payments within the same total payment budget. A debt already paid off shows zero months remaining. Invalid extra allocations are rejected before changes are saved.
- An invoice classified as **Gjeld** must point to an existing debt. Registering its payment reduces that debt's estimate and updates **Gjeld & strategi**, without creating a second ordinary expense. The bill now names and links to the debt; its card shows today's estimated remainder separately from the original reference balance. This records repayment, not a new credit purchase.

## Research basis

The focus on recorded spending and realistic category limits follows [NAV's budgeting guidance](https://www.nav.no/okonomi-gjeld) and the [CFPB spending-tracking guide](https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/). Conditional buffer guidance accounts for irregular costs and income timing described in the [CFPB emergency-fund guide](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/). Transparent calculations and input limitations follow the [Money and Pensions Service budget-planner description](https://www.gov.uk/algorithmic-transparency-records/money-and-pensions-service-budget-planner). No source supplies household amounts or a prescribed savings percentage.

## Verification and update

Independent source review found no unresolved findings after the dashboard cutoff correction. Focused tests cover refunds, zero/missing limits, private-budget isolation, reader/editor parity, SELECT-only calculation helpers, debt allocation and fund history. Desktop and phone-sized browser checks used a fictional household and verified overspending, missing-limit explanations and the category-to-records link. No physical push-device delivery or NAS deployment is claimed.

The final full regression run passed all 478 Django tests; all 64 Node workflow checks also passed. System checks, migration consistency and diff checks passed. The earlier full run identified an outdated annual-report test expecting future spending as actual; its expectation was corrected and the full suite rerun successfully, preserving the original query-growth check.

The subsequent debt-link presentation improvement passed four new tests and two existing focused regressions covering a shared editor's invoice payment, repeat submission, correct debt association, no double counting, refunds, restricted access and missing rates. An independent reviewer also ran all four new tests successfully. Browser verification registered a fictional 1,000 kr payment against a 10,000 kr zero-interest loan: its estimate became 9,000 kr and the strategy showed nine monthly payments. No live debt or family data was changed.

This change adds no dependency or database migration. Apply the sharing repair's additive migration during the normal application update. Preserve the existing environment, keys, database volume and private import path; no restore, reseed or key replacement is required.
