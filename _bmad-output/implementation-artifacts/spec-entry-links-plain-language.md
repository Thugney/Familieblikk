---
title: 'Forståelige poster med riktige koblinger og kontrollerte summer'
type: 'bugfix'
created: '2026-10-24'
status: 'done'
route: 'dispatch'
baseline_commit: 'ae36c9f3eab3ecc003e9b06f63d1b8f6b5601c65'
review_loop_iteration: 1
context:
  - rules.md
---

<frozen-after-approval reason="Direkte bestilt feilretting og fortsettelse; eksisterende design og beregningsregler beholdes">

## Intent

Robel melder at aktivitetene i Alle poster ikke er riktig koblet, at språket krever økonomikunnskap, og ber om kontroll av beregningene. Gjør registrerte aktiviteter forståelige og sporbare i eksisterende app. Rett bekreftede feil, bruk vanlig norsk bokmål og behold reglene for penger inn, forbruk, regninger, sparing, gjeld og årsutgifter.

## Boundaries & Constraints

Publisering autorisert 2026-10-24: Robel ba uttrykkelig om «Yes commit and push all the fixes». Dette overstyrer commit-/pushbegrensningen nedenfor for verifiserte rettelser på `codex/entry-links-plain-language`. Ingen NAS-utrulling eller automatisk endring av faktiske økonomiposter følger av autorisasjonen. Oppdateringskommandoer: `docs/OPPDATERING.md`.

Alltid: behold valgte budsjett og riktig datoperiode i lenker, respekter lese-/skrivetilgang og modulrettigheter, og gjenbruk eksisterende detalj-/historikksider. Vis konkrete kilder, aldri gjett koblinger fra beskrivelse eller beløp. Bruk samme Figtree, farger, komponenter og responsive oppsett. Forklar beregninger uten å fremstille dem som banksaldo. Historiske og angrede poster skal fortsatt kunne forstås.

Aldri: endre familieprofil, privat konfigurasjon, nøkler, import, databasevolumer eller opprette nye avhengigheter. Ingen migrasjon, NAS-utrulling, commit eller push. Ingen ny økonomimodell eller redesign. Alle muterende tester bruker egen syntetisk testdatabase.

## I/O & Edge-Case Matrix

| Situasjon | Handling | Forventet resultat |
|---|---|---|
| Vanlig post | Åpne fra Alle poster eller kategoriens detaljliste | Lesbar detalj/historikk for eksakt post og budsjett, også for leser |
| Regningsbetaling | Følg postens regningslenke | Riktig regning, dato, betalingspost og endringer; ikke redigeringsskjema som avviser betalingen |
| Tilbakebetaling | Åpne historikken | Opprinnelig betaling kan åpnes; originalen viser sine tilbakebetalinger, inkludert forståelig angret status |
| Sparing/gjeld/årsutgift/utland | Følg koblet mål eller mottaker | Riktig eksisterende oppsett i riktig budsjett og postens måned, helst med nøyaktig anker |
| Handletur/skanning | Følg aktivitet | Riktig handletur, ikke bare toppen av listen; tilknyttede skannedetaljer er tilgjengelige med nødvendig rettighet |
| Begrenset tilgang | Følg eller manipuler lenke | Ingen skjulte opplysninger eller skrivetilgang; annen familie/budsjett avvises |
| Økonomiske bevegelser | Kjør isolerte regresjoner | Betaling erstatter reservasjon én gang; refusjon, dato, sparing, gjeld og fond følger eksisterende regler |

</frozen-after-approval>

## Code Map

