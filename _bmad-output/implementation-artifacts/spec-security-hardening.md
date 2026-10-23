---
title: 'Sikkerhetsherding av internetteksponert Familieblikk'
type: 'bugfix'
created: '2026-10-24'
status: 'done'
route: 'dispatch'
baseline_commit: 'a6b29b6c0e96d0e2fc1fb38ac0bf51865a661293'
review_loop_iteration: 0
context: ['{project-root}/context.md', '{project-root}/rules.md']
---

<frozen-after-approval reason="Brukeren bestilte sikkerhetskontroll, rettelser, commit og push i denne chatten.">

## Intent

**Problem:** Familieblikk er tilgjengelig gjennom Cloudflare Tunnel. Angripere skal ikke kunne bruke innlogging eller valgte økonomidatoer til å omgå grenser eller binde opp serverressurser. Budsjettisolasjon, dokumentbehandling og avhengigheter må undersøkes med etterprøvbare resultater.

**Approach:** Reproduser konkrete svakheter med syntetiske tester, reparer dem uten nye pakker, og publiser den verifiserte funksjonsgrenen. Dokumenter gratis Cloudflare-tiltak og hva som faktisk er kontrollert.

## Boundaries & Constraints

**Always:** Bevar privat .env, databasenavn, Compose-prosjektnavn, volumer, importbane, eksisterende nøkler og alle økonomiposter. Bruk bare isolert testdatabase. Eksisterende passordkontoer og kodeinnlogging skal fungere. Brukeren har autorisert commit/push av sikkerhetsrettelsene.

**Never:** Ingen NAS-utrulling, live belastningsangrep, nye avhengigheter uten godkjenning, automatisk sletting/import/restore, nøkkelrotasjon, produktutvidelser eller endring av økonomiberegninger. Ingen påstand om at fravær av kjente CVE-er garanterer sikkerhet. Ikke stol på vilkårlige proxy-headere.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Vanlig innlogging | Gyldig lokal konto og CSRF | Innlogging og øktrotasjon fungerer | Eksisterende norsk respons |
| Sperret passord | Oppbrukt e-post- eller IP-kvote | Ingen passordhashing eller ny kontooppslag; ingen innlogging | Generisk feil |
| Stor passordinndata | Mer enn 1024 tegn | Avvis før hashing både i skjema og tjeneste | Generisk feil |
| Samtidige e-postkoder | Samme adresse eller IP fra flere transaksjoner | Kvoter og 60-sekundersgrense kan ikke omgås | Generisk respons |
| Ekstrem periode | År 9999 eller kildeanker år 0001 | Begrenset arbeid før månedsløkker/skriveoperasjoner | Kontrollert 4xx/valideringsfeil |
| Normal økonomi | Eksisterende historikk og neste måned | Identiske summer, rettigheter og kildeposter | Ingen omskriving av historikk |
| Nettleserbeskyttelse | HTML, API, statiske filer og feil | CSP begrenser scripts og innramming, privat innhold lagres ikke i delt cache | Kamera og service-worker virker fortsatt |

</frozen-after-approval>

## Code Map

- `budget/identity.py`: `password_login` gjør hashing også når `blocked`; `send_code` mangler serialisering før kvotelesing ved samtidige forespørsler. Gjenbruk PostgreSQL advisory locks og eksisterende forsøksmodeller; ingen migrasjon nødvendig.
- `budget/forms.py`: passord-/kodefelter mangler eksplisitt maksimal lengde. Bevar eksisterende passordregler.
- `budget/views.py`: `selected_month` godtar år 0001–9999; `page_view` kaller `prepare_month` på GET. Feil må håndteres før materialisering.
- `budget/services.py`: `prepare_month`, `materialize_template` gjør ubegrensede månedsløkker. `budget/financial_projection.py` har tilsvarende lesende løkker; kildeankre kan også være ondsinnede. Begrens total beregningsjobb før arbeid, ikke bare URL-dato.
- `budget/middleware.py`: private cache-headere finnes; legg til kompatibel CSP og Permissions-Policy, bevar eksisterende Vary med Django-hjelper.
- `familieblikk/settings.py`, `docker-compose.yml`: eksisterende host-nettverk og HTTP-origin er godkjent; endre ikke bindadresse eller produksjonsoppsett automatisk.
- `budget/tests/`, `tests/`: eksisterende regresjoner for isolasjon, CSRF, kamera, push, regninger og budsjetter.

## Tasks & Acceptance

