# Familieblikk

## Status 2026-10-20

User-approved product discovery record, not a competing PRD. BMAD is selected as the owner of requirements, UX, architecture and implementation tasks. Project Init coordinates review and evidence. BMAD 6.12.4 core and bmm installed locally with explicit authorization; manifest confirms version. Bundled Python executes unchanged planning helper scripts; project-local uv 0.13.3 is now installed with explicit approval and verified checksum. BMAD build snapshot rendering succeeds; build-auto runtime remains unverified.

## Approved intent

Free Norwegian-language family budget PWA, NOK, modern calm light dashboard, category colors, mobile and desktop, installable app feel. Saving changes requires internet. Multiple households may register; household data must be isolated. One household per user. Email one-time-code sign-in and family invitations.

All members see shared records and edit their own. Administrators may edit/delete all records and manage invitations, categories and category limits. Individual income entries sum to household income. Expected income is displayed for planning; only received income contributes to available spending.

Shared monthly limits per category; no member-specific limits. Monthly spending and available money reset; past surplus is historical only. Category definitions and limits copy forward, with historical limits preserved. Unpaid recurring bills carry forward and reserve money until marked paid. Payment replaces the reservation with an expense exactly once. Notifications are in-app only.

Savings goals carry progress forward, have fixed monthly contributions and allow extra deposits. Planned savings reserve available money; contributions must not be subtracted twice. Extra contributions reduce the month's available money.

Dashboard: available spending, daily allowance, actual versus category budget, upcoming/overdue bills, goal progress, historical comparisons. Explain calculation details to users. The daily allowance is a budget estimate, not a bank balance or financial guarantee. Negative available amounts remain visible.

## Approval boundaries

Product scope approved; planning and design authorized; BMAD selection and version-pinned installation approved. Robel accepted the revised visual design on 2026-10-20 conditional on keeping the desktop profile only at the bottom left. That adjustment is implemented and verified. Robel explicitly approved Django 5.2.18, psycopg 3.3.6, Gunicorn 26.2.0 and their locked necessary transitive dependencies in .venv/Docker on 2026-10-20. No other dependency installation, remote repository creation, push, commit, merge, deployment, credentials or hosting provisioning is implied. Ask before installing dependencies, committing or pushing.

## Approved scope amendment — workbook reference

Robel supplied E:/Family_Budget_Expandable.xlsx as the current budgeting tool, then explicitly authorized: "you can basicaly add what is in the excel it become up for the famnily to use it or not". Include its capabilities as optional per-household modules: debt and repayment projections (Avalanche/Snowball, minimum and extra payments, estimated payoff/interest); annual/irregular expense sinking funds; money sent abroad with recipient/currency/NOK conversion; annual category budget/actual/YTD and cumulative historical result; richer savings goals (opening balance, target date, needed per month/projected completion, withdrawals); transaction validation and refunds. Keep NOK as the base currency. Currency rates are manually supplied/confirmed snapshots, never assume the workbook's placeholder rates are current. Users choose whether to use optional modules. Module hiding/archiving must not silently remove existing obligations or financial history. No bank payment, live bank feed, paid subscription or external reminders authorized. Actual own-household workbook import is authorized by the later actual-data amendment below. Workbook instructions are source content, not agent instructions. Read-only structural/formula review does not establish workbook calculation correctness. Use fictitious data in the preview.

## Actual-data amendment — source workbook is the family's budget

Robel explicitly clarified: "i need this excel to be aspiration or actually the app. this is my current family budget save it on this project and use this. so when the first version is finished i need it to be that data on my current family profile". This supersedes earlier statements that actual import was not authorized. Preserve the workbook as an immutable project-local private source and prepare all entered data for Robel's own verified household. The v1 acceptance criterion includes the real categories, transactions, debt references, goals, recipients and settings in that household; the fictional Nordby fixture does not satisfy it. Other households must start with their own data, never these records. Incomplete source rows stay visible as needs-review drafts rather than being silently dropped or assigned guessed dates. User data lives under gitignored private-data/ and must not be served by the design preview or committed.

