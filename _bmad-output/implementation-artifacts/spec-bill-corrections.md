---
title: 'Trygg retting av regninger og poster'
type: feature
created: '2026-10-22'
status: done
baseline_commit: '6855a459a3916193a6f9210a5ea3aadc14cd0fd1'
route: dispatch
review_loop_iteration: 1
context:
  - _bmad-output/specs/spec-familieblikk-family-workflows/SPEC.md
  - _bmad-output/specs/spec-familieblikk-family-workflows/bill-corrections.md
  - _bmad-output/specs/spec-familieblikk-family-workflows/acceptance-tests.md
---

<frozen-after-approval reason="Robel aksepterte planen 2026-10-22">

## Intent

Regningslisten mangler trygg retting av én forekomst. Betalingsangre sletter posten fysisk. Implementer akseptert trinn 1 med bevarte poster, historikk, angre/gjøre om/gjenoppretting, eksplisitte seriegrenser og filtrert CSV. Den eksakte native kontrakten og preview er akseptert med «Plan is accepted»; kvittering ligger i .project-init/bill-corrections-human-acceptance.json.

## Boundaries & Constraints

Alltid: bevar ID-er, kildereferanser, datoer, beløp og eksisterende private data. Bruk familieisolasjon, ferske modulrettigheter, oppretter/admin, versjon og idempotens for hver mutasjon. Bevar Figtree/merkevare, kalender/push og modulsynlighet som brukeren har løst. Bruk kompatible migrasjoner og PostgreSQL i isolerte tester.

Aldri: rekonstruer gamle slettinger uten grunnlag, skjul faktiske forpliktelser ved arkivering eller tell reverserte poster. Ingen nye avhengigheter, commit/push, NAS-utrulling, import/seed/restore av eierprofil eller faktiske familievarsler. Dokumenter og handlelister følger senere designporter.

## I/O & Edge-Case Matrix

| Tilfelle | Inn | Ut | Feil |
|---|---|---|---|
| Rett forekomst | Ubetalt, forventet versjon | Samme slot, ny verdi/reserve | Konflikt bevarer utkast |
| Avbryt/gjenopprett | Feilført regning | Beholdt rad, null/én reserve | Betalt avvises |
| Angre betaling | Aktiv betaling uten refusjon | Reversert rad, reserve tilbake | Nyere betaling blokkerer gjenopprett |
| Serie | Fra-dato og berørt liste | Kun tillatte fremtidige forekomster | Endret liste må bekreftes på nytt |
| Historikk | Hendelse + gjeldende versjon | Ny hendelse, aldri overskriving | Gamle rettigheter gjelder ikke |
| CSV | Tillatt periode/kategori/status | Hele tillatte utvalg | Ingen privat cache/formler |

</frozen-after-approval>

## Code Map

- budget/models.py: FamilyRow-versjon, Entry-sekvens/idempotens, BillOccurrence-identitet; utvid med beholdt aktivstatus og varig historikk.
- budget/services.py: autoritativ økonomi, Household-lås, fondsavstemming og betalingsvalidering; gjenbruk fremfor ny beregningsmotor.
- budget/access.py: row_modules/safe_rows/lock_member; behold gjeldende sammensatt policy.
- budget/views.py/forms.py/templates: eksisterende skjema/navigasjon; nye rettinger bruker samme UI.
- budget/spending.py og øvrige lesere: aktive poster og forekomster må telles eksplisitt; behold tidligere funksjoner.
- budget/migrations: kompatibel backfill av stabil slot; stopp ved kollisjon uten å slå sammen data.

## Tasks & Acceptance

**Execution:**
- [x] budget/models.py og migrations: aktivstatus, historiske koblinger, unike aktive betalinger, stabile slotter og historikk/kommandoer.
- [x] budget/services.py og correction_services.py: validerte atomiske kommandoer, arkiv/serierevisjoner, reversering/gjenoppretting og alle økonomiske lesere.
- [x] budget/correction_views.py, forms/templates/urls: før/etter-bekreftelse, historikk, statusfiltre og CSV.
- [x] budget/tests*: AT-01–15 og relevant regresjon; nye testdata er syntetiske.
- [x] work: browser- og reviewbevis samt lesende kontroll av bevaringskontrakt.

