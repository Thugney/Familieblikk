# Familieblikk — planning graph

## Family workflows — planning candidate 2026-10-22

Authorized intake: work/family-workflows-handoff.json. Order: bill corrections/history and existing-module discovery, local document import, shared shopping lists. Local processing and explicit trip confirmation are settled; detailed designs remain candidates. No new dependency, commit, push or NAS deployment authorized for this scope.

- producer-family-workflows-spec: native BMAD feature kernel and necessary companions; contract graph/nodes/producer-family-workflows-spec.md.
- producer-bill-corrections-preview: fictional stage-one interaction candidate; contract graph/nodes/producer-bill-corrections-preview.md.
- verifier-family-workflows-plan: independent source/spec/preview review; contract graph/nodes/verifier-family-workflows-plan.md.

Intake + current source -> native spec -> fictional preview -> deterministic checks -> fresh-context verdict -> exact human acceptance. Existing accepted screens and baselines remain unchanged.

## Calendar Web Push — authorized 2026-10-21

Robel requests real browser/OS push for calendar booking and accept/reject replies, repair of the calendar toolbar/person filters, preservation of the completed private Synology transfer, and commit/push when verified. pywebpush 2.5.0 with locked necessary dependencies is explicitly approved in .venv/Docker only. Follow the native build spec under _bmad-output/implementation-artifacts/spec-calendar-web-push.md. Graph nodes: producer-calendar-push (implementation and evidence), verifier-calendar-push (fresh-context source/runtime/security review). Existing accepted calendar design and preregistered accounts remain authoritative; no renewed email verification requirement. Private .env and private-data remain untracked and must survive updates. No actual NAS deployment or test notifications to family members without separate authorization.

Read context.md and rules.md first. BMAD 6.12.4 owns the authoritative product/design/architecture documents under _bmad-output/planning-artifacts/ and feature kernels under _bmad-output/specs/. Project Init owns evidence and review projections only. Approved scope and implementation approval are distinct.

## Graph

- gatherer-source: collect approved intake and framework installation facts into work/source-receipt.json.
- producer-prd: produce the BMAD PRD from approved intake.
- producer-design: produce the BMAD visual contract.
- producer-experience: produce the BMAD behavioral contract.
- producer-architecture: produce the BMAD architecture spine.
- verifier: fresh-context review against approved intake, native workflow rules and current technology sources.
- producer-family-import: preserve the actual workbook and produce a private, source-linked import package for Robel's household. Contract: graph/nodes/producer-family-import.md.
- verifier-family-import: independently reconcile every source row and private import record. Contract: graph/nodes/verifier-family-import.md.
- human gate: Robel reviews the exact visual/design/architecture candidate. Only the human accepts it.

Node contracts: graph/nodes/*.md. Each node has one artifact output; framework memlogs are updated through the deterministic BMAD script. The orchestration session sequences nodes and deterministic rendering/validation edges. No separate research or competing PRD.

## Edges

context.md + _bmad/_config/manifest.yaml -> work/source-receipt.json -> producer inputs.
PRD -> DESIGN.md + EXPERIENCE.md + ARCHITECTURE-SPINE.md (separate producer nodes).
Native specifications -> .project-init/review-context.json and ui-design.json -> project-init baseline/render/visual plan.
Native specifications + mockup + evidence -> verifier -> work/design-verdict.json -> human gate.

## Rules

One job/output per node. Declared inputs only. Cross-node receipts/verdicts use structured JSON. Deterministic edges render and validate; models do not approve their own work. work/ is gitignored. Never fabricate passed gates or record approval from product-scope approval alone. Preserve existing files and other agents' work. No app implementation before design acceptance.

## Private family source

The user's actual Excel data is authorized for preservation and eventual import into the user's own family profile. Store actual data only under gitignored private-data/. Never embed it in the public prototype, commit it, use it as global seed data or expose it to newly registering families. Copy verification, extraction and validation scripts are allowed now; this is not final design acceptance or permission to provision infrastructure. Owner account must be bound explicitly to a verified email; never infer it from a workbook name.

## Shared calendar extension

The user requests a calendar integrated into this existing application and explicitly declined a separate calendar chat. Continue this feature here. Existing preregistered-account authorization in context.md remains authoritative; do not reintroduce an email-code requirement.

- producer-calendar-spec: derive the native BMAD calendar spec from work/calendar-request.json; contract graph/nodes/producer-calendar-spec.md.
- producer-calendar-preview: create one fictional integrated calendar preview from the native spec; contract graph/nodes/producer-calendar-preview.md.
- verifier-calendar-preview: independently check the candidate and execution evidence; contract graph/nodes/verifier-calendar-preview.md.
- Calendar spec -> fictional preview -> deterministic browser checks -> independent review -> exact human design acceptance -> bounded implementation and runtime verification.

Do not alter the accepted budget preview or its screenshot baselines. Calendar capability discovery is approved; calendar visual acceptance is not yet recorded. No new dependency, commit, push or external-calendar integration is authorized by this request.

## Budget usability repairs
User explicitly approved all current dashboard/category/Poster's usability and brand repairs alongside calendar design refinement. Contract: graph/nodes/producer-budget-usability.md. Existing accepted budget design remains authoritative; no fabricated monthly limits or source data changes. Calendar runtime acceptance remains pending. Independent fresh-context review must cover both the repaired app evidence and updated fictional calendar candidate.


## Bindende databevaring ved hver commit, push og vanlig oppdatering

Kontroller at den eksisterende `.env`, `POSTGRES_DB`, Compose-prosjektnavn, databasevolum, `PRIVATE_IMPORT_PATH` og alle nøkler bevares. Bruk bare kompatible migrasjoner på eksisterende database. Aldri kjør `down -v`, volumfjerning eller prune, flush/drop/truncate, ny restore/import/seed, eierklargjøring eller erstatning av nøkler som del av en vanlig oppdatering. Destruktiv datamigrering krever separat, uttrykkelig godkjenning. Releasetest skal kontrollere både Compose-kontrakten og lesende avstemming av de private kildepostene; syntetisk omstartstest alene beviser ikke bevaring av den faktiske profilen.

## Bill corrections — accepted 2026-10-22
Robel accepted the exact stage-one plan and candidate with “Plan is accepted”. Receipt: .project-init/bill-corrections-human-acceptance.json. Implement stage one in this existing build chat; preserve stages two/three for their later design gates. Producer owns implementation and evidence; fresh-context verifier reviews source/runtime/accounting/security. No new dependencies, commit, push or NAS deployment. Native work item: _bmad-output/implementation-artifacts/spec-bill-corrections.md.

## Bill corrections publication — authorized 2026-10-22
Robel explicitly requests commit and push of the completed stage-one work. This supersedes its earlier commit/push restriction. Publish the verified feature branch; preserve main/develop and private configuration/data. No NAS deployment is authorized.