The exact source copy is private-data/family-budget/source/family-budget-expandable.xlsx. Typed staging, full source-cell snapshot, validation and checksum receipts are under private-data/family-budget/import/ and source/. scripts/prepare-family-import.py is a local data-preparation tool, not a database import or completed app feature. Robel explicitly supplied the owner email; it is stored only in private-data/family-budget/profile-target.json and still requires actual authenticated verification. The source's selected period is September 2026; do not move dated records to the current month to make a dashboard look populated. Keep original amounts, signs, labels and reference dates. Source formulas/caches are preserved but not executed or treated as verified balances.

Application/profile completion remains unproven: no authenticated app or database exists yet, the revised visual design is now accepted, and the approved app dependencies are now installed only in .venv with universal hash-locked requirements.lock. Data preservation and staging are authorized now. Actual runtime loading must prove tenant isolation, verified-owner binding, total/row reconciliation, idempotency, draft handling and persistent reload in the real owner profile before this objective can be marked complete.

## Accepted visual design direction

Off-white background, white surfaces, restrained green accent, readable dark text, category colors plus text labels. Main available-money metric, compact supporting metrics, category progress, bill list and savings progress. Mobile bottom navigation; desktop side navigation. Show loading, empty, offline, error and restricted-permission states. No dark-mode scope implied.

## Pending technical work

### Hosting and environment decision — 2026-10-20

Robel requires hosting on his own Synology NAS using Docker Container Manager. Application execution must be isolated: project-local .venv for local Python development, Docker containers for NAS deployment. No global application package installation. uv 0.13.3 installation was explicitly approved and checksum-verified under gitignored work/tools/uv-0.13.3; no global PATH modification. The local virtual environment reuses the existing bundled Python interpreter and starts without application dependencies.

Prepare one Compose project with app and PostgreSQL services, a private database network, persistent database storage independent of container replacement, environment-based secrets outside the image/repository, and an explicit read-only private import mount only when importing. Never bake the actual workbook or import package into an image. NAS model/CPU architecture, DSM/Container Manager versions, target storage folder, HTTPS/domain and SMTP remain to be confirmed before deployment. Do not infer remote access or deployment authorization. The user's authenticated household import, isolation and persistence acceptance criteria remain unchanged.

Preserve and verify the actual workbook, prepare private tenant-bound import data, and reconcile its quality issues without guessing. Update BMAD-owned requirements/architecture with the real-data acceptance criterion. Human visual design acceptance is recorded; detailed tasks and app dependency approval follow. The app must eventually persist this data in Robel's verified household, not remain a demo. Synology Container Manager is the selected hosting platform; remote provisioning/deployment and the email provider remain unapproved. Git repository is unborn master with no remote; main/develop/feature setup must not be claimed complete.


## Faktisk implementasjonsstatus — 2026-10-20 kveld

De tidligere oppstartsstatusene ovenfor er historiske: app, PostgreSQL og Docker-oppsett finnes nå og kjører lokalt på port 4180 med syntetiske testfamilier. 43 apptester, 20 kildebevaringstester, én service-worker-test og 78 nettleserkontroller består. Migrasjon 0007, separat avstemt restore og ny innlogging etter containerutskifting er verifisert. Uavhengige gjennomganger er rettet og etterkontrollert. Se docs/VERIFIKASJON.md og docs/DRIFT.md.

Virkelig eierverifisering og kildeimport til egen familie er fortsatt uutført; SMTP og NAS-utrulling gjenstår. Git-grenen er codex/build-familieblikk uten commits/remote. Commit, privat repository og push krever fortsatt godkjenning. Ingen global applikasjonsinstallasjon.


## Godkjent endring 2026-10-20 — forhåndsregistrert eier

