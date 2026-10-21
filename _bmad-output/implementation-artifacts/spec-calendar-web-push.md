---
title: 'Kalendervarsler med ekte Web Push'
type: feature
created: '2026-10-21'
status: done
route: dispatch
baseline_commit: 45536db63f3b5f8ab2e1bc40e2ac268c34198e2f
review_loop_iteration: 0
---

<frozen-after-approval reason="Menneskeeid funksjonsomfang">

## Intent

**Problem:** Kalenderen mangler telefon-/PC-varsler, og dato-/personkontrollene blir uoversiktlige på smale skjermer. Brukeren vil hente og bygge oppdateringen uten konflikt med allerede overført familieprofil.

**Approach:** Bruk standard Web Push med frivillig aktivering per enhet, varseloversikt i appen og en vedvarende leveringskø. Bevar eksisterende lyse design og rydd kalenderkontrollene.

## Boundaries & Constraints

**Eksplisitt brukerutvidelse 2026-10-21:** Bruk «Familieblikk Loader.html» og de to vedlagte transparente PNG-logoene som grunnlag for ekte oppstarts-/lastetilstander i samme release. Både ikonets fireflisers orbit-animasjon og logoens trinnvise inn-/utvisking er brukerens visuelle kilde. Behold proporsjoner og grønn identitet, tilpass mobil og redusert bevegelse. Ingen kunstig minimumsventetid, ingen loader som blir stående ved feil, tilbakeknapp eller JavaScript-avslag; eksisterende skjema-/navigasjonsvern skal virke.

**Always:** Samme innlogging og familier. Nye avtaler varsler berørte familiemedlemmer utenom oppretteren; felles gjelder hele familien, personvalg bare valgte deltakere. Godta/avslå varsler de andre deltakerne og oppretteren, aldri personen selv. Samme svar eller lagringsnøkkel gir ingen nye varsler. Detaljer åpnes med vanlig tilgangskontroll. Låseskjerm viser aktivitetstype uten kalenderens private tittel/notat. Egen enhet kan aktiveres/deaktiveres og sende et testvarsel. Utlogging og utløpt/ugyldig økt stopper levering til enheten. Eksisterende regningsvarsler beholdes.

**Never:** Ingen e-post/SMS, tidspunktspåminnelser, bankintegrasjon, automatisk tillatelsesprompt eller varsler til andre familier. Ingen nye globale familiedata, ny eierprovisionering, gjenkjøring av overføring eller endring av NAS-ens hemmeligheter. Ingen egen Firebase-konto eller ekstra database/køserver.

## I/O & Edge-Case Matrix

| Tilstand | Resultat | Feilbehandling |
|---|---|---|
| Ny avtale eller endret ja/nei | Varselpost og kø opprettes i kalendertransaksjonen | Rollback gir ingen levering |
| Tillatt enhet | Kryptert push; trykk åpner riktig kalender | Tilgang sjekkes ved åpning |
| Avslått tillatelse / manglende støtte | Ærlig veiledning og varseloversikt | Ingen falsk «aktivert» |
| iPhone vanlig nettleserfane | Veiledning om Hjem-skjerm | Aktiver etter installasjon |
| Nettfeil / 429 / 5xx | Vedvarende retry med begrensning | Kalenderlagring venter ikke på leverandør |
| Utløpt abonnement / annen familie / utlogging | Ingen sensitiv levering | Abonnement sperres eller fjernes |
| Langt navn / smal skjerm | Samlede datokontroller og personvelger | Ingen avkuttede e-postbrikker |

</frozen-after-approval>

## Code Map

- `budget/calendar_services.py::mutate`: eksisterende transaksjon, deltakerutvalg og idempotens.
- `budget/views.py`, `base.html`, `page.html`: innlogging/utlogging og eksisterende Varsler-side.
- `budget/static/budget/sw.js`, `app.js`: eksisterende offentlig serviceworker og registrering.
- `calendar.html`, `calendar.css`, `calendar.js`: behold modal-/avtaleatferd, reparer verktøylinje og lange personvalg.
- `docker-compose.yml`, `docker-compose.import.yml`: samme host-nettverk, volum, POSTGRES_DB og PRIVATE_IMPORT_PATH; privat overføring er allerede gjennomført.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `requirements.lock`: pywebpush 2.5.0 og nødvendige låste pakker, bare godkjent miljø.
- [x] `budget/push_models.py`, `push_services.py`, migrasjon: abonnementer, mottakervarsler, kø og stabil kryptert VAPID-nøkkel i eksisterende database.
- [x] `budget/calendar_services.py`: kø bare ved gyldig, faktisk ny kalenderhandling.
- [x] `budget/push_views.py`, `urls.py`, varselsmal: autentiserte CSRF-beskyttede enhetsvalg, test, lesestatus og oversikt.
- [x] `sw.js`, ny `push.js`: brukerutløst tillatelse, mottak og trygg åpning; ingen privat offline-cache.
- [x] `calendar.html`, `calendar.css`: responsive datokontroller, samlet Måned/Liste og personvelger med tydelig etikett.
- [x] `budget/management/commands/`, Compose: automatisk nøkkelklargjøring og restartbar køarbeider med begrenset DB-rolle; ingen manuell .env-endring.
- [x] `budget/tests/`, `tests/`, driftsveiledning: avgrensning, samtykke, idempotens, retry, kryptering, migrering/omstart og kompatibilitet.

