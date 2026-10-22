---
title: 'Tydelige og pålitelige kalendervarsler ved trygg oppdatering'
type: bugfix
created: '2026-10-22'
status: done
route: dispatch
baseline_commit: 786f99be24cac9a578cd57e041d37f4c51761950
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="Menneskeeid rettelsesomfang">
## Intent
Robel mottar ikke forventede kalenderavtale-/svarvarsler på Windows og Android. Begge ekte familiemedlemmer har nå tillatt varsler. Aktivering skal være tydelig etter innlogging; erstatt Varsler-tekstknappen med bjelle og rødt antall uleste. Bakgrunnslevering må ikke kreve en åpen appside. Alle fremtidige kodeoppdateringer skal bevare Synology-databasen.

## Boundaries & Constraints
Alltid: samme familie/roller, norske tekster, eksisterende UI/logo/loader. Vis tydelig aktivering på alle autentiserte familiesider inntil denne enheten er aktivert; nettleserens nødvendige brukerklikk beholdes. Eksisterende tillatelse skal ikke utløse ny tillatelsesdialog. Ny avtale og godta/avslå varsler riktige andre medlemmer; en ny deltaker lagt til en eksisterende avtale får også invitasjonsvarsel. Samme handling skal ikke dupliseres. Bjellen teller bare mottakerens egne uleste i nåværende familie, med tilgjengelig tekst og nulltilstand. Levering skjer i separat worker; oversiktsoppdatering er ikke en erstatning for push. Generisk låseskjermtekst beholdes.
Aldri: ingen tvungen OS-tillatelse, offentlig profilinformasjon, svekkelse av utlogging/økt/passord-/familiesjekker, nye avhengigheter, ny database, gjentatt restore/import/seed eller endring i faktiske familiedata/.env/nøkler. Ingen produksjonsvarsler, NAS-utrulling eller fysisk OS-levering påstås uten bevis.

## I/O & Edge-Case Matrix
| Tilstand | Resultat |
|---|---|
| Første innlogging, tillatelse ikke gitt | Tydelig aktiveringsoppfordring; tillatelsesdialog bare etter klikk |
| Aktiv enhet / avslått / ustøttet / offline | Riktig status og veiledning; ingen falsk aktivering |
| Ny avtale, ny deltaker, endret ja/nei | Bare riktige andre mottakere, én køpost per faktisk handling |
| Lukket appside | Worker og serviceworker virker uavhengig av siden |
| Test pending/sent/retry/failed | Vis faktisk kø-/leverandørstatus; leverandøraksept er ikke OS-kvittering |
| Uleste, annen familie, lesemarkering | Privat korrekt antall; oppdatering når synlig uten privat cache |
| Pull/build med eksisterende NAS-oppsett | Samme DB-navn/volum, .env, importmappe, kontoer og kilder bevares |
</frozen-after-approval>

## Code Map
- `push_services.py`, `push_views.py`, `push_models.py`: eksisterende kryptert kø, øktbinding og leveringsrader; ingen modellendring.
- `calendar_services.py::mutate`: familielås/idempotens; varsle bare nye deltakere ved edit.
- `push.js`, `base.html`, `notifications.html`, `ui-refresh.css`: én kontroller på alle familiesider; behold eksisterende hooker og visuell identitet.
- `sw.js`, `views.py::worker_view`: bakgrunnsmottak og versjonshash.
- Compose og `.gitignore`: bevar alle eksisterende miljø-/volumvalg.

## Tasks & Acceptance
- [x] `push_services.py`, `calendar_services.py`: nye deltakerinvitasjoner; høy Web Push-prioritet og 24 timers leverandør-TTL med samme generiske tekst; eksisterende logout-/idempotensvern beholdes.
- [x] `push_views.py`, `urls.py`: CSRF-/øktavgrenset testkvittering med trygge tilstander og privat ulestantall; ingen endepunktstokener eller andres varseldata.
- [x] `push.js`, `base.html`, varselmaler/tag, `ui-refresh.css`: tydelig aktivering uten å besøke Varsler først, bjelle med rødt antall og lesbar aria-tekst; test viser leveringstilstand og tidsavgrenset gjenoppretting. Behold markering som lest og oppdater ved synlighet/online.
- [x] `AGENTS.md`, `rules.md`, `docs/DRIFT.md`: bindende regel per commit/push/oppdatering: bevar eksisterende .env/POSTGRES_DB/prosjektnavn/volum/PRIVATE_IMPORT_PATH; aldri down -v, volumfjerning/prune, flush/drop/truncate, ny restore/seed eller erstattede nøkler som del av vanlig oppdatering. Bare kompatible migrasjoner; eksplisitt separat godkjenning for destruktiv datamigrering.
- [x] `budget/tests/`, `tests/host-network.test.cjs`: mottakere, nye inviterte, enhetsisolasjon, ingen prompt ved sideåpning, badge/lesestatus, leveringskvittering og bevart gjenopprettet DB-konfigurasjon; meningsfull releasekontroll av privat databevaring.
- [x] `work/`: isolert Docker-/nettleserverifisering med appfanen lukket; oppgi nøyaktig hva som er simulert. Ingen privat produksjonsendring.

Gitt godkjent enhet, når andre booker/besvarer med fanen lukket, sender worker kryptert push. Gitt pull/build, når profilen åpnes, er tidligere data bevart.