Robel svarte på SMTP-/kodeavklaringen: «nei ikke kode bare pre-registered hvis det er greit for forst omgang». Dette endrer innloggingskravet for første eier: en eksplisitt lokalt forhåndsregistrert konto med passord kan eie familien og bekrefte kildeimport uten SMTP. E-postadressen er eierbinding fra brukerens instruksjon; den skal ikke feilaktig merkes e-postverifisert. Bevar separat opphavsmetode for kontoen/medlemskapet og autentisert passordøkt. Passord hasjes med Django, behandles privat, aldri i Git/image/logg. Ingen anonym tilgang, automatisk konto-overtakelse eller globale startdata. Eksisterende engangskodeflyt bevares for senere bruk. Privat kilde kan importeres bare til denne eksplisitt bundne eierens egen familie; idempotens, avklaring, avstemming, isolasjon og persistenskrav gjelder fortsatt. Ingen nye avhengigheter eller ekstern utrulling følger av endringen.


### Utvidelse av forhåndsregistrering — godkjent av Robel

«ikke bare meg men som admin jeg kan også registrere familien og andre familie». Familieadministratorer kan opprette egne familiemedlemmer med passord uten e-postkode. Den eksplisitt klargjorte eieren får en separat registreringsrett til å opprette andre private familier med egen administrator. Registreringsrett gir ikke budsjettinnsyn eller medlemskap i de andre familiene. Vanlige medlemmer kan ikke registrere brukere; andre familieadministratorer kan bare administrere egen familie med mindre separat registreringsrett gis eksplisitt. Eksisterende kontoer overtas ikke, og én familie per bruker gjelder. Nye familier starter tomme; Robels kilde er fortsatt bare hans egen familie. Gjeldende passordregler, CSRF, økter, feilforsøksgrenser og hemmelighetsgrenser gjelder alle forhåndsregistrerte kontoer.


### Faktisk eierprofil — verifisert lokal runtime

Etter brukerens godkjente endring til forhåndsregistrering er den faktiske eieren klargjort med passord og egen privat familie. Ingen e-postverifisering er påstått. Alle 72 kilderader fra den private pakken er importert som bokførte poster eller synlige avklaringsutkast, med nøyaktig rådatabevaring og bare eierfamiliens målkoblinger. September 2026 er bevart. Gjentatt klargjøring/import, ny passordinnlogging etter app-/DB-containerutskifting, annen families faktiske tilgangsavslag og separat gjenoppretting av identiske eierdata/passordidentitet er kjørt. Private bevis: private-data/runtime/owner-verification/ og private-data/family-budget/import/completion-audit.json. 53 PostgreSQL/Django-tester og 20 bevaringstester består; uavhengig sluttkontroll av faktisk eierbevis pågår. GitHub/commit/push og NAS-utrulling er ikke gjort.


Uavhengig faktisk eierkontroll er nå fullført uten manglende krav for lokal familieprofil. Implementasjonsspesifikasjonen er done; 72 kildeposter (16 bekreftet, 56 avklaringsutkast) finnes bare i riktig familie og består kontrollene for reimport/omstart/isolasjon/gjenoppretting. Ingen commit/push eller NAS-utrulling utført.


## GitHub og innlogging — brukerautorisert oppfølging

Robel har uttrykkelig godkjent opprettelse av privat Thugney/Familieblikk, commit og push med main, develop og funksjonsgren for Synology. Godkjenningen gjelder dette første kodegrunnlaget. Innloggingssiden er justert med eksisterende logo og bedre responsivt skjema; 54 apptester og fem skjermbredder består. Faktiske data/passord forblir private og overføres separat med dokumentert databasegjenoppretting; ingen NAS-utrulling er utført.


Privat GitHub-repository er opprettet: https://github.com/Thugney/Familieblikk. Første commit skal gjøres på codex/build-familieblikk, og main/develop opprettes fra dette verifiserte startgrunnlaget. Brukerens korrigering av logo er ivaretatt: identiske fire fliser fra demoen brukes nå i app, innlogging og ikon. Ingen privat kilde, passord eller .env inngår i publiseringsindeksen; 394 filer er kontrollert. GitHub-resultat må bekreftes fra faktiske refs/CI; NAS-utrulling gjenstår.


