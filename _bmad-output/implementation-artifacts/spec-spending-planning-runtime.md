---
title: 'Bygg godkjent forbruksanalyse og månedsplanlegging'
status: done
created: '2026-10-20'
baseline_commit: 9560f9a0a885cd437c0697f1a6eaac8d64d2365f
route: dispatch
review_loop_iteration: 0
source_spec: ../specs/spec-familieblikk-spending-planning/SPEC.md
human_acceptance: ../../.project-init/spending-planning-human-acceptance.json
---

## Godkjent resultat

Implementer native CAP1–7 og godkjent prototype i eksisterende Familieblikk. Forbruk viser hele bekreftede utgiftsgrunnlaget med beløp, automatisk søk, kategori- og tidsvalg. Årsoversikt bruker grafer med tydelig datadekning. Neste måneds plan er et redigerbart utkast; bare administrator kan lagre etter eksplisitt mål-/endringsgjennomgang. Kalender, kontoer, private kildeposter og faktisk bokføring bevares. Native kernel og calculation-rules.md er produktkilden; dette er utførelseskartet.

## Implementeringskart og eierskap

- Backend: nye spending_models/services/forms/views, migrering 0010 og fokuserte PostgreSQL-tester. Kontrakt mellom noder: work/spending-api-contract.json.
- Frontend: spending.html og gjenbrukbar spending_workspace.html, spending.js/css og atferdstester. Godkjent grønn fireflisidentitet og eksisterende appskall.
- Koordinator: URL-integrasjon, eksisterende oversiktsflate og kategoriadministrasjon, generisk skjemahåndtering, Docker, faktisk eierkontroll og uavhengig gjennomgang.
- Lagrede arbeidsendringer tilhører autorisert pågående produktarbeid på codex/family-calendar. Brukerens eksplisitte aksept gjelder denne implementasjonen; bevar samtidige endringer. Ingen avhengighet, commit/push eller ekstern utrulling er godkjent.

## Avstemt datamapping

Forbruk bruker expense/remittance minus tilhørende refund på refusjonsdato. Inntekt, sparebevegelser, gjeld og fond er egne klasser. Hele periodens total vises separat fra det filtrerte utvalget. Ingen toppseks-avgrensning; ingen tomme inntektsrader i utgiftsgrafen. Kategorier uten ramme viser faktiske beløp, ikke falsk budsjettprogresjon. Ukategorisert og negativ nettorefusjon er egne synlige tilfeller. Alle oppslag og valglister avgrenses til innlogget familie.

Neste måneds forventede inntekt lagres separat som planforventning; lagring oppretter aldri inntekts-/utgiftsposter. Eksisterende MonthPlan lagrer full kategoriavsetning (ordinære faste forpliktelser pluss øvrig variabel plan) eller én asset-avsetning. Faste ordinære regninger trekkes én gang i utkastets ligning; kategoriens variable forslag trekker fra den delen som allerede er klassifisert som fast. Sparing lagres per eksisterende sparemål, gjeld og fond per eksisterende oppsett. Ingen nye mål eller ukjente kildedatoer gjøres opp.

Virtuelle regninger for målmåneden og tidligere ubetalte forpliktelser leses uten prepare_month/materialisering. Faktisk forekomst undertrykker en virtuell forekomst for samme mal og måned, også når dagen er flyttet. Gjeld dekkes av plan/forpliktelse én gang. Fondsbalanse og tidligere reserverte forpliktelser må avstemmes før ny underfinansiering beregnes; et gammelt påfyll trekkes ikke på nytt som neste måneds gap. Historisk forslag er et synlig gjennomsnitt av eksplisitt valgte avsluttede måneder; sparsomt/ufullstendig grunnlag krever gjennomgang, og ukjente beløp blokkerer bekreftelse.

## Sikker lagring

Egen atomisk tjeneste med familiens radlås, adminpolicy, fersk kilde-/mål-snapshot, revisjoner og idempotens. Bekreftelsesdialog viser mål, beløpsendringer og rest. Konflikt eller feil gir ingen delvis oppdatering. Bare den bekreftede fremtidige målmånedens forventning og månedsplaner skrives, pluss audit og forespørselskvittering. Bevar oppretter på eksisterende plan, øk versjon, sett derived=False og marker eksplisitt månedsavsetning fremfor gammel annual_total når beløpet overstyres. Ikke kall save_row/prepare_month/reconcile_funds eller oppdater andre måneder fra denne lagringen; eksisterende motor kan senere avlede fremtidige måneder fra det eksplisitte ankeret når de åpnes.