- [x] `budget/static/budget/`, `budget/templates/budget/`: integrer brukerens loader ved faktisk oppstart/lasting, med selvstendige lokale ressurser, feil-/tilbake-/redusert-bevegelse-kontroller.

**Acceptance Criteria:**
- Gitt to familier, når en avtale opprettes eller besvares, får bare riktige mottakere ett varsel per faktisk handling.
- Gitt en aktivert enhet, når appen er lukket, sendes standard Web Push og vises via serviceworker; mottaker styrer OS-tillatelse.
- Gitt eksisterende NAS-.env og database, når ny Compose bygges, bevares kontoer, kildeposter, kalender, importsti og passordidentitet.
- Gitt mobil/PC og lange navn, når kalenderen åpnes, er alle datoknapper/personvalg tilgjengelige med tastatur og minst 44px trykkflate.

## Implementation Notes

2026-10-21 brukerutvidelse: «her er den loader jeg vile bruke i appen», med eksakt HTML og to PNG-filer. Ingen ny designaksept skal utledes utover disse eksplisitt valgte kildene. HTML er en pakket artefakt, ikke applikasjonskode som skal kjøres: trygt dekodede visuelle maler finnes i work/loader-design-0.html (ikon) og work/loader-design-1.html (logo). Begge kilde-PNG-er er RGBA med transparent bakgrunn; ingen bilderedigering er nødvendig. Kildenes integritetskvittering er .project-init/loader-human-source.json. Bruk bare de rene, navngitte animasjonene/SVG-figurene og de oppgitte bildene, ikke bundler-runtime, x-dc/DCLogic eller eksterne skriftnettkall. Normaliser sc-camel-view-box til faktisk SVG viewBox. Loaderens JS må feile åpent, respektere avbrutte navigasjoner og ikke blokkere normale budsjett-/kalenderhandlinger.

2026-10-21: Robel godkjente eksplisitt planen med «Godkjenn og bygg videre her» og pywebpush 2.5.0 med nødvendige låste underavhengigheter. Commit/push er eksplisitt bestilt når verifisert. Kalender/UI er godkjente avgrensede utvidelser av eksisterende design. Arbeidet omfatter hele specen; andre bidrag og private filer skal bevares. Ingen egen chat eller ekstra godkjenning skal innføres for rutinevalg.

Tekniske grenser for implementasjonen: bruk transaksjonell outbox og separat restartbar push-worker i Compose, ikke synkron leverandørkontakt fra kalenderlagring. Nøkler klargjøres automatisk og vedvarer i eksisterende DB; privat nøkkel og abonnementstokener krypteres med nøkkel avledet fra eksisterende DJANGO_SECRET_KEY og skal aldri returneres/logges. Abonnement bindes til bruker, familie og faktisk autentisert Django-økt; worker kontrollerer aktivt medlemskap/økt/passordhash før sending. Endpointvalidering tillater bare offisielle browser-pushtjenester over HTTPS, uten redirects, brukerinfo eller vilkårlige/private nettadresser. Idempotens og lease/retry skal tåle dobbeltarbeider og prosessdød. Nye avtalemeldinger gjelder hele serien én gang; ja/nei gjelder riktig forekomst. Ingen nye varsler for uendret svar, avbrutt transaksjon eller egen handling. Velg korte, generiske låseskjermtekster; private detaljer blir i autentisert varseloversikt. Behold gammel regningsoversikt på Varsler. Bruk ekte kryptering/signering i tester, med begrenset ekstern transport.

Prosjektets godkjente uv finnes i work/tools/uv-0.13.3/uv.exe; Python-runtime i .venv. Bruk hash-lås og bare .venv/Docker. Ingen global pakkeinstallasjon. Prod-NAS er allerede aktiv og har nye data; ikke utfør produksjonsendringer, ikke send testvarsler til virkelige familiemedlemmer. Test med separate fiktive familier/volumer. Original PC-app på 4180 og private dataoverføringer skal ikke erstattes. Oppdateringsflyt må bruke eksisterende private .env/POSTGRES_DB og privat importoverstyring; aldri kjøre eier-/familie-seeding eller gjenoppretting ved vanlig oppstart.

