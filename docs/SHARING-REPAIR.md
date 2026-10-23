# Shared-budget repair

The approval screen now shows who has confirmed, prevents repeated confirmations by the same person, and opens the shared budget once both approvals are recorded. Identical submissions reuse a pending proposal. Invalid, changed or stale proposals require a fresh review instead of silently changing the approved participants.

After updating, open **Dine budsjetter**, choose the pending proposal, and confirm once from each person's own account. For joint administration, the spouse must appear as **Kan administrere** in a **Felles** budget. **Kun innsyn** remains read-only. If an old proposal says it must be reviewed again, the owner/administrator uses **Gjennomgå nytt forslag** (or the existing-budget setup) and both people confirm the replacement.

Notifications now include sharing requests, sharing activation and shared shopping-item changes, alongside calendar notifications. Bill due/overdue alerts remain in-app and are scoped to accessible budgets. Enable **Varsler på denne enheten** on each device after signing in. Push text is generic; access is checked again before sending and when opening a notice.

Migration `0024_notification_targets` adds nullable notification links. It does not assign legacy budget ownership, replace private data or change credentials. Keep the existing Compose project, `.env`, database volume and import path during the normal update. No restore/import/reseed or new key setup is part of this repair.

## Verification

The frozen sharing/notification release passed all 446 Django tests and all 64 Node workflow checks. Both confirmation orders, editor monthly-plan saving and revoked-access retries are covered. Independent source review passed. Browser approval and shared editing were exercised with fictional accounts. Local private source reconciliation preserved all 72 imported records and exact raw values; configuration and private source fingerprints stayed unchanged. No actual NAS deployment or physical OS push display was observed; delivery transport was tested with a controlled mock.
