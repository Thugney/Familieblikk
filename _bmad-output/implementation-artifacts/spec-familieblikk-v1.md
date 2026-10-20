---
title: 'Familieblikk v1 med eget familiebudsjett'
type: feature
created: '2026-10-20'
status: done
route: dispatch
baseline_commit: UNBORN
review_loop_iteration: 1
context:
  - context.md
  - rules.md
  - _bmad-output/planning-artifacts/architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/prds/prd-familieblikk-2026-10-20/prd.md
  - _bmad-output/planning-artifacts/prds/prd-familieblikk-2026-10-20/addendum.md
  - _bmad-output/planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md
---

<frozen-after-approval reason="Robel har godkjent design, bedt om bygging og sagt Bare bygg ferdig">

## Intent

**Problem:** Prosjektet har bare en fiktiv prototype og privat Excel-staging. Familien trenger den fungerende appen med egne vedvarende data.

**Approach:** Bygg norsk Django/PostgreSQL-PWA med godkjent sammenhengende design og alle v1-funksjonene i PRD FR-1–22. Lever Synology Compose og kontrollert import til den eksplisitte, e-postverifiserte administratorens familie. Ingen fiktive startposter i nye familier.

## Boundaries & Constraints

**Always:** NOK i heltall øre, Europe/Oslo, familieavgrensning i serveroppslag og relasjoner, medlem endrer egne poster/admin alle. Bruk arkitektur AD-1–14 som implementasjonsregler, inkludert samlet beregningskontrakt, historiske effektive datoer, refusjoner, spareuttak, idempotent betaling og månedsversjoner. Bevar brukerdata og uklarheter som avklaringsutkast. Designaksept er registrert i .project-init/human-design-acceptance.json. Bruk prosjektets .venv; Docker for NAS. Ingen globale pakker. Eksisterende arbeidsfiler skal bevares; ingen commit eller push. Baseline UNBORN betyr at HEAD faktisk ikke finnes.

**Never:** Bankbetaling, abonnement, offline-skriving, oppdiktet dato/kurs, deling av Robels data med andre familier, privat kilde i bilde/static/Git, automatisk oppretting av ekte verifisert eier, utsendelse fra tester, eller påstand om ekstern deployment uten bevis. SMTP og NAS-konfigurasjon gis via miljø senere. Vanlige registreringer påvirker bare én regnskapsklasse. Modulskjuling sletter ikke økonomiske virkninger.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Identitet | Gyldig/feil/utløpt/gjenbrukt kode | Kun gyldig engangskode gir ny serverøkt | Generisk sendesvar, rategrense, CSRF |
| Familie | Medlem, admin, fremmed familie | Serveravgrenset lesing og riktig skriverett | Ingen fremmed rad/aggregat eller endring |
| Penger | Mottatt/forventet, regning, innskudd/uttak, refusjon | Én motor med AD-10 og kontantresultat separat | Ugyldig beløp, relasjon eller konflikt avvises |
| Oppgjør | Dobbeltbetaling, gjenforsøk, gammel regning | Én post og historisk riktig reservasjon | Atomisk og entydig kobling |
| Kildeimport | Samme kilde to ganger, endret kilde, ufullstendig rad | Bare eierfamilien; ingen dubletter; synlige utkast | Endret kilde avvises/vises som diff, aldri stille overskriving |
| Drift | Utlogging, ny innlogging, app-/DB-omstart | Data består, gamle økter ugyldige | Private svar no-store; offline ingen mutasjon |

</frozen-after-approval>

## Code Map