**Acceptance Criteria:**
- Gitt flyttet eller avbrutt forekomst, når måned materialiseres igjen, så oppstår ingen ny kopi av samme slot.
- Gitt feilført betaling, når angre/rett/registrer utføres, så teller én aktiv utgift og hele historikken beholdes.
- Gitt nyere endring eller tilbakekalt tilgang, når gammel kommando eller gjenoppretting forsøkes, så avvises den uten bivirkning.
- Gitt eksisterende serie, når den arkiveres, så består alle reelle ubetalte forpliktelser; gjenåpning ettergenererer ikke stoppintervallet.
- Gitt filter og medlemsrettigheter, når CSV eksporteres, så samsvarer det komplette tillatte utvalget og ingen skjulte rader lekker.

## Implementation Notes

Godkjenningen dekker samme native kontrakt; dette arbeidskortet konkretiserer filansvar uten nye produktvalg. Arbeidstreet inneholder bare egne aksepterte planleggingsfiler. Ingen fornyet godkjenningsport kreves. Migrasjoner skrives og prøves på isolert database, aldri automatisk mot NAS.

## Spec Change Log

- Runde 1: Uavhengig review avdekket datorekkefølge, eksplisitt stoppstatus, replay og ufullstendig visning av økonomisk virkning. Ikke-frosne implementasjonskrav presiseres under. KEEP: behold migrasjon/slot-ID, append-only historie, fersk policy/låser, norske eksisterende flater og alle grønne bevaringstester. Bevar fungerende kode og utbedre avgrenset i samme arbeidskopi; ingen destruktiv tilbakestilling av delt arbeid.

## Presisering for ny implementasjonsrunde

- Seriens baseline gjelder før tidligste lovlige revisjonsdato. Daterte verdier/status er autoritative; nye endringer avgrenser berørte forekomster ved neste revisjon. Verdiendring bevarer enabled; bare resume gjenopptar. Ordinary-serie krever kategori.
- Hvert postutkast får egen stabil kommandonøkkel. Signert serie-retry bruker opprinnelig manifest for replay; fersk tilgang kontrolleres først. Andre payloads avvises.
- Eksisterende postredigering krever før/etter-bekreftelse. Vis faktisk økonomisk effekt per berørt måned gjennom eksisterende regnemotor, også gjeld/fond; ikke likestill fakturabeløp med tilgjengelighetsendring. Preview må etterlate null dataendringer.
- Regningshistorikk viser lenkede betalingers angre/gjenoppretting under gjeldende policy. Historikk viser alle regnskapsrelevante felt med forståelige etiketter og autoriserte relasjonsnavn.
- Betalt regning har eksplisitt refusjonshandling til eksisterende skjema, med validert original valgt. Bevar rolle-/familiekontroll.
- Måltester dekker datorekkefølge og start før første forfall, arkivert revisjon, HTTP-retry, eksakte eksportfiltre og bekreftelsesflytene.

## Review Triage Log

