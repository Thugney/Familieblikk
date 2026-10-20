# verifier

## Input
- context.md
- rules.md
- _bmad-output/planning-artifacts/prds/prd-familieblikk-2026-10-20/prd.md
- _bmad-output/planning-artifacts/prds/prd-familieblikk-2026-10-20/addendum.md
- _bmad-output/planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
- _bmad-output/planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md
- _bmad-output/planning-artifacts/architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md
- .project-init/familieblikk-mockup.html
- .project-init/evidence/design-checks.json

## Output
work/design-verdict.json

## Contract
Fresh context; schema: schemaVersion,verdict,findings[{severity,file,issue}],checks,limitations. This is review evidence, never human approval.

One artifact per node. Framework memlog updates use the unchanged BMAD helper as a deterministic side-effect. Preserve others' work. No approval, commit, push or app implementation.