- `.project-init/familieblikk-mockup.html`, `connected-design.css/js`: visuell referanse; flytt designet til ekte servermaler, ikke behold demodata eller simulerte handlinger.
- `scripts/prepare-family-import.py`: kildeidentitet, typekontrakt og full kildebevaring; gjenbruk staging uten å endre originalen.
- `private-data/family-budget/import/import-package.json`, `profile-target.json`: privat runtime-input, ikke kode eller offentlig seed. Les kun nødvendig struktur; ikke rapporter private verdier.
- `tests/test-family-import-preparation.py`: bevaring og privat preview; eksisterende tester skal fortsatt passere med riktig eksisterende runtime.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `requirements*.txt`, `manage.py`, `familieblikk/`: konfigurer Django, miljø og rot-URL-er.
- [x] `budget/models.py`, `migrations/`, `services.py`: datamodell, policy, transaksjoner, planer og felles beregninger.
- [x] `budget/forms.py`, `views.py`, `urls.py`: ekte CRUD, innlogging/invitasjon, alle navigasjonssider, importgjennomgang og avklaring.
- [x] `budget/templates/`, `budget/static/`: godkjent responsivt design, bunntekst og kun venstre-nedre desktopprofil; manifest, offentlige ikoner og offline-side.
- [x] `budget/importing.py`, `management/commands/`: verifisert eierbinding, idempotent provenance, synlige utkast og avstemming.
- [x] `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/*.ps1`, `docs/`: Synology app/Postgres, ihållende lagring, start/migrasjon, backup/restore, lokale kjørekommandoer og SMTP-miljø.
- [x] `budget/tests/`, `tests/`: reelle motor-, HTTP-, policy-, import-, persistens- og nettlesertester; kontroll av private bilde-/cachegrenser.

**Acceptance Criteria:**
- Gitt ny familie, når den bruker appen, så finnes ingen annen families eller fiktive poster.
- Gitt kildens verifiserte eier, når import bekreftes, så finnes alle kilderader eller avklaringsutkast i kun riktig familie; ny import og re-login endrer ikke radantall.
- Gitt månedsskifte, når oversikten åpnes, så videreføres mål og ubetalte regninger, men ikke gammelt fritt overskudd.
- Gitt administrator/medlem, når UI eller direkte HTTP brukes, så håndheves samme rettigheter og konkurrerende endring overskriver ikke stille.
- Gitt alle v1-sider, når de brukes på mobil/desktop, så fungerer handlingene med ekte data, godkjent layout og ingen horisontal sideoverflyt.
- Gitt Compose på støttet Linux-vert, når tjenester erstattes, så består data; backup/restore og isolasjon verifiseres før ekte NAS-lansering.

## Implementation Notes

Arbeidseierskap: implementeringsagenten eier ny appkode, tester, Docker og driftsdokumentasjon. Andre agenter arbeider i samme prosjekt; ikke reverser deres endringer. Koordinator eier godkjennings-/evidensfiler. Oppgaven omfatter hele v1, ingen stille reduksjon av omfang. Brukeren har bedt om bygging uten flere produktvalg; tekniske valg innen eksisterende kontrakt tas av implementøren. Synology-modell er ikke en lokal kodeblokker; lag portabel Linux-image, ikke gjett CPU-verdi. Docker CLI finnes, daemon er foreløpig stoppet.

Installasjonsport: godkjenning er spurt samlet for Django 5.2.18, psycopg[binary] 3.3.6 og Gunicorn 26.2.0 samt låste nødvendige underavhengigheter. Skriv kildekode nå, men ikke installer pakker eller trekk Docker-images før koordinator bekrefter svaret. Bruk eksisterende Python 3.12.14 i .venv; Gunicorn bare Linux. Ikke erstatt PostgreSQL-bevis med SQLite-bevis.

## Spec Change Log

## Review Triage Log

## Verification

- `.venv\Scripts\python.exe manage.py check` og Django-tester: ingen systemfeil; alle matrisescenarioer kjøres.
- PostgreSQL-integrasjon og samtidighet, migrasjoner og omstart: faktiske runtime-bevis, ikke bare mocks.
- Eksisterende importbevaringstester kjøres med eksisterende bundled Python/openpyxl.
- Eksisterende bundled Playwright/Edge brukes for ekte appflyt, fem bredder og skjermbilder. Ingen nye frontendavhengigheter kreves.
- Kjør Docker Compose config/build og backup/restore når daemon er tilgjengelig; registrer ærlige gjenstående miljøkrav.