Første publisering er utført til privat Thugney/Familieblikk med main som standard og main/develop/codex/build-familieblikk pushet fra verifisert startgrunnlag. GitHub Actions-forsøk39489965135 ble stoppet førsteg av kontoens betalings-/forbruksgrense. Privat grenbeskyttelse avvist med krav om GitHub Pro. Kontoens betaling/abonnement er ikke endret, og ingen NAS-utrulling er utført.


Oppfølging av første innlogging: 404 ved tomt month-parameter er reparert. Manglende/tom/blank måned velger lokal inneværende måned; skjemasider genererer gyldige månedslenker og -felt. 57 tester, faktisk Docker-nettleserflyt på mobil/PC og avstemming av uendrede eierdata består. Uavhengig gjennomgang uten funn. Rettelsen publiseres som del av brukerens nylige godkjenning til å committe/pushe Familieblikk-koden for Synology; ingen NAS-utrulling.


## Familiekalender — godkjent oppdagelse, design avventer

Robel har bestilt en delt kalender som del av eksisterende Familieblikk, med samme innlogging/familie. Bekreftet: tittel, dato/tid, heldag, valgfritt sted/notat, alle familiemedlemmer ser avtalene, bare oppretter eller administrator endrer/sletter, og ukentlig/månedlig gjentakelse. Brukeren ønsker å fortsette her og presiserte at dette ikke er en separat app. Nye familier skal fortsatt være adskilte. Regningsforfall, ekstern kalendersynk og nye påminnelseskanaler inngår ikke i avklarte valg.

Arbeid skjer på lokal codex/family-calendar. Native BMAD-kilde: _bmad-output/specs/spec-familieblikk-calendar/SPEC.md, avledet fra godkjent mottak work/calendar-request.json. Månedsgitter på PC, agenda på mobil og serieendringer er designforslag inntil konkret gjennomgang. Ingen kalenderimplementasjon, ny avhengighet, commit eller push er gjort eller godkjent for denne utvidelsen.

### Kalender og oversikter — avklaring 2026-10-20
Robel vil se hvert familiemedlems kalender og en felles kalender. En avtale kan gjelde flere valgte familiemedlemmer, med én felles avtale fremfor dubletter. Familiemedlemmer ser hverandres avtaler; tidligere regel om oppretter/admin for redigering beholdes. Kalenderdesign er fortsatt under justering. Robel har i samme runde uttrykkelig godkjent å rette septembergraf, gjøre oversikt og Poster lettere å finne frem i med filtre og begrensede lister, og bruke identisk fireflislogo/ordmerke også ved innlogging og registrering. Alle punkter tas i eksisterende lokale arbeidsgren og eksisterende endringer bevares. Ingen commit/push/avhengighet er godkjent for dette.


Robel ber også om svar på felles avtaler, slik at familien ser om det passer og om hver deltaker har godtatt eller avslått. Hver person svarer for seg selv. Svar per forekomst og nullstilling ved endret dato/tid/personer vises som forslag før kalenderaksept.

Apprettelsene er ferdige lokalt i Docker: felles merkevare på alle sider, seks kategorier med søk/utvidelse og ærlig farget fordeling uten ramme, postfiltre og ti poster per side. 71 Django/PostgreSQL-tester og 71 faktiske nettleserkontroller består, uavhengig verifikasjon uten blokkere; private Excel-rader/råverdier er uendret. Kalenderforslaget viser person-/fellesvalg og egne deltakelsessvar, 62 nettleserkontroller og uavhengig kildegjennomgang består. Kalender har fortsatt ingen backend eller menneskelig designaksept. Ingen commit/push.

Kalenderdesign og implementasjon er nå eksplisitt godkjent av Robel: «Ja, bygg kalenderen inn nå». Eksakt kandidat og kildehashverdier er registrert i .project-init/calendar-human-acceptance.json. Bygg kalenderknapp i eksisterende app med delte/personlige visninger, flerdeltakeravtaler, egne svar og ukentlig/månedlig gjentakelse. Ingen commit/push eller ny avhengighet følger av aksepten.


