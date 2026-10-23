---
title: 'Repair shared-budget confirmation and family notifications'
type: 'bugfix'
created: '2026-10-23'
status: 'verified'
baseline_commit: 'f928de02f853e1f6f475bfec419d880b1bb88a87'
---

## Authorized outcome

Robel requests repair of the shared-budget approval loop, verification that both spouses can accept and administer their shared budget, related defect hunting, notifications beyond calendar, then commit/push only this repair. Another chat's UI work is already committed at the baseline and must remain intact. No NAS deployment, private-data rewrite, dependency installation or real test notifications.

## Repair contract

- Owner and a distinct eligible family member confirm the same exact proposal, in either order. Owner/editor grants allow administration of the shared financial area; reader remains read-only. No role-based bypass of financial grants.
- Repeated identical submissions reuse a valid pending proposal. Existing duplicate proposals are grouped in the chooser, prioritizing a proposal with a recorded confirmation.
- Waiting, already confirmed, active and invalid/stale states are explicit. Successful POST redirects to GET. Activated state links to the accessible budget.
- Validate all participant rows, stored digest, current owner/membership/grants and reviewed version before accepting either confirmation. Never silently discard malformed rows to apply different permissions.
- Legacy inventory includes financial series history. Historical changes require renewed review. Old pending legacy proposals with history may need replacement; no automatic assignment or approval transfer.
- Notify eligible recipients about required sharing confirmations and activation. Shared shopping-item changes notify other members with shopping access. Preserve calendar events/replies and per-budget in-app bill alerts.
- Push and in-app notices share current recipient/household/target authorization. Push text contains no private budget names, amounts or item descriptions. No calendar permission requirement for unrelated notifications.
- Notification migration adds nullable target references only. Existing family records, environment, key material, Compose project/database/volume and private sources stay intact.

## Verification

Regression coverage: both approval orders, shared edits, duplicate retries, stale/tampered/malformed proposals, unrelated members and households, connected legacy graph preservation, transaction rollback, push retry/revocation/isolation, generic service-worker payload and in-app bill scope.

Browser evidence uses an isolated fictional household: owner proposes and confirms; spouse receives an unread notice, follows it, confirms, opens the shared budget and creates a category; owner receives activation notice and edits the same category. No real family account was mutated.

Final release evidence and exact executed checks are recorded in docs/SHARING-REPAIR.md. Physical OS notification display and actual NAS update require device/host testing and must not be claimed from mocked transport.
