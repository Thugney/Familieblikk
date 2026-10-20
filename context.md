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
