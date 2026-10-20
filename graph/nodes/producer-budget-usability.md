# Producer — existing budget usability repairs

Input: context.md, rules.md, approved native budget DESIGN/EXPERIENCE/architecture, current budget app sources, user's explicit all-points authorization, real September diagnosis (32 categories, no monthly limits, zero bars).

Output: one native BMAD build work item and its implementation for existing category/entry browsing and consistent app identity. Ownership: budget/views.py, budget/templates/budget/, budget/static/budget/, related tests. Preserve concurrent calendar planning/preview files and all actual budget/import records. No schema/data changes, guessed budget limits, dependency installation, commit or push. Existing app design acceptance authorizes repairs; calendar remains preview-only pending its own acceptance.

Requirements: compact/filterable category overview and bounded/filterable entries, correct category-color visualization with a clearly distinguished spending-share fallback where no positive budget exists, consistent four-tile brand and font on every responsive page including authentication/registration. Household-scoped filtering must not alter global totals or expose another household. Root executes Docker/actual-owner browser verification and fresh-context review after producer tests.