- `budget/templates/budget/entry_list.html`: beskrivelsen er ren tekst, betalingen har bare angreknapp. Legg til én konsekvent, lesbar detaljlenke.
- `budget/correction_views.py`, `templates/budget/correction_history.html`: eksisterende lesbar historikk, men svak detaljvisning og manglende opprinnelseslenker. Bruk denne fremfor en parallell detaljside. Betalingsposter skal ikke tilby ugyldig beløpsredigering.
- `budget/templatetags/budget_tags.py`, `templates/budget/workflow_links.html`: eksisterende rettighetsfiltrerte dokument-/handleturlenker; utvid med konkrete relasjoner og gjenbruk `access.require_row/safe_rows`. Ikke gjør family-shared shopping til finansielt innsyn.
- `budget/spending_services.py:spending`, `static/budget/spending.js:entryUrl`: detaljlenker er `/endre/entry/.../` uten area. Bytt til lesbar historikk, eksplisitt area og dato; oppdater sikker URL-validering og Node-testene. HTML-mellomvaren omskriver ikke JSON.
- `budget/templates/budget/page.html`, `shopping_detail.html`: stabile ankere for oppsett/mottaker/tur. Eksisterende gjeldsanker bevares.
- `budget/forms.py`, `correction_forms.py`, sentrale budget-templates og `spending.js`: enklere brukerord; endre etiketter/hjelpetekst, aldri feltverdier/API-nøkler eller lagrede data. Unngå modellvalg som krever migrasjon; bruk presentasjonshjelper ved behov.
- `budget/services.py`, `financial_projection.py`, `money_control.py`: autoritativ beregning. Separat lesende undersøkelse pågår; orkestrator håndterer eventuelle aritmetikkrettelser etter dokumentert reproduksjon.
- `budget/tests/financial_support.py`, `tests/test_domain.py:setup_family`: eksisterende isolerte budsjett-/familiefixtures. `work/run-money-tests.py` laster bare syntetisk testmiljø og angir egen testdatabase.

## Tasks & Acceptance

- [x] Lenker og detaljer: Alle poster, forbruk, betaling, original/refusjon, sparemål/gjeld/fond/mottaker og handletur/skanning. Ingen ødelagte lenker for lesere eller tap av budsjett i kontrollerte tilfeller.
- [x] Språk: daglig oversikt, post-/regningsskjema, sparing, gjeld, årsoversikt og historikk bruker enklere ord, med presis betydning og synlig beregningsgrunnlag.
- [x] Fokuserte Django-tester følger de faktiske genererte lenkene med vanlig Client, leser/editor, eksakt budsjett, relasjoner og annen families avslag. JS URL-validering kontrollerer same-origin og avviser ugyldige ruter.
- [x] Beregningskontroll, full Django-/Node-regresjon, syntetisk nettleserkontroll på mobil/PC og uavhengig fersk review.

Gitt en aktivitet i valgt budsjett, når brukeren åpner detaljer, skal korrekt aktivitet og faktiske relasjoner vises uten å endre data. Gitt en leser, når detaljer åpnes, skal lesing fungere uten redigeringshandlinger. Gitt eksisterende økonomiske fixtures, når summer beregnes før og etter presentasjonsrettingen, skal forventede resultater stemme med uavhengig aritmetikk og tidligere kontrakt.

## Implementation Notes

Implementasjonsagenten eier app-/testendringer for lenker og tekst. Orkestrator eier testkjøring, beregningsoppfølging, denne spesifikasjonen og bevis under work. Du er ikke alene i arbeidskopien: bevar andres endringer, ikke reset eller revert. Eksisterende utracked .claude/ og .codex-remote-attachments/ er utenfor arbeidet. Lokal gren: codex/entry-links-plain-language. Ingen ny designaksept er påstått eller nødvendig for denne bestilte feilrettingen.

## Verification

Kjør målrettede Django-regresjoner via eksisterende lokale Python/testmiljø, deretter hele budget-suiten og eksisterende Node-tester. Nettleserprøven bruker syntetisk profil og sjekker lenker, lesing, mobil/PC og horisontal overflyt. Registrer faktiske resultater og begrensninger; ingen garanti om at all mulig beregningsfeil er utelukket.

## Beregningsfunn og utført retting

To feil er bekreftet både ved uavhengig kildekontroll og isolerte PostgreSQL-regresjoner: fremtidig årsutgiftsplan gjentok en gammel mangel før påfyll var lagret; gjeldsplanens minste betaling ble brukt i bekreftelsen, men et lavere utkastbeløp ble lagret. Seks nye tester ga fire forventede feil før retting. Samme tester og tidligere planleggingstester består nå (46 totalt). Årsutgifter gjenbruker forrige måneds lesende `month_basis`; gjeldens bekreftelsesutkast og endringsliste viser og lagrer samme beløp som summeringen. Ingen historiske planer oppdateres automatisk.

## Review Triage Log

