# Verifier — kalender med Web Push

Input: native spec-calendar-web-push.md, git-diff, berørt kildekode og tester, work/calendar-push-verification.json når klar. Ingen .env, VAPID-private nøkler, abonnementstokener eller faktiske familieposter leses eller skrives ut.

Jobb: uavhengig kilde-/sikkerhets-/runtimekontroll av familie- og mottakeravgrensning, samtykke, utlogging, ekte kryptert Web Push, pålitelig kø og retries, idempotens og kalendertransaksjoner, responsiv UI og bevaring av Synology-database/importvalg. Kontroller at kildebevis stemmer, og skill simulering fra faktisk enhetslevering.

Output: work/calendar-push-review.json med dom, funn, etterkontroller og begrensninger. Ingen kildeendringer eller publisering.