## Kontrollpunkter

- [x] Alle kategorier og filtre, identiske graf-/detalj-/postsummer, år uten nullmatrise.
- [x] Utkast uten autosave; korrekt ligning, refusjon, manglende grunnlag og historie.
- [x] Adminbekreftelse, familieisolasjon, konflikt/idempotens og ingen bokførte endringer.
- [x] Reaktiv mobil/PC-visning med tastatur-/tekstalternativer, feil/frakobling og beholdt utkast. Full skjermleseraudit er ikke kjørt.
- [x] Eksisterende kalender-/domene-/identitetstester og nye meningsfulle tester består.
- [x] Docker og faktiske egne kildeverdier avstemmes; uavhengig gjennomgang uten blokkere.

## Review Triage Log

### BMADs tre uavhengige gjennomganger

Hvert funn er vurdert separat før gruppering. `B` er blind kildegjennomgang, `E` kanttilfeller og `G` verifikasjonshull. Ingen ny produktbeslutning eller brukeraksept er utledet fra modellgjennomgangene.

| Funn | Dom | Bevis og håndtering |
|---|---|---|
| B1 videreføring etter målmåneden | low · patch | Umiddelbare skrivinger er målbegrenset; senere videreføring er allerede godkjent eksisterende oppførsel. Dokumentasjon og bekreftelse presiserer denne forskjellen. |
| B2 gjeldsminimum under redigering | high · patch | Minimum var bare et startforslag. Inngår nå i kjent forpliktelsesgulv, med regressjonskontroll. |
| B3 antatt variabel del av gammel kategoriramme | false | MonthPlan lagrer én samlet ramme, ingen kjent del på 500 kr. Å bevare anmelders antatte del ville gjette et ukjent regnestykke. Øvrig plan er eksplisitt redigerbar, historiske forslag kan velges, og bekreftelsen viser faktisk før/etter-ramme. Ingen dobbeltføring er påvist. |
| B4 inntektsmåned tegnes som utgiftsnull | medium · patch | Datostatus alene skilte ikke manglende ordinære observasjoner. Grafverdien blir ukjent uten treff; netto null krever faktiske utgifts-/refusjonsobservasjoner. |
| B5 prognoseinntektens tidsrom | medium · patch | Hele månedsforventninger kunne merkes som en enkeltdag; årstelleren inkluderte fremtidige grafmåneder. Egen periodeetikett og korrekt headerdekning, delvise egendefinerte intervaller undertrykkes. |
| B6 mistet utkastvarsel ved lastefeil | high · patch | Dirty-markøren ble fjernet før erstatningsdata kom. Bevares nå til vellykket erstatning. |
| B7 feil Prøv igjen-handling | medium · patch | Tidligere utkast ble forhåndsvist etter mislykket målbytte. Nytt forsøk beholder den konkrete feilede operasjonen og målet. |
| B8 avtaler på synlige nabodatoer | medium · patch | Kalendergitter viste valgbare datoer utenfor måneden uten data. Hele gitteret leses nå, med separat månedsagenda og familieavgrenset regresjonstest. Innen allerede godkjent kalenderomfang. |
| B9 årsgrafens pengeverdi | low · patch | Eksakte tall fantes i tekstalternativ; synlig pengeskala og søyletitler legges til for direkte lesning. |
| B10 samtidige DB-operasjoner | medium · patch | Sekvensielle tester beviste ikke faktiske låskøer. Ekte PostgreSQL-tråder med separate forbindelser dekker idempotens, konflikt og konsistent lesing. |
| B11 kildeverdier og revisjon under samtidig skriving | high · patch | Ubeskyttet planning-GET kunne kombinere ulike tidspunkt. Samme gjenbrukbare familielås gir konsistent lesing. |
| B12 foreldet akseptprojeksjon | low · patch | Aktive projeksjoner og kalenderens statusreferanse er oppdatert til faktisk aksept. Historiske hashverdier og ikke-beståtte automatiske porter bevares. |
| E1 månedsanker videreføres | false | Dette er eksplisitt godkjent eksisterende videreføring av grenser, ikke en livstidsbegrenset engangsplan. Umiddelbar målbegrensning er testet. Ordlyden presiseres under B1. |
| E2 redigert gjeldsminimum | high · patch | Bekrefter B2; samme gulvretting dekker begge konkrete rapporter. |
| E3 bekreftelse låst etter gjenoppkobling | medium · patch | Historikk-/forkast-/avstemmingshandlinger har ingen save-preview. Kravet til preview gjelder nå bare lagringshandlingen. |
| G1 manglende lesetilbake av planbeløp | medium · patch | Lokal Docker/nettleser testet persistens, men varig Django-regresjon manglet ulike før/etter-beløp. Ny test leser kategori og asset fra DB og plan-API. |
| G2 bekreftelsesflyt bare kilde-regex i Node | high · patch | Lokale nettlesertester kjørte flyten, men CI-Node-testen ville ikke stoppe et for tidlig kall. Eksekverbar DOM/VM-test kjører preview, avbryt og separat bekreftelse. |

