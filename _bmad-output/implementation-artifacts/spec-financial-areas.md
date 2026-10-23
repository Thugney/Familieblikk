---
title: 'Separate budsjetter med eksplisitt innsyn'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
baseline_commit: 'a0ba6437057294c29e2c3de6cc19a2c3f6851213'
context:
  - 'graph/nodes/producer-financial-areas.md'
  - 'work/financial-privacy-request.json'
  - '.project-init/financial-areas-approval.json'
  - '_bmad-output/implementation-artifacts/spec-documents-shopping.md'
---

<frozen-after-approval reason="Produktregler bekreftet; detaljdesign fortsatt kandidat">

## Intent og godkjente regler

Medlemmer styrer egen økonomi uten å se foreldrenes. Ved medlemsopprettelse velges uttrykkelig privat budsjett eller navngitte foreldre med leserett. Ingen automatisk aldersregel. Senere tilgangsendringer krever budsjetteierens og familieadministratorens bekreftelse av samme forslag. Administratorrollen gir ikke økonomiinnsyn. Eieren styrer kategorier, planer, mål og øvrig økonomi uten familieadmin. Kalenderen forblir felles etter eksisterende kalenderpolicy.

Robel har nå bekreftet de resterende reglene med «Use these rules» og bedt om fullføring, commit og push for egen testing. Bruk eksisterende akseptert UI-stil. Ingen ny avhengighet eller faktisk NAS-/familiemigrering følger av dette. Senere vertsoppsett krever eksplisitt valg og bekreftelse i appen; ingen automatisk eierskapstildeling.

</frozen-after-approval>

## Modell og invariants

FinancialArea har household, navngitt eier, status, access_version og financial_revision. FinancialAreaGrant gir owner/reader i personlige områder; personlig område opprettes tomt. Foreldreleser kan aldri skrive, betale, bekrefte dokument/tur eller lagre plan. Egen editor-kapabilitet for et felles foreldreområde er foreslått, ikke en utvidelse av foreldreinnsyn i barnets budsjett. Den avklares nedenfor; faktiske navn og rader kan vente til privat vertsmanifest.

AreaAccessChange lagrer før/etter-deltakere, forventet versjon og digest. Bekreftelser bindes til samme digest og aktuelle roller. Endret forslag nullstiller bekreftelser; aktivering låser familie, medlemskap, område og forslag, revaliderer begge og endrer grants atomisk. Kandidat: to forskjellige personer bekrefter; eier som eneste admin får ventende forslag uten selvbekreftelsesomvei. Dette er foreslått tolkning, ikke uttrykkelig brukerbeslutning.

- Tilgang krever aktivt medlemskap, områdegrant, modulrettigheter og handlingens skrivekapabilitet. Ingen admin/complete_finance-bypass.
- Ett eksplisitt autorisert område per finansflate; aldri husholdningssum eller automatisk fallback ved ugyldig område.
- Alle finansrelasjoner tilhører samme familie og område, inkludert JSON-snapshots og generiske target-ID-er. Område kan ikke endres gjennom vanlig redigering. Håndhev i tjenester og databasevern, også bulk writes.
- NULL betyr uavklart legacy, aldri felles tilgang. Nye rader krever område; nye medlemmer får ingen legacy-rett.
- Idempotens, resultatcache, eksport, historikk og køarbeid kontrollerer gjeldende tilgang før replay/sending. Nøkler/payload bindes til område og aktør. Skjult aktivitet påvirker ikke synlige totaler, antall eller revisionshash.
- Bevar regnskapsregler og historisk sequence internt; ikke eksponer husholdningssekvens som aktivitetsteller. Manglende nødvendige moduler gir begrenset oversikt, ikke misvisende delsum som disponibelt.

## Kodekart og utførelse

| Kilde | Nødvendig endring |
|---|---|
| models.py, spending_models.py | Scope Category, Asset, MonthPlan, BillTemplate/Occurrence, Entry, FundTopUp, ImportBatch/Record, MonthlyBudgetHeader, PlanningRequest, CorrectionCommand/Event og finans-Audit. SeriesRevision arver template/event-scope. Kalender holdes separat. |
| access.py, forms.py, views.py | resolve/require/safe_rows, category_choices, restrict_form og lock_relations krever område før hurtigstier. Erstatt admin-only oppsett med områdekapabilitet. Gjennomgå også direkte queries og reverse managers. |
| services.py | calculate, pending_bills, prepare_month, refresh_future_plans, reconcile_funds, topups, debt allocation og alle saves/materialiseringer tar område; template gir forekomstens scope. |
| spending_services.py | Avgrens ordinary_rows, coverage, source_revision/snapshot, commitments, planning, preview og save_plan. Header uniqueness blir area/month. |
| correction_services.py | Autoriser current/before/after/reverses og restore/export; samme område i economic_preview og kommandoresultat. |
| document_* og document_worker | Document/WorkflowCommand får scope; DocumentJob arver dokument. Upload, original, OCR-tekst, metadata, duplikatsøk og lenker avgrenses. Jobb suspenderes hvis initiativtaker mister nødvendig tilgang. |
| shopping_* | Avhenger av ventende produktvalg: områdelister eller husholdningsfelles lister med separat privat turøkonomi. Ved felles liste må varekategori, pris, turkoblinger og kvittering/utgift ha egen synlighet; ikke krev samme scope på listen og privat betaling. Ingen shopping-modul gir automatisk finansinnsyn. |
| identity.py | register_family_account/create_household/provision_owner/accept_invite oppretter eksplisitt tomt område. Invitasjon lagrer innsynsvalg og revaliderer lesere; gamle invitasjoner uten valg gjennomgås. Ingen reprovisionering ved oppdatering. |
| importing.py, kommandoer, push/sw | Eksplisitt importmål og typed target-validering. Finansvarsler kontrolleres ved kølegging/sending/åpning; kalender uendret. Ingen sensitive sider i service-worker-cache. |