**Execution:**
- [x] `budget/identity.py`, `budget/forms.py`: avvis sperrede/store passord før hashing og serialiser kodekvoter; test med ekte PostgreSQL samtidighet.
- [x] `budget/services.py`, `budget/financial_projection.py`, relevante visninger: sett eksplisitt arbeidstak før datoløkker, avvis både fjern fremtid og gamle kildeankre med kontrollert feil uten delvise skriveresultater. Velg tak som bevarer vanlig familiehistorikk, forklar grensen; ikke klipp økonomidata lydløst.
- [x] `budget/middleware.py`: CSP med lokale scripts, ingen inline-script/eval, objekt/base/rammer av; tillat nødvendige inline-stiler, lokale skrifter, data/blob-bilder og eget kamera. Bevar Vary.
- [x] `budget/tests/test_security.py`: regresjoner for matrisen, negative tillatelser og headere.
- [x] `scripts/audit-dependencies.py`, `.github/workflows/test.yml`: kontroller hash-låste pakker mot offentlig sårbarhetskilde uten ny pakke; utilgjengelig kilde må være feil/ukjent, aldri grønt resultat.
- [x] `docs/SIKKERHET.md`: funn, faktiske tester, avhengighetsstatus og presise gratis Cloudflare-regler, med kilder og skille mellom anbefalt og aktivert.

**Acceptance Criteria:**
- Gitt syntetiske angrepsforsøk, når tester kjører, så avvises misbruk uten å endre tilgang eller korrekt økonomi.
- Gitt eksisterende privat profil, når releasen forberedes, så er konfigurasjon/source-hasher og lesende DB-avstemming uendret.
- Gitt publisering, når kontrollene er ferdige, så peker origin-funksjonsgrenen til den verifiserte committen og rapporten sier hvilke eksterne tiltak som gjenstår.

## Implementation Notes

Brukerens direkte ordre om å undersøke, reparere og publisere gir implementasjons- og publiseringsautorisasjon; ingen ny design-/scope-aksept diktes opp. Project Init status feiler på en eksisterende testlenke; faktiske kontrollbevis brukes.

Appimplementasjon 2026-10-24: 1024-tegns passordgrense, tidlig avslag før kontooppslag/hashing og PostgreSQL-serialisering av kodekvoter. Beregninger avvises ved mer enn 600 måneder per kildeløp eller 10 000 månedstrinn samlet per HTTP-forespørsel; overlappende ankere telles og ingen historikk klippes. Selvstendige tjenestekall har samme arbeidstak per beregning. Månedssider bruker transaksjon slik at senere avslag ruller tilbake materialisering. Lokal CSP og kamera-policy er lagt til med bevart Vary. Etter orkestratorens konkrete avhengighetsfunn er native dekodermiljø begrenset til en tillatt liste uten apphemmeligheter, core-dump deaktivert på POSIX, og eldre PDF-jobber går til manuell gjennomgang uten native PDF-kjøring eller sletting av original/utfylte felt.

Produsentkontroll: 100 målrettede PostgreSQL-tester for sikkerhet/innlogging/planlegging/økonomi bestod på 73,913 s; deretter 100 tester for sikkerhet/dokumenter/kamera/rettelser bestod på 78,284 s. Siste lille tillegg (404 for ugyldig måned i forbruksskallet og utvidet URL-regresjon) inngår i orkestratorens etterfølgende fulle kjøring. Python compileall og git diff --check bestod. Dette erstatter ikke uavhengig gjennomgang, Docker-/nettleserbevis, privat avstemming eller publiseringskontroll.

Implementeringsagent eier bare appfiler og `budget/tests/test_security.py`, pluss merknader her. Orkestrator eier avhengighetsskript, CI, dokumentasjon og bevaring/publisering. Andre agenter arbeider samtidig: ikke tilbakestill eller overskriv deres endringer. Agenten kan gjøre minimale sammenhengende rettelser i andre appfiler hvis kildeundersøkelsen krever det.

## Spec Change Log

## Review Triage Log

Tre uavhengige, kontekstfrie BMAD-reviewere leverte alle sine funn før triage. Alle 13 enkeltfunn er ført nedenfor, også overlappende funn. Brukerens sikkerhetsoppdrag omfatter retting av eksisterende svakheter; ingen ny produktfunksjon eller avhengighet er lagt til.

