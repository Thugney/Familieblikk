---
title: 'Explain money use and correct misleading financial recommendations'
type: 'bugfix-and-extension'
created: '2026-10-23'
status: 'verified'
---

## Authorization and scope

Robel explicitly requests continued defect hunting in calculations/recommendations, visibility into unplanned family spending and practical help controlling/saving money, informed by online research, then implementation. Extend the existing accepted overview and planner; preserve private financial areas, explicit plan confirmation, original data and current design. No bank connection, automated transfer, new dependencies, guessed income/limits, account balances or NAS deployment.

## Evidence informing the implementation

- NAV recommends realistic budgets based on receipts/statements and alerts when spending exceeds the budget: https://www.nav.no/okonomi-gjeld
- CFPB recommends tracking actual spending, distinguishing obligations from discretionary choices, and inspecting recurring costs: https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/
- CFPB identifies timing of income/expenses and reserves for unexpected costs as useful controls: https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/
- Money and Pensions Service describes transparent category breakdowns and checking input accuracy/duplicates: https://www.gov.uk/algorithmic-transparency-records/money-and-pensions-service-budget-planner

These sources inform product design; they do not establish anyone's spending needs or supply family amounts.

## Contract

1. Audit arithmetic and recommendations against stored facts. Reproduce defects and correct them with focused tests before changing accounting rules.
2. Add a read-only overview section, 'Hvor ble pengene av?', within existing design components. Show gross ordinary expenses, refunds and net ordinary spending separately. Distinguish actual debt payments, annual-fund payments and savings deposits/withdrawals from unspent reservations. Do not present transfers as consumption or claim bank reconciliation.
3. Show category plan, net spending, outstanding ordinary bills, remaining room and excess over the limit. Missing limit is different from an explicit zero. Refunds stay signed; one category's refund cannot conceal another's excess. Include uncategorized and archived activity. Link to the selected budget's records/plans.
4. Explain that 'igjen å bruke' still includes category money needed for the rest of the month. Calculate remaining category allocations as sum(max(limit - net spend - pending ordinary category bills, 0)); outstanding bills are already reserved in available money and must not be counted twice. Show the signed difference between available money and these remaining allocations, labeled as remainder of registered plans, never a guaranteed safe-to-spend/save balance.
5. Prioritize actionable notices: negative available/plan shortfall; exceeded category limits including bills; spending with missing limit or category; incomplete imported data; otherwise conditional suggestion to review buffer/savings. No hard-coded savings percentage or extrapolation of rent as daily discretionary spending. Historical/future periods must not show current-day advice.
6. Only full financial access can see whole-budget reconciliation/recommendations. Every query and action link respects current financial area. No sensitive financial figures in push; this panel is in-app.
7. State the coverage limit prominently: only registered entries, no bank balance/feed, unknown spending cannot be detected. Existing source drafts remain uncounted and disclosed. No data changes during report calculation.
8. Report actual movements through the earlier of today/month end; retain outstanding obligations through the selected month end. Do not add actual cash-flow totals to reserved-budget totals: these are separate views. Future periods have no actual-spending advice.
9. Resolve carried category/asset plans, unmaterialized recurring commitments and fund top-ups in a read-only projection shared with the calculation engine. Reader and editor totals must match before/after materialization. Pending payment recognition uses the same actual cutoff, so future-dated payments cannot remove current obligations. Annual reports must disclose projected known commitments rather than claim they are omitted.
10. The no-write guarantee applies to reporting/calculation helpers. Existing editor page preparation may still materialize known bills/plans for their editing/payment actions; the new report does not add mutations to that lifecycle. Verify HTTP reader/editor report parity as well as helper-level SELECT-only behavior.
11. Robel's clarification: an invoice payment classified as debt must reduce its selected existing debt and update the strategy exactly once. Expose the bill-to-debt link and today's estimate alongside the original reference balance. Respect bill/debt permissions and verify shared-editor payment, retries and refunds; this does not introduce purchases on credit.

## Verification

Cover gross/net/refunds across months; ordinary bills paid/pending without double count; savings/debt/fund separate cash movements; zero/missing limits; uncategorized and archived spending; negative remainder; incomplete imports; other budget/family/module denial; current/historical/future periods; read-only behavior. Browser-check synthetic complete and warning states at mobile/desktop. Fresh independent review and full regression before publication.

Verified release results and limitations are recorded in docs/MONEY-CONTROL.md. Core full suite:478 passed; Node workflow:64 passed. The subsequent debt-link presentation delta has six additional focused tests plus independent source review and synthetic browser payment evidence.