Revider uniqueness/replayregistre for Entry, imports, PlanningRequest, CorrectionCommand, WorkflowCommand og document upload; bevar gamle legacy-nøkler under overgang. Bruk neste ledige migrasjonsnummer. Finansielle modulvalg følger området; medlemsmodultilgang er fortsatt et ekstra tak. Implementer schema/policy først, alle tjenester deretter, så medlemsflyt/UI og dokument/handel. Ingen nye medlemsflater før full policydekning.

## UI-kandidat

Behold eksisterende Figtree, grønne aksenter, paneler og navigasjon. ui-ux-pro-max er lest og brukt for merkede kontroller, fokus, tastatur og mobile treffflater; ingen ny stilpakke.

Vis «Budsjett: Mitt budsjett» og «Du kan redigere»/«Kun innsyn». Velgeren viser bare tillatte områder; område følger ruter/skjemaer slik at to faner ikke bytter lagringsmål. Ulagrede endringer avklares før bytte. Nytt medlem krever privat/navngitte-lesere-valg og oppsummering før opprettelse. Første innlogging viser hvem som har innsyn.

«Hvem kan se dette budsjettet?» viser før/etter og begge bekreftelsesstatusene. Admin uten innsyn ser nødvendig tilgangsmetadata, ingen finansinnhold. Tilbakekalling gir tilgangsmelding uten gamle beløp. «Familiens kalender» har ingen budsjettfilter. Dokumentupload og turbekreftelse viser målbudsjett. Fiktiv mobil-/desktopkandidat og nøyaktig menneskelig aksept gjenstår.

## Gjennomgått legacy-overgang — forslag, ingen migrering utført

1. Les inventar på faktisk gjeldende vert, senere NAS; PC-data er aldri erstatningskilde. Privat manifest binder databaseidentitet, rad-/relasjonsfingeravtrykk og medlems-ID-er.
2. Gjennomgå valgt eier, lesere/redigerere, modulvalg og hele sammenkoblede radgrupper. Anbefalt første kandidat er ett eksisterende foreldreområde. Ingen slutning fra created_by/admin/filnavn.
3. Godkjenn eksplisitt midlertidig legacy-kohort med nøyaktige eksisterende medlemmer/rettigheter. Nye eller ikke-valgte medlemmer nektes NULL-data. Ingen automatisk kohort fra opprettelsesdato.
4. Additivt schema tildeler ingen eier. Aktivering krever kohortkvittering; ellers stopp finansaktivering, behold kalender. Ikke åpne ny medlemsregistrering på gammel husholdningsåpen kode i mellomfasen.
5. Kort finansskrivepause: nytt verts-inventar må stemme med manifestet; nye NAS-endringer krever ny gjennomgang. Utpekt eier og admin bekrefter samme manifest. Separat autorisert overgangskommando tilordner FK-er/grants atomisk uten å endre ID, beløp, dato, råkilde, fil eller sekvens.
6. Avstem alle felt/koblinger, replayregistre og faktisk vertskonfigurasjon før åpning. Fjern legacy-kohort først etter komplett mapping. Feil ruller transaksjon tilbake eller gir vedlikeholdsmodus; aldri gammel personvernåpen kode, restore/import/seed eller volumfjerning.

Bevar .env, POSTGRES_DB, Compose-prosjekt, volum, PRIVATE_IMPORT_PATH og nøkler. Lokal 72-kilderaders avstemming erstatter ikke kontroll av nyere NAS-data.

## Verifikasjonsmatrise

Test barn/eier, forelder-leser, admin uten grant og annen familie på alle flater; samme-familie kryssområde-FK/JSON; aggregater/planer/coverage; begge bekreftelsesrekkefølger, stale digest og rolleendring; tilbakekalt økt/URL/download/replay/job; parallelle betalinger/turer; historikk/restore/export; identisk dokumenthash i to områder; tomme medlemsområder og invitasjoner; uendret kalender/push; NULL-kohort og nyere vertsmanifest; to faner, offline og mobil/tastatur.

