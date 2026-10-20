---
title: 'Host-nettverk og port 6451 ved hosting'
type: chore
created: '2026-10-20'
status: done
route: oneshot
review_loop_iteration: 2
---

<frozen-after-approval reason="Eksplisitt brukerbestilling">

## Intent

Familieblikk skal som standard bruke Docker host-nettverk ved hosting på Synology og lytte på port 6451. Standard Compose skal fungere uten en ekstra host-overstyring. Bevar familiedata, volumnavn, begrenset approlle, hemmeligheter utenfor Git og eksisterende importmontering.

</frozen-after-approval>

## Implementation Notes

Dette er en reversibel konfigurasjonsendring, uten app-/skjemaendring, ny avhengighet eller faktisk NAS-utrulling. Brukeren har senere uttrykkelig godkjent commit/push for å hente denne versjonen til Synology. Brukerens nye mål autoriserer videre arbeid med det eksisterende lokale kodegrunnlaget; alle tidligere godkjente, ucommittede endringer bevares på codex/synology-host-network.

Byggeverktøyets første kjøring ble stanset av filtilgang under annen Windows-identitet; samme renderer lykkes under den eksisterende generasjonens eier, uten ACL-endring eller direkte kjøring av workflow-kilder.

Alle tre Compose-tjenestene bruker network_mode: host uten ports/networks. Gunicorn og Docker-image bruker fast 6451, uavhengig av foreldede APP_PORT/APP_BIND i eksisterende .env. PostgreSQL bindes bare til 127.0.0.1 på separat port 6452 (POSTGRES_PORT kan tilpasses) og krever SCRAM også på localhost gjennom eksplisitt read-only hba-konfigurasjon. App/migrering bruker samme localhostport; PGPORT holder backup-/restore-verktøy synkronisert. Bevar eksisterende databasevolum og eier-/approlleskille.

Endre docker-compose.yml, Dockerfile, .env.example, docker/postgres/pg_hba.conf og README/docs DRIFT/SYNOLOGY. Ingen Windows-bridge-fallback legges til i hostingoppsettet. Docker Desktop her eksponerer ikke host-nettverk til Windows-loopback; den eksisterende lokale appen på 4180 bevares, og host-oppsettet kjøres/verifiseres i et separat syntetisk Compose-prosjekt i Dockerens Linux-hostnamespace. Dette påstås ikke som fysisk NAS-utrulling.

Kontroller faktisk normalisert Compose for alle tjenester, uendret volum, ingen portmapping og fast 6451 også med foreldede .env-verdier. Kjør nytt syntetisk host-prosjekt: migrering, HTTP på 6451 fra hostnamespace, begrenset rolle, skrive/lese og omstartspersistens, avvis feil DB-passord og ikke-loopback DB-forbindelse. Eksisterende ekte familie avstemmes uendret. Ingen full interpolert config eller hemmeligheter skrives ut. Uavhengig fresh-context review før overlevering; faktisk bevis i work/host-network-verification.json.

## Brukerens bekreftede hostingpresisering 2026-10-21

Eksisterende Cloudflare Tunnel på Synology skal publisere blikk.betilab.com og peke til appens HTTP-origin på 6451. Ingen ekstra Synology-proxy, sertifikater eller tunnelinstallasjon. Tillatt vertsnavn, CSRF-origin og tolkning av tunnelens HTTPS-header settes i eksisterende miljøkonfigurasjon. Appens HTTPS-redirect er av; Cloudflare håndterer offentlig HTTPS. Robel sa uttrykkelig at ferdig kode skal pushes, slik at han kan hente og bygge på NAS. Dette autoriserer nødvendige commits/push av godkjente kalender-, forbruks- og hostingendringer på funksjonsgren og integrasjon til develop/main, uten direkte commit på main eller faktisk NAS-utrulling.

NAS-adresse bekreftet av Robel: 192.168.20.135. Eksisterende tunnel bruker HTTP-origin http://192.168.20.135:6451; databaseforbindelser forblir localhost.

## Review Triage Log

| ID | Finding | Decision | Resolution |
|---|---|---|---|
| H1 | Existing MD5 verifier incompatible with new SCRAM rule | patch | Preflight format-only check and interactive conversion retaining passwords, volume and app accounts documented before replacement. Explicit server password_encryption=scram-sha-256 overrides legacy MD5 defaults for future role updates. |
| H2 | Forced test project name masks default volume regression | patch | Tests use default Compose name and assert familieblikk plus familieblikk_database. |
| H3 | HBA mount assertion does not prove command selects it | patch | Tests assert explicit hba_file setting in effective PostgreSQL command. |
| H4 | Switch to all-interface binding lacks early access restriction | patch | NAS guide restricts direct origin access before app startup and requires actual NAS check, allowing existing tunnel connector. |
| H5 | Alternate database port lacked operational restore evidence | patch | Synthetic host runtime and separate dump/restore passed with implicit PGPORT on both 6452 and 16452. |

## Verification

149 PostgreSQL/Django tests, 21 Node tests and 20 source/preview preservation tests passed. Django system checks and migration drift check passed. All three services verified using host network without published ports. Default and alternate database ports, container replacement, exact synthetic amount persistence, limited role, wrong-password denial and non-loopback DB denial passed. Separate restore passed at both ports. Public Host and HTTPS header requests succeed over plain HTTP origin. Real owner source records remain identical to initial audit. Receipt: work/host-network-verification.json. Independent aftercheck passed with H1-H5 closed, all 11 source hashes matching and no remaining blockers; no physical NAS deployment claimed. See work/host-network-review.json.