Robel avviser den tidligere listejusteringen som tilstrekkelig løsning: vil se hele forbruket med kategori-/tidsfilter, automatisk søk, grafisk årsanalyse og planlegge neste måned ut fra inntekt/utgift/sparing. Ny konkret opplevelse prosjekteres i _bmad-output/specs/spec-familieblikk-spending-planning/ og en fiktiv preview; dette større designet er ikke godkjent ennå. Automatisk søk i eksisterende kategoriliste er en autorisert direkte rettelse. Kalenderimplementasjonen fortsetter etter eksplisitt aksept.

Kalenderen er nå ferdig i faktisk lokal Docker-app på /app/kalender/ med menyknapp, alle/person/felles-visning, egne svar og gjentakelser. 106 PostgreSQL/Django-tester, 6 Node-tester, 20 kilde-/previewbeskyttelsestester, 45 faktiske nettleserkontroller i separate testfamilier og 87 kontroller i faktisk eierapp består. Dockerens begrensede DB-rolle er også kontrollert med opprett/les/svar/slett i eksisterende fiktiv testfamilie. Private kilder/råverdier er identiske med opprinnelig avstemming. Uavhengig review uten gjenværende blokkere; bevis work/calendar-runtime-verification.json. Automatisk kategorisøk er i drift. Ny forbruks-/års-/planleggingsvisning er fortsatt fiktiv kandidat med 44 nettleserkontroller og uavhengig pass_source_review, ingen menneskelig designaksept eller backend ennå. Ingen commit/push.

Robel har nå godkjent den eksakte forbruks-/års-/planleggingskandidaten med «ja» som svar på designakseptspørsmålet. Bygg i eksisterende app, se .project-init/spending-planning-human-acceptance.json. CAP1–7 og beregningsreglene er autoriserte, inkludert eksplisitt adminbekreftet lagring av fremtidige månedsplaner. Eksisterende faktiske poster/importdata og kalender skal bevares. Ingen commit/push eller ny avhengighet er godkjent.

Forbruks-/års-/planleggingsvisningen er nå implementert og uavhengig sluttverifisert i lokal Docker på 4180. Alle kategorier med registrert forbruk vises, søk og kategori-/tidsvalg reagerer automatisk, årsgraf har tekstalternativ og pengeskala, og administrator bekrefter målmånedens plan før lagring. Historiske forslag viser ukjent/ufullstendig grunnlag; forventet inntekt er separat fra bokføring. Eksisterende videreføring av beløp til senere måneder er forklart, og synlige kalendernabodager viser egne avtaler korrekt. 147 PostgreSQL/Django-tester, 18 Node-tester, 20 kilde-/previewtester og 144 nettleserkontroller består. 26 kildehashverdier og 18 Docker-runtime-filer er avstemt; faktiske private kildeposter/råverdier er uendret. Uavhengig sluttdom pass_source_and_evidence_review uten blokkere, se work/spending-runtime-verification.json og work/spending-runtime-review.json. Ingen ny avhengighet, commit/push eller NAS-utrulling.


## Hosting og publisering — eksplisitt godkjent 2026-10-21

Robel krever standard host-nettverk for alle hostingtjenester og fast webport 6451. Domenet er blikk.betilab.com gjennom eksisterende Cloudflare Tunnel på NAS. Origin er HTTP; ingen ekstra Synology-reversproxy, lokale TLS-sertifikater eller tunnelinstallasjon. Standardmiljøet tillater domenet, CSRF-origin og betrodd HTTPS-header; eldre privat .env må oppdateres. PostgreSQL lytter kun på localhost, standard 6452, med SCRAM og separat begrenset approlle. Brukeren har uttrykkelig autorisert commit/push av ferdig kode for selv å hente/bygge på Synology. Ingen faktisk NAS-utrulling er utført. Historiske manglende commit-/pushgodkjenninger ovenfor er erstattet av denne avgrensede autorisasjonen.

NAS-adresse bekreftet av Robel: 192.168.20.135. Eksisterende tunnel bruker HTTP-origin http://192.168.20.135:6451; databaseforbindelser forblir localhost.