| ID / kilde | Vurdering og kildebevis | Rettelse og kontroll |
|---|---|---|
| B1 / blind | medium: error.html brukte onclick som den nye CSP-en avviser. | Vanlig lenke til samme side; HTML-parsertest kontrollerer ingen inline-handler. |
| B2 / blind | medium: estimated_debt_balance kontrollerte bare enkeltspenn; gjeldsfordeling manglet samlet reservasjon. | Faktisk renteløp reserverer arbeid; standalone-operasjoner deler budsjett. Test dekker samlet avslag og ingen delvise planer. |
| B3 / blind | medium: refresh_future_plans leste alle fremtidige avledede rader uten å belaste arbeidskvoten. | Teller radene før per-rad-arbeid; test dekker avslag og rollback ved lagring. |
| B4 / blind | medium: month_steps avviste gammel engangsregning før reduksjon til ett steg. | Reduksjon skjer før grensekontroll; gammel engangsregning verifisert. |
| B5 / blind | medium: bred preflight avviste gammel gjeld selv uten faktisk renteløp. | Gjeld belastes ved faktisk beregning etter tidlige returer; urelatert månedsberegning består. |
| B6 / blind | medium: save_row validerte også uendrede historiske ankerdatoer ved metadataredigering. | Bare nye/endrede ankerdatoer får opptaksgrense; rename/archive bevarer gammel dato. |
| B7 / blind | medium: e-postsending låste transaksjonen mens SMTP kunne vente uten socket-timeout; låseventing var ubegrenset. | SMTP fem sekunder og try-lock med begrenset venting; ekte PostgreSQL-kontensjon og feilet sending testes. |
| B8 / blind | medium: gyldige passord kunne hashes uten noen forsøksteller. | Separat all-forsøk-kvote med bevart feilkvote; vellykket hashing og konkurrerende IP-forsøk testes. |
| B9 / blind | medium: CI testet Ubuntu-runtime, men bygget ikke endret produksjons-Dockerfile. | Egen jobb bygger image og kontrollerer rettede Debian-versjoner, UID, pip check og språkmodeller. Samme kontroller består lokalt. |
| E1 / edge | medium: historisk valgt måned underregnet gjeldens faktiske replay gjennom dagens dato. | Reservasjon bruker faktisk as_of; test med valgt eldre måned og reell beregningsdato. Samme rotårsak som B2. |
| V1 / verification | medium: audit.main kunne regressere til exit 0 ved kjente varsler uten testfeil. | Ren, OSV-only og PyPI-only respons testes gjennom main og skrevet rapport. |
| V2 / verification | medium: ingen regresjon for for langt nytt/gammelt passord i passordendring. | For langt gammelt passord når ikke check_password; for langt nytt passord bevarer hash. |
| V3 / verification | medium: middleware erstattet dokumentnedlastingens strengere sandbox-CSP. | Eksisterende CSP beholdes; ekte autentisert originalnedlasting, anonymt avslag og private headere testes. |

Rettelsene endrer ingen produktkontrakt og ble behandlet innen brukerens autoriserte sikkerhetsarbeid. Reviewerne leverte kildefunn; produsenter og orkestrator kjørte rettelser og tester. En ekstra, separat sluttgjennomgang fra kildeagenten ble avvist av review-tjenesten og er ikke registrert som gjennomført eller som godkjenning. Tre opprinnelige reviewlag og deres faktiske resultater beholdes; ingen modellgodkjenning av eget arbeid diktes opp.

## Verification

Endelig kontroll: 524 Django-tester i Linux/PostgreSQL bestod på 262,719 s; 65 Node-kontroller og 8 avhengighetsport-tester bestod. 161 appfiler samsvarer byte for byte med testimaget. Native PNG/OCR, pip check, UID og de to Debian-rettelsene er kontrollert. Nettleserens ordinære flyter og headere er kontrollert med syntetiske data; faktisk mobilkamera/push og Cloudflare-policy er ikke ende-til-ende-verifisert. 72 private kildeposter ble avstemt lesende og 14 beskyttede filer var identiske. Se docs/SIKKERHET.md og .project-init/security-build-evidence.json for presise begrensninger. Ingen uavhengig sluttgodkjenning eller NAS-utrulling påstås.

- `.venv/Scripts/python.exe work/run-security-tests.py test budget --noinput` — isolert PostgreSQL, full regresjon.
- `node --test` med prosjektets eksisterende eksplisitte testliste — JavaScript og Compose.
- `python scripts/audit-dependencies.py` — alle låste direkte/transitive pakker, offentlig rådgivningsdata, ingen installasjon.
- Docker-bygg av separat sikkerhetsimage; Django check og migrasjonsdrift; lesende bevaring; uavhengig ny gjennomgang før commit/push.
