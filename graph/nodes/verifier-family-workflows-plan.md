# Verifier — family workflows planning candidate

Input: AGENTS.md; context.md; rules.md; work/family-workflows-handoff.json; _bmad-output/specs/spec-familieblikk-family-workflows/*; _bmad-output/planning-artifacts/bill-corrections-preview.html; relevant budget source; work/family-workflows-preview-checks.json if present.

Output: work/family-workflows-plan-verdict.json.

Fresh context, independent of producer. Check intake preservation, concrete accounting transitions, current policy/ownership, retained obligations on archive, cancellation regeneration, safe restore/version conflicts, export isolation, staged scope and approval boundaries. Check preview against specification; distinguish static/browser checks from application runtime. JSON schema: {status: pass|needs-work, findings: [{severity, file, issue, remedy}], checked: [string], limitations: [string]}. No approval, app edits, private-data access, dependency installation, commit or push.