- Tidligere ubetalte virtuelle regninger manglet: rettet med månedlig projeksjon fra første forfall; reelle månedlige forekomster overstyrer og betalte forekomster telles ikke på nytt.
- Historisk datadekning ble for sterkt tolket fra én post: rettet til ufullstendig dekning, manuell gjennomgang og ukjente kategoriforslag når en valgt måned mangler observasjoner.
- Fonds-/gjeldsregnestykket på klienten avvek: rettet til samme forpliktelsesgulv og saldo-/påfyllsregler som serveren. Arkiverte kjente forpliktelser beholdes.
- Bruk historikk gjenbrukte gammel plan: rettet til egne historiske forslag med stabil kildeversjon; konkurrerende endringer krever eksplisitt avstemming.
- Detaljlenker ble skjult av feil ruteprefiks: rettet til presis samme-opprinnelse /endre/entry/UUID/-rute.
- Fremtidig forbruksperiode ga omvendt datointervall: rettet til tydelig validering før respons.
- Manglende historiske fondsavsetninger ble utelatt: rettet til skrivefri projeksjon som avstemmes mot eksisterende prepare_month/fund_balance i tre regresjonstester.
- Raske faneskift kunne gi dupliserte graf-ID-er: rettet ved eksplisitte ID-er per visning, uavhengig av aktiv fane.
- Nye endepunkter og planforhåndsvisning er skrivefrie. Den eksisterende Oversikt-rutens månedsforberedelse er bevart og er uttrykkelig unntatt fra denne avgrensede påstanden.

## Verification

Bruk eksisterende isolerte PostgreSQL og .venv. Kjør fokuserte tester under utvikling, deretter relevant fullsuite én gang per nødvendig reparasjonsrunde. Nettleser på 360/390/768/1024/1440, separate fiktive familier for mutasjoner og ekte eierprofil for lesekontroll/privat kilderevisjon. Ingen virkelig eierplan lagres som test. Project Init status har gamle registrerings-/driftmarkører; ikke påstå automatiske porter grønne når bare faktiske kvitteringer er kjørt.

Endelig teknisk kontroll: 147 Django/PostgreSQL-tester (60,941 s), 18 Node-tester og 20 kilde-/previewbeskyttelsestester består. Node-testene kjører nå faktisk bekreftelses-/gjenopprettingsflyt via DOM/VM uten nye avhengigheter. System-/migrasjonskontroll er ren. Fersk isolert server 4188: 77 nettleserkontroller i én sammenhengende kjøring og uendrede kildehashverdier. Faktisk Docker-eierapp: 67 kontroller på fem bredder, ingen eierlagring; privat rådatatilstand er identisk med opprinnelig avstemming. Dockerens begrensede approlle består eksplisitt lagring/lesing/idempotens i fiktiv testfamilie. Alle 18 runtime-filer i image er identiske med testet kilde. Samlet kvittering: work/spending-runtime-verification.json; uavhengig sluttdom: work/spending-runtime-review.json. Ingen commit/push eller NAS-utrulling.

Uavhengig sluttdom er `pass_source_and_evidence_review`, uten blokkere eller ventende bevis. 26 kildehashverdier, 8 nettleserbundne hashverdier og 18 Docker-runtime-hashverdier er avstemt av en separat verifier. Alle tre BMAD-lag er gjennomført og hvert funn triagert; ingen gjenværende feil er utsatt. Eksisterende videreføring av planer og generisk Oversikt-forberedelse er eksplisitt avgrenset, ikke nye garantiutsagn.