| Funn | Dom | Bevis og rute |
|---|---|---|
| Blind 1 | high | affected bruker bare nedre dato, mens series_state bruker siste daterte revisjon; eksisterende og virtuelle desemberregninger divergerer. bad_spec. |
| Blind 2 | high | revise setter archived=False uten å bruke gjeldende enabled; vanlig verdiendring starter serien. bad_spec. |
| Blind 3 | medium | CorrectionForm tillater tom kategori; revise_series mangler ordinary-kategorikrav som validate_entry krever ved betaling. patch. |
| Blind 4 | medium | save_entry erstatter originalnøkkel med uuid4 mens EntryForm beholder originalnøkkelen; retry treffer versjonskonflikt. bad_spec. |
| Blind 5 | medium | edit_view lagrer eksisterende Entry direkte; bekreftelse med økonomisk virkning mangler. bad_spec. |
| Blind 6 | medium | entry_state øker forekomstversjon, men registrerer bare Entry-hendelse; regningshistorikk mangler tilbakeføringen og lenke. bad_spec. |
| Blind 7 | medium | history_view labels utelater kind/asset/original/received/valuta/kurs/gebyr, som EntryForm kan endre. bad_spec. |
| Blind 8 | high | preview bruker alltid amount_ore som reserve; calculate bruker max(plan,paid+pending) for gjeld og fondspåfyll for fond. Beløpspåstand blir feil. bad_spec. |
| Blind 9 | medium | bill_list har angre uten faktisk-refusjonshandling; eksisterende EntryForm støtter original men ingen forhåndsvalgt bill-lenke. bad_spec. |
| Blind 10 | maybe-false | Hele eksportlisten evalueres under Household-lås med payment-spørringer; faktisk problematisk datamengde/ventetid er ikke demonstrert. Defer, medium uverifisert; mål realistisk stor syntetisk historikk før ytelsesendring. |
| Edge 1 | high | Baseline har first_due som dato; revisjon før denne taper ved series_state-sortering. bad_spec. |
| Edge 2 | high | Samme bekreftede datogrensefeil som Blind 1; separate funn bevart. bad_spec. |
| Edge 3 | high | Samme bekreftede automatisk-gjenopptak-feil som Blind 2. bad_spec. |
| Edge 4 | medium | correction_view regenererer manifest med økte versjoner før replay; signert identisk retry avvises. bad_spec. |
| Verification 1 | medium | Tester har ikke avvikende filterrader; fravær av dato/kategori/status-filter ville fortsatt passert. patch: eksakte HTML/CSV-ID-er. |
| Runde 2 Blind 1 | medium | preview settes før economic_preview; ValidationError skjules av hidden-form-grenen. patch: nullstill preview/token ved feil. |
| Runde 2 Blind 2 | medium | Stale hidden version beholdes ved redigering; ny innsending feiler igjen. patch: eksplisitt last-gjeldende-og-vurder med bevart utkast, aldri automatisk overskriving. |
| Runde 2 Blind 3 | high | DateField tillater år 1–9999; economic_preview bygger hele månedsintervallet under familielås. patch: rask eksplisitt ressursgrense før løkken; ingen delvis mutasjon. |
| Runde 2 Blind 4 | medium | calculate-komponenter dekker disponibelt beløp, ikke mål-/gjeld-/fondssaldo; innskudd innen plan kan feilaktig beskrives uten virkning. patch: inkluder tillatte berørte saldoer fra eksisterende balansefunksjoner. |
| Runde 2 Blind 5 | medium | Entry restore kan endre flere felt enn preview viser. patch: bruk eksisterende financial_changes for snapshot før/etter. |
| Runde 2 Blind 6 | medium | Hendelsens økonomiske virkningsdato lagres, men template viser bare registreringstid. patch: vis effective_date. |
| Runde 2 Blind 7 | false | Native kontrakt garanterer undo for forekomstretting/avbrytelse og postendring; serier har eksplisitt ny datert revisjon. Historikken viser ingen gjenopprettingsknapp for series_revision, og lover ikke slik handling. Gjør begrensningen synlig, uten ny serie-undo. |
| Runde 2 Blind 8 | medium | Eksisterende grensesnitt viser også før endringen bare materialiserte regninger; fremtidig måned kan velges og materialiserer serien. Defer: egen serieoversikt er pre-eksisterende oppdagelsesforbedring, ikke tap av korrigeringsdata. |
| Runde 2 Blind 9 | low | can_restore ser ikke occurrence_version som tjenesten avviser. patch: vis kjent sperre og skjul ugyldig handling. |
| Runde 2 Blind 10 | low | Manifestet har ID/versjon men skjermen viser ikke lenke/kategori. patch: vis lenke og før/etter-kategori/verdi med eksisterende data. |
| Runde 2 Edge 1 | medium | Samme bekreftede preview/error-feil som Blind 1; egen rad bevart. patch. |
| Runde 2 Verification Other 1 | medium | Samme feil bekreftet i template og manglende HTTP-feiltest. patch med refund/sparing-avvisning. |

## Verification

- Django/PostgreSQL-måltester og full regresjon; migrasjonskontroll uten uregistrerte modellendringer.
- Nettleserkontroll med fiktive familier på mobil/PC, konflikt, rettigheter og CSV.
- Uavhengig fersk gjennomgang av databevaring, kilde og faktiske testkvitteringer før ferdigmelding.

Implementasjonsnoden eier budget-kilde og tester for dette arbeidskortet. Andre agenter arbeider i checkouten; ikke reverser andres endringer. Orkestrator eier plan/graf/bevis. Utfør implementasjon sekvensielt. Unngå å påkalle bmad-build rekursivt; dette er selve implementasjonshandoffet fra steg 3. Eksisterende work/run-test-python.ps1 gir isolert PostgreSQL-testoppsett; ikke skriv til eierdatabasen.


## Ferdigstillelse

Alle bekreftede feil fra review er rettet; siste uavhengige etterkontroll bekrefter feilvisning, konfliktgjenoppretting og ressursgrense. Testoppslaget i en eksisterende kalendertest er stabilisert på medlems-ID; kalenderlogikken er uendret.

290 Django/PostgreSQL-tester, 90 nettleserkontroller, 41 Node-tester og 9 lesende kildebevaringstester passerte. Bevis: .project-init/bill-corrections-build-evidence.json. Datamigrasjon er prøvd bare isolert; faktisk eierprofil/NAS er ikke oppdatert. Utsatt: eksportytelse ved stor historikk og egen serieoversikt. Ingen commit/push/deploy.