### Sluttgjennomgang, runde 1

| Funn | Vurdering | Bevis / avgjørelse |
|---|---|---|
| B1 | high | prepare_month persists future copied plans; later current edits leave future copies unchanged. |
| B2 | high | Archived templates are excluded from all generation, including unvisited historical obligations. |
| B3 | high | Fund allocation uses current target_ore for unmaterialized historical month. |
| B4 | high | Fund edits/deletion validate neither all future balances nor funding refunds consumed later. |
| B5 | high | allocate_debt_plan uses original opening_ore rather than current estimated balance. |
| B6 | medium | Debt events sort by signed amount on same day and clamp credits prematurely. |
| B7 | medium | Mer template includes optional module links unconditionally despite preference flags. |
| B8 | false | category_list.html already renders Endre ramme linking edit plan when item.plan exists; claimed missing edit path is disproved. |
| B9 | medium | verify_code creates username=email; valid254-char email exceeds default username150. |
| B10 | medium | Fixed service-worker cache name and cache-first public assets remain stale across asset-only updates. |
| E1 | high | Fund plans created only for requested month, so skipped allocations absent from balance. |
| E2 | high | ensure_fund_topups assigns selected month rather than obligation month. |
| E3 | high | Existing insufficient top-ups are not reconciled after funding/obligation changes. |
| E4 | medium | add_calendar_months calls date without range guard; valid large target/low plan overflows year9999. |
| E5 | medium | Historical savings plan check examines submitted month only; persisted old month can be moved. |
| E6 | high | Asset form plan save uses freshly read plan.version rather than displayed expected version. |
| E7 | medium | Duplicate of B9; verified independently against username=email. |
| E8 | high | Duplicate of B5; current allocation uses original principal. |
| E9 | medium | Duplicate of B7; preference flags unused in Mer links. |
| V1 | medium | CI has source-substring SW assertions, no executable install/fetch/fallback regression. Root real browser cache checks exist outside committed CI and do not cover fallback. |

Alle reelle funn rettes i implementasjonen uten å redusere brukerens godkjente omfang. Eksisterende kilde bevares; ingen destruktiv tilbakeføring eller ny produktgodkjenning er nødvendig for disse kontraktsrettingene. V1 krever Node-standardbibliotektest av selve service worker-koden i CI; ingen ny pakke. Opprinnelig HEAD finnes ikke, derfor er UNBORN bevart som sann baseline.


### Supplerende avstemming mot FR-22

- R1 (high): Asset.kind guard omits linked bill templates/occurrences, so an unposted debt obligation can disappear from reservation.
- R2 (high): Raw-source totals alone cannot verify explicitly approved dates/classes; capture approved decisions and refresh reconciliation after edits.
- R3 (medium): Valid zero balances/plans are rejected by shared MoneyField min0.01; distinguish positive transactions from nonnegative plans and explicit source review.


### Verifisert lokal implementasjon — 2026-10-20

Alle sju implementasjonsoppgaver er utført. 43 PostgreSQL/Django-tester, 20 kildebevaringstester, én kjørbar service-worker-test og 78 nettleserkontroller består. Docker-image bygges, migrasjon 0007 er aktiv, separat gjenoppretting er avstemt og ny innlogging etter containerutskifting bevarer testdata. Uavhengige målrettede etterkontroller har ingen gjenstående funn. Se docs/VERIFIKASJON.md.

Status beholdes in-review: faktisk eierverifisering/import og NAS-aksept er ikke utført. BMAD steg 5 ber om done og lokal commit, men brukerens uttrykkelige krav om faktisk familieimport og godkjenning før commit har forrang. Ingen commit/push er gjort.


## Godkjent endring 2026-10-20 — forhåndsregistrert eier