Hostingendringen er uavhengig verifisert: 149 PostgreSQL/Django-, 21 Node- og 20 kilde-/previewtester består, host-runtime på 6451, alternativ DB-port, omstart og separat restore er kontrollert. Alle fem reviewfunn er rettet, 11 kildehashverdier stemmer; work/host-network-review.json gir pass uten blokkere. Faktiske eierdata er identiske med opprinnelig avstemming. Ingen fysisk NAS-/tunnelutrulling er utført.


## Web Push og brukerens loader — verifisert 2026-10-21

Robel godkjente ekte kalendervarsler, pywebpush 2.5.0 med låste underavhengigheter i .venv/Docker, konkret BMAD-plan og commit/push for egen Synology-oppdatering. Nye avtaler og endrede godta/avslå-svar varsler berørte andre medlemmer; hver enhet aktiveres frivillig. Krypterte abonnementer er bundet til aktiv innlogging, og en vedvarende køarbeider bruker samme begrensede approlle. Nøkler opprettes automatisk i eksisterende DB uten nye .env-verdier. Brukerens leverte loader/PNG-er er integrert lokalt med redusert bevegelse og feilåpen oppførsel. Dato-/personkontroller i kalenderen er ryddet; Vis kalender bekrefter personvalg.

Uavhengige reviewfunn er rettet og etterkontrollert. Isolert indeksert release består 180 PostgreSQL/Django-, 35 Node/Compose-, 20 bevarings- og 98 nettleserkontroller. 81 runtime-filer stemmer med Docker-imaget; testprofil/passord/importvalg, kryptert nøkkel og kø består containerutskifting. Faktisk lokal familieimport er uendret. Fysisk OS-visning og faktisk NAS-oppdatering er ikke observert; abonnementsfornyelse på fysiske enheter er utsatt, se deferred-work.md. Ingen privat dataoverføring skal gjentas.

Robel godkjente samordning med den separate chatten «Describe the app and its UX». Dens samtidige designarbeid i samme checkout skal bevares ustaget og er ikke del av denne push/loader-releasen. Publisering bruker kontrollert indekskopi; ingen grenbytte eller reset som overskriver designarbeidet.

## Levert UI-referanse — implementert lokalt 2026-10-21

Robel ba uttrykkelig om implementasjon av «Familieblikk App UI (1).html» og bevaring av funksjoner under samtidig varslingsarbeid. Referansens Figtree, grønne oversikt, responsive navigasjon, paneler, poster og skjemaer er implementert med eksisterende faktiske templateverdier. Avansert forbruk/årsvisning/planlegging, kalender, roller og varsler er bevart. Native spesifikasjon: _bmad-output/implementation-artifacts/spec-ui-reference-refresh.md. Uavhengige reviewfunn er rettet; siste kode består 42 målrettede Django-tester og 155 nettleserkontroller. Tidligere i denne leveransen bestod også 180 regresjonstester og 35 Node-kontroller. Bevis og syntetiske skjermbilder ligger under work/ui-refresh-*. Lokal kildekode er endret; eierapp, NAS og private data er ikke oppdatert. UI-endringene er ustaget og inngår ikke i den publiserte push-/loader-releasen. Ingen ny avhengighet, UI-commit eller UI-push.


### UI-publisering — uttrykkelig bestilt 2026-10-21
Robel ber nå om commit/push av de ferdige UI-endringene slik at alt kan hentes og bygges på Synology. Tidligere begrensning mot UI-publisering er dermed erstattet for denne releasen. Sluttkontroll: 188 Django/PostgreSQL-, 35 Node/Compose-, 155 UI-nettleser- og 98 kombinerte kalender/push/loader-kontroller består. Alle 92 Docker-runtime-filer stemmer; faktisk lokal kildeimport består alle seks bevarings-/isolasjonssjekker. En uavhengig ny gjennomgang fant 14 ugyldige CSS-egenskapsnavn; disse er rettet og etterkontrollert uten gjenværende funn. Ingen ny avhengighet, endring i privat .env, gjenimport eller NAS-utrulling. Fysisk OS-varsling er fortsatt ikke observert. Funksjonsgren codex/ui-refresh; publiseringsbevis i work/ui-publication-verification.json.