## Implementation Notes
Robel godkjente den konkrete planen med «Approve and build here» 2026-10-22. Ingen ny avhengighet eller produksjonsendring er autorisert.
Ingen bekreftet generell sideavhengighet; faktisk NAS-worker/OS-levering er ukjent. Dagens UI viser bare queued. Utvid trygg diagnostikk uten falsk leveringskvittering. Eksisterende .venv/Docker og låste pakker; kun fiktive testfamilier/volumer, eierapp4180 urørt.

Testverktøy: work/run-test-python.ps1 manage.py test budget.tests bruker separat PostgreSQL55432; ikke skriv ut testmiljøet. Eksisterende work/verify-push-browser.cjs og work/ui-refresh-qa.cjs viser Playwright/Edge og fiktive fixture-mønstre. Bruk separat Docker-image/prosjekt; ikke endre eierapp4180 eller faktiske familier. Produsentkvittering skal være work/background-alerts-verification.json. Forelderen eier staging/review/publisering. Du eier hele implementasjonen, men er ikke alene i koden: bevar andre endringer.

## Spec Change Log

## Review Triage Log

| ID | Dom | Bevis og rute |
|---|---|---|
| Blind-1 | medium | `mutate` sammenligner framtidig serie mot valgt unntak. Et engangsunntak med B skjuler at B legges til resten av serien; framtidige unntak slettes ved deling. Patch: sammenlign mot seriens grunnlag ved framtidig serieendring, fortsatt valgt forekomst ved engangsendring. |
| Blind-2 | medium | `refresh` skriver globalt abonnement før generasjonssjekken; et forsinket getSubscription-svar kan erstatte abonnementet fra fullført aktivering. Patch: lokale kandidater publiseres først etter sjekken. |
| Blind-3 | medium | `valid_binding` kan være sann ved failed/retrying. controls skjuler da leveringsadvarselen på vanlige familiesider. Patch: skjul bare frisk aktiv status; behold feil/forsinkelse synlig. |
| Blind-4 | low | Test-ID lever bare i minnet og forsvinner ved navigasjon. Avvist: dette gjelder sporadisk testdiagnostikk; varig kvitteringshistorikk krever mer tilstand og er ikke nødvendig for ordinære kalendervarsler. Tidsbegrenset kontroll og ny test etter ett minutt beholdes. |
| Blind-5 | low | Fullt panel rendres før asynkron aktiv-statuskontroll og flytter aktiv brukers innhold. Patch: start skjult, slett tidlige visninger mens kontrollen pågår, vis endelig oppfordring/status ved resultat. Behold noscript-veiledning synlig. |
| Blind-6 | low | Aktivering utenfor Varsler skjuler knappen med tastaturfokus. Patch: flytt fokus til bjellen når aktiveringsknappen fortsatt hadde fokus idet panelet skjules. |
| Blind-7 | low | To identiske config-kall gir en tautologisk sammenligning. Patch: slett redundant før/etter-sammenligning; behold konkrete uavhengige kontraktasserts. Faktisk containerutskifting og eieravstemming er egne beståtte runtimebevis. |
| Blind-8 | maybe-false | Potensielt medium: fysisk Windows-/Android-levering gjennom ekte leverandør er ikke observert. Dokumentasjonen sier dette uttrykkelig; applikasjonsfeil er ikke påvist. Defer: egen autorisert enhetstest etter NAS-oppdatering må vise leverandørstatus og faktisk OS-visning med lukket app. |
| Edge-1 | medium | Samme demonstrerbare forsinkede abonnementsoverskriving som Blind-2; grupperes med denne patchen. |
| Edge-2 | medium | Kvitteringens eierskap følger en muterbar abonnementskobling. Etter eksplisitt ombinding kan ny økt med kjent gammel test-ID lese historiske testmetadata. Patch: fjern gamle diagnostiske testjobber ved ombinding; ordinære kalenderjobber/varsler og familiedata beholdes. |
| Gap-1 | medium | Verifikasjonslaget har bekreftet at framtidig invitasjonstest beholder dato og ikke åpner lenken. Patch: test flyttet framtidig serie med ny deltaker, ny originaldato og faktisk åpning av erstatningsforekomst/måned. |

## Design Notes
Behold Figtree og grønn UI. Bjelle44px, badge med hvit tekst på mørk rød, 99+ ved store tall, sr-only null-/antalltekst. Oppfordring følger eksisterende panelstil uten å dekke navigasjon eller skjema. Ingen ny helhetsdesign.

## Verification
Hele Django/PostgreSQL- og Node/Compose-testpakken, responsiv nettleserkontroll og isolert Docker. Test worker med ingen åpen appside og test faktisk serviceworker i nettleser når mulig; HTTP-mock/DevTools-dispatch merkes som simulering. Revider privat kildeavstemming lesende, og vis at oppdateringskontrakt bevarer eksisterende DB/volum/import. Uavhengig fresh-context review før commit/push; publiser først når autorisert.

Sluttkontroll etter review-rettelser: 195 Django/PostgreSQL, 44 Node/Compose, 20 kildebevaring og 139 Edge-kontroller bestod. Korrigert Docker-image stemmer med 93 kildefiler. Ny containerutskifting bevarte profil/passordidentitet, DB, pushnøkler, abonnementer, ventende køpost og importmontering. Lesende faktisk eieravstemming bevarer alle 72 kilderader. Tre uavhengige review-lag er triagert; alle grupperte patcher er rettet og fullt etterkontrollert. Fysisk Windows-/Android-levering er utsatt og uttrykkelig uverifisert. Ingen NAS-utrulling eller familievarsler sendt.