Krev PostgreSQL-konflikttester, relevante eksisterende suites, syntetiske browserbevis og fersk uavhengig kilde/runtime-review. Ingen tester eller personvernimplementasjon hevdes bestått av denne planen.

## Åpne produktvalg

- Skal eier som også er eneste administrator kunne bekrefte begge roller? Kandidaten krever to personer og lar ellers endringen vente; ingen implisitt bypass.
- Hvem eier eksisterende fellesøkonomi, og hvilke foreldre skal administrere alle poster/oppsett sammen? Faktisk person-/radmanifest må aksepteres privat.
- Må handlelister være husholdningsfelles også mellom private budsjetter? Kandidaten deler innen område; kryssområde-liste med privat betaler trenger egen synlighetskontrakt.

Opprettelsesvalg, leserett, fravær av aldersregel og dobbelbekreftelse er avgjort og skal ikke spørres om igjen.

## Uavhengig planreview

2026-10-22: fresh-context financial_plan_review vurderte kandidaten egnet som utkast med åpne valg. For tidlig låsing av handlelistescope er rettet til betinget kodekart. Fellesforeldres editor-forslag er skilt fra barnets read-only foreldreinnsyn. To-personstolkning forblir et åpent forslag. Ingen implementasjons- eller visuell aksept er hevdet.

## Avklaringer og utførelse 2026-10-22

Dette avsnittet erstatter kandidatspørsmål ovenfor: Handlelister er felles for familien med private betalingsdetaljer; foreldre kan begge redigere et felles foreldreområde; to forskjellige personer bekrefter senere delingsendringer. Brukeren har bedt om implementasjon og publisering etter verifikasjon. Personlige foreldrerettigheter er fortsatt kun lesing.

Eksisterende vertsdata tildeles ikke automatisk. Implementer en eksplisitt oppsettflyt som viser radgrupper, eier og redigerere/lesere før bekreftelse; kalender fortsetter. Før autorisert oppsett kan ingen nye medlemmer få legacy-innsyn. Test overgang bare i syntetiske familier. Virkelige personnavn og gjeldende NAS-rader velges på verten av brukeren.

Produsentkontrakt: graph/nodes/producer-financial-areas.md. Ingen separat redesign, OCR-algoritmeendring eller globale pakker. Publisering er autorisert når alle berørte funksjoner og isolasjon er uavhengig verifisert.

## Tasks & Acceptance

- [x] Additive områdemodell, grants, to-persons delingsendringer og eksplisitt legacy-oppsett; ingen automatisk eierskapstildeling.
- [x] Alle finansielle tjenester, skjemaer, spørringer, bakgrunnsjobber, eksport, historikk og idempotens avgrenses til område.
- [x] Personlig eier kan administrere egen økonomi; leser kan ikke skrive; familieadmin uten grant kan ikke lese; fellesforeldre kan begge redigere.
- [x] Felles handlevarer uten lekkasje av privat betaling/kvittering/kategori/pris; tur oppretter én utgift i eksplisitt valgt budsjett.
- [x] Integrert budsjettvelger, opprettelsesvalg, delingsbekreftelse og migreringsforhåndsvisning i eksisterende design; stabilt mål i to faner.
- [x] PostgreSQL tester for isolasjon, samtidighet, gjenkalling, uendret kalender og legacy-overgang; faktisk familie leses bare.

### Trygg oppstart med én eksisterende konto
Familieadministrator kan opprette eller invitere et nytt medlem med uttrykkelig valgt, tomt personlig budsjett selv om eldre økonomiposter venter på oppsett. Dette gir ingen tilgang til de eldre postene og foretar ingen legacy-tildeling. Dermed kan en annen person bli familieadministrator og bekrefte oppsettet sammen med eieren. Begge bekreftelsene er fortsatt obligatoriske fra forskjellige personer.

### Reparasjon av aktivering og avsenderbekreftelse — 2026-10-24

Brukeren bekrefter at delingsinvitasjonen skal telle som avsenderens godkjenning. «Bekreft og send forslag» registrerer derfor avsenderen i riktig bekreftelsesfelt; mottakeren bekrefter én gang. Hvis administrator sender for en annen budsjetteier, må eieren fortsatt bekrefte selv. To ulike personer, samme signerte innhold, gyldig datagrunnlag og gjeldende tilgang er fortsatt obligatorisk. Gamle lenker med registrert første bekreftelse skal kunne fullføres uten å opprette et nytt forslag.

Avklarte kategoriimporter kan peke på den lagrede månedsplanen, mens uavklarte kategorirader peker på kategorien. Database- og modellkontroll må bevare begge gyldige varianter. Månedsplanvarianten krever bekreftet kategoriimport og samme familie/budsjett for planen og dens kategori. Migrasjon 0025 erstatter bare kontrollfunksjonen; den endrer ikke finansposter, kildeverdier, tidligere godkjenninger eller tilganger. Deling og økonomiske koblinger er separate forhold: aktivering skal bevare eksisterende betalings-/gjeldskoblinger og beløp.