Robel svarte på SMTP-/kodeavklaringen: «nei ikke kode bare pre-registered hvis det er greit for forst omgang». Dette endrer innloggingskravet for første eier: en eksplisitt lokalt forhåndsregistrert konto med passord kan eie familien og bekrefte kildeimport uten SMTP. E-postadressen er eierbinding fra brukerens instruksjon; den skal ikke feilaktig merkes e-postverifisert. Bevar separat opphavsmetode for kontoen/medlemskapet og autentisert passordøkt. Passord hasjes med Django, behandles privat, aldri i Git/image/logg. Ingen anonym tilgang, automatisk konto-overtakelse eller globale startdata. Eksisterende engangskodeflyt bevares for senere bruk. Privat kilde kan importeres bare til denne eksplisitt bundne eierens egen familie; idempotens, avklaring, avstemming, isolasjon og persistenskrav gjelder fortsatt. Ingen nye avhengigheter eller ekstern utrulling følger av endringen.


### Utvidelse av forhåndsregistrering — godkjent av Robel

«ikke bare meg men som admin jeg kan også registrere familien og andre familie». Familieadministratorer kan opprette egne familiemedlemmer med passord uten e-postkode. Den eksplisitt klargjorte eieren får en separat registreringsrett til å opprette andre private familier med egen administrator. Registreringsrett gir ikke budsjettinnsyn eller medlemskap i de andre familiene. Vanlige medlemmer kan ikke registrere brukere; andre familieadministratorer kan bare administrere egen familie med mindre separat registreringsrett gis eksplisitt. Eksisterende kontoer overtas ikke, og én familie per bruker gjelder. Nye familier starter tomme; Robels kilde er fortsatt bare hans egen familie. Gjeldende passordregler, CSRF, økter, feilforsøksgrenser og hemmelighetsgrenser gjelder alle forhåndsregistrerte kontoer.


### Utførelse av godkjent forhåndsregistrering

- [x] Passordinnlogging og passordbytte for eksplisitt forhåndsregistrerte kontoer; ingen falsk e-postverifisering.
- [x] Familieadministrator registrerer egne medlemmer; særskilt registrator oppretter adskilte familier med egen administrator.
- [x] Klargjør faktisk eier privat og importer faktisk kilde gjennom autentisert appflyt; bevar alle rader eller avklaringsutkast.
- [x] Avstem faktisk kilde rad for rad, prøv reimport og gjeninnlogging etter containerutskifting; uavhengig etterkontroll.


### Faktisk eierprofil — verifisert lokal runtime

Etter brukerens godkjente endring til forhåndsregistrering er den faktiske eieren klargjort med passord og egen privat familie. Ingen e-postverifisering er påstått. Alle 72 kilderader fra den private pakken er importert som bokførte poster eller synlige avklaringsutkast, med nøyaktig rådatabevaring og bare eierfamiliens målkoblinger. September 2026 er bevart. Gjentatt klargjøring/import, ny passordinnlogging etter app-/DB-containerutskifting, annen families faktiske tilgangsavslag og separat gjenoppretting av identiske eierdata/passordidentitet er kjørt. Private bevis: private-data/runtime/owner-verification/ og private-data/family-budget/import/completion-audit.json. 53 PostgreSQL/Django-tester og 20 bevaringstester består; uavhengig sluttkontroll av faktisk eierbevis pågår. GitHub/commit/push og NAS-utrulling er ikke gjort.


### Uavhengig sluttkontroll og avslutning

Faktisk eierprofilkrav er oppfylt etter eksplisitt godkjent forhåndsregistrering: 72 kildeposter bevart, 16 bekreftet og 56 synlige avklaringsutkast. Kildeavklaringer regnes ikke som bokførte beløp. Etterkontroll work/actual-owner-completion-review.json har ingen manglende krav for den lokale familieprofilen. Alle 53 apptester og 20 kildebevaringstester består, service-worker-testen består. Dokumentert faktisk reimport, omstart, isolasjon og gjenoppretting fullfører implementasjonsaksepten. Status settes done. BMADs foreslåtte automatiske commit utføres ikke: brukerens krav om eksplisitt godkjenning før commit/push har forrang. GitHub og NAS-utrulling er separate, uutførte leveransetrinn.
