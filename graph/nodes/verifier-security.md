# verifier-security

## Job
Uavhengig kontroller sikkerhetsrettelser og bevis før publisering.

## Input
- AGENTS.md, context.md, rules.md.
- _bmad-output/implementation-artifacts/spec-security-hardening.md.
- Diff fra a6b29b6c0e96d0e2fc1fb38ac0bf51865a661293 og berørte app-/test-/CI-/dokumentasjonsfiler.
- work/security-source-findings.json, work/security-release-evidence.json og refererte testlogger.
- docs/SIKKERHET.md.

## Output
Bare work/security-review.json med status, findings (severity, file, evidence, repair), checked og limitations. Ingen appendringer, private dataverdier, commit/push eller NAS-tilgang.

## Checks
Angrep avvises før kostbart arbeid, samtidighet håndteres, ordinære flyter bevares, CSP passer kamera/PWA, avhengighetsfeil stopper CI, bevaringspåstander samsvarer med bevis. Kontroller usikre antakelser og testdekning. Ingen godkjenning utledes fra egenprodusert arbeid.