Tre uavhengige gjennomganger er gjennomført: blind kildekontroll, grenseverdier og verifikasjonsdekning. Alle rapportene ble samlet før retting.

| Funn | Vurdering og handling |
|---|---|
| Åpningsbeløp for årsutgifter mangler når oppsettet starter i planmåneden | Bekreftet og rettet. Beløpet tas med én gang i åpningsmåneden. Tester dekker første dag, midt i måneden og senere åpning. |
| Gjeldens normaliserte minstebeløp kan overstige tillatt beløpsgrense | Rettet: valider det normaliserte beløpet før bekreftelsen vises. Tester dekker minimum, summen av flere regninger og lagring akkurat ved grensen. |
| Fast regningsoppsett viser fremtidig endring som allerede gjeldende | Rettet: hent daterte verdier med series_state og vis «Oppsett per» valgt dato. Tester dekker ny pris, stopp og gjenopptakelse. |
| Inntektens eier mangler i lesbar detaljvisning | Rettet: «Inntekten tilhører» vises separat fra den som registrerte posten; leser omfattes av testen. |
| Manglende test for skanning knyttet bare til regning | Test lagt til: eier og leser følger betalingspostens skanningslenke; bortfall av modulrettighet kontrolleres. |
| Sikkerhetstest bruker gammel argumenttype for fund_available_before | Kallsted oppdatert. Grensen for svært gammel historikk er fortsatt kontrollert. |
| Planlagte årsutgiftsbeløp omtales som penger som allerede finnes | Rettet etter siste språkkontroll: teksten sier beregnet beløp og opplyser at tidligere planer inngår. Antall observasjoner omtales korrekt som poster, ikke måneder. |
| Tilbakelenke mangler for regning og fast oppsett | Rettet med budsjett- og månedskontekst. Senere regning åpner oppsettet i regningens måned; egen regresjon lagt til. |
| Valgfri liste over alle enkeltregninger inne på fast oppsett | Utsatt som separat navigasjonsforbedring. Tilbakelenken åpner allerede riktig regningsmåned; ingen nødvendig feilretting gjenstår her. |

Blindkontrollen og grenseverdikontrollen har lest rettingene på nytt uten gjenværende bekreftede feil i de undersøkte delene. Verifikasjonskontrollen bekrefter at testhullene er lukket; siste språkmerknad er rettet. De oppgir eksplisitt at dette var kildekontroll, ikke egen kjøring av hele testsuiten.

## Verifikasjonsnotater

- Første fullkjøring: 537 tester, 7 feilaktige forventninger til gamle etiketter og 4 feil fra gamle testfixturer/kallsteder. Rettet ved å oppdatere de konkrete forventningene og gi testpostene eksplisitt budsjett-ID. Regnskaps-/tilgangspåstander beholdt.
- Etter retting: 43 fokuserte beregnings-, sikkerhets- og presentasjonstester bestod. Endelig fullkjøring: **546 av 546 tester består**, 163,744 sekunder, fire isolerte testdatabaser (`work/entry-repair-full-verified.log`). En tidligere sluttkjøring ble avbrutt ved sesjonsskifte og regnes ikke som bestått. Windows-testskriptet fikk main-guard før den vellykkede parallelle kjøringen.
- 65 Node-tester består; etter aller siste språkpresisering består også de 13 berørte testene på nytt. Django rapporterer ingen modellendringer med makemigrations --check --dry-run.
- Alle 11 lenkeintegrasjonstester består etter siste retting av regningsmåned. Etter siste språkpresisering består de 13 berørte Node-testene fortsatt.
- Nettleser på syntetisk profil: Alle poster → utgift/refusjon/betaling/sparemål; betaling → regning; utgift → nøyaktig handletur og tilbake; kategoriens «Åpne post» → riktig historikk. Area og måned beholdes. Lesebruker åpner detaljer uten redigeringslenker.
- Mobilbredde 390 og PC-bredde 1440 kontrollert uten horisontal overflyt på undersøkte sider. Ingen nettleserkonsollfeil registrert. Midlertidig skjermstørrelse er tilbakestilt og testserveren stoppet.
- Privat profil og konfigurasjon er ikke endret. Tester bruker bare syntetiske databaser på eksisterende testport 55436. Ingen migrasjoner, nye avhengigheter, commit, push eller utrulling.