## Spec Change Log

## Review Triage Log

| ID | Dom | Bevis og håndtering |
|---|---|---|
| BH1 | high | Varselklikk bruker client.navigate uten skjemavern. Patch: åpne egen fane og bevar eksisterende ulagrede skjemaer. |
| BH2 | medium | Avvist navigate/focus avbryter åpning uten fallback. Samme patch som BH1 fjerner den sårbare klientnavigasjonen. |
| BH3 | medium | Fetch, worker.ready og tillatelsesløfte har ingen tidsgrense; busy kan bli stående. Patch: begrens venting og gjenopprett kontrollene. |
| BH4 | medium | Refresh-feil kaller controls(false) selv med eksisterende abonnement. Patch: behold deaktivering ved ukjent status, test krever bekreftet enhets-ID. |
| BH5 | maybe-false | Ingen konkret nettleserfornyelse er observert; utløpt abonnement sperres, og ny aktivering krever brukerhandling ved avslag. Uverifisert medium livssyklusrisiko utsettes til fysisk langtids-/abonnementsbyttetest. |
| BH6 | medium | Native select endrer verdi med tastatur før brukeren har valgt ferdig. Patch: bruk eksisterende Vis kalender-knapp. |
| BH7 | medium | Fremtidig seriesplitt gjør originalradens occurrence ugyldig, og fallback forklarer ingenting. Patch: tydelig melding om endret/slettet avtale. |
| BH8 | low | Claim-query filtrerer state og lease; eksisterende available_at-indeks filtrerer ikke historikk. Direkte patch: to små partielle køindekser. |
| BH9 | low | Oppbevaring er ubegrenset, men oppryddingspolicy/kommando er mer enn en direkte korreksjon og ingen konkret hverdagsfeil er vist. Avvist som utvidelse i denne rettingen; ingen automatisk sletting innføres. |
| BH10 | low | VM-testnavnet hevder lukket side uten ekte nettleserbevis. Patch: presist testnavn. Produsentkvitteringen oppgir allerede at fysisk OS-levering ikke er observert. |
| VG1 | medium | CI lister Node-filer eksplisitt og utelater to nye suiter. Patch: inkluder begge i eksisterende kommando. |
| VG2 | medium | Direkte response-mocker dekker ikke pywebpush sin WebPushException for leverandøravslag. Patch: bruk eksisterende ekte transportintersept for 410/429/503 og kontroller lagret tilstand. |
| VG3 | medium | Siste forsøk gir failed jobb men retrying abonnement. Patch: sett failed ved uttømte forsøk. |
| EC1 | medium | Enqueue kan ha lest gammel binding før annen families rebind; sent innlagt gammel jobb passerer ny binding men har feil mottaker/familie. Patch: kanseller bare gammel jobb uten å sperre nytt gyldig abonnement. |
| EC2 | medium | Lukket klient under navigate/focus mister klikket. Samme årsak og patch som BH2/BH1. |

## Design Notes

Eksisterende grønne aksent, skrifttype og flate komposisjon beholdes. Dato vises som én sammenhengende kontrollgruppe; personvalg bruker tilgjengelig nedtrekksfelt i stedet for en lang avkuttet brikkerad. Push-kontrollene følger eksisterende knappe-/skjemastil og viser aktivert, avslått, utgått, frakoblet og feilet tilstand.

## Verification

PostgreSQL/Django- og Node-tester, krypterings-/transportkontroll, isolert Docker-kø/migrering/omstart og bevart privat kildeavstemming. Nettleserbilder på mobil/nettbrett/PC, langt innhold og tastaturflyt. Fysisk OS-levering rapporteres bare dersom den faktisk observeres. Indeksen kontrolleres for private filer før autorisert funksjonsgren → develop → main-publisering.

Etter uavhengig review er alle direkte rettelser etterkontrollert uten gjenværende blokkere. Isolert indeksert release: 180 PostgreSQL/Django-, 35 Node/Compose-, 20 kildebevarings- og 98 nettleserkontroller består; 81 Docker-runtime-filer er identiske. Én uverifisert abonnementsfornyelsesrisiko er dokumentert i deferred-work.md. Fysisk OS-levering og NAS-utrulling er ikke observert. Samtidig UI-arbeid holdes utenfor denne releasen og bevares ustaget. Bevis: work/push-release-final-verification.json og work/calendar-push-review.json.
