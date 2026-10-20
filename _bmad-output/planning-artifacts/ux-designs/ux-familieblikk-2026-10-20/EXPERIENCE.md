---
name: Familieblikk
status: draft
updated: 2026-10-20
sources:
  - ../../../../context.md
  - ../../prds/prd-familieblikk-2026-10-20/prd.md
  - ../../../../work/workbook-structure.json
  - ../../architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md
---

## Foundation

**Reelt datagrunnlag:** FR-22 krever nå at Robels faktiske arbeidsbok brukes i hans egen verifiserte familieprofil i v1. Designprototypen forblir fiktiv og offentlig delbar uten kildeverdier. En ny familie får ikke disse startdataene. Privat kildekopi og importstaging er ikke en ferdig innlogget profil.

### Eierspesifikk importgjennomgang (spine-only)

Etter at den eksplisitt oppgitte eieradressen er verifisert og riktig familie er opprettet, får bare denne administratoren en privat importgjennomgang: kilde/versjon og omfang → rader som trenger avklaring → bekreft import til denne familien. Vis kildeperiode og råverdi ved avvik, behold dato- og regnskapsklasseuklarheter som importutkast. Ingen automatisk gjettet dato, lånekobling eller eier. Ingen ekstra fiktive poster hvis importen feiler.

Etter import skal eieren kunne finne alle kildeposter, inkludert utkast med tydelig «Trenger avklaring». Bekreftede poster påvirker summer i riktig historisk måned, ikke dagens måned bare fordi importen skjedde i dag. Oppsummering og siste kildeperiode forklarer hva som ble lastet. Re-login og gjenkjøring beholder data uten dubletter. Dette forløpet er spesifisert, men ikke bygget eller demonstrert som en autentisert app.

Norskspråklig responsiv PWA for familiens felles månedsbudsjett i NOK. DESIGN.md er visuell referanse. Godkjent produktgrunnlag finnes i context.md; denne headless-utgaven foreslår konkrete samspill for menneskelig vurdering. Eksempelpersonene under er fiktive, ikke forskningsbaserte personas. Ingen UI-system eller teknisk stakk er valgt.

Alle medlemmer ser familiens delte data og kan endre egne poster. Administrator kan endre/slette alle poster, administrere invitasjoner, kategorier og grenser. Én familie per bruker. Lagring krever internettilgang. Tilgjengelig beløp er et budsjettanslag; det er ingen bankintegrasjon eller betalingsfunksjon.

## Information Architecture

| Flate | Inngang og innhold | Handlingsrett og visuell dekning |
|---|---|---|
| Logg inn / engangskode | E-post → kode → familieport. Endre e-post, send ny kode, ugyldig/utløpt kode. | Uinnlogget; mock finnes for e-post og kode. |
| Familieport | Opprett familie med navn, eller godta familieinvitasjon etter innlogging. Vis hvem som inviterer og hvilken familie. | Uten familie; mock finnes for oppretting og invitasjonsaksept. Bruker med eksisterende familie får forklaring fremfor nytt medlemskap. |
| Oversikt | Gjeldende måned, hovedbeløp, dagsramme, inntekt, forbruk, reserver, kategorier, regninger, mål og sammenligning. «Slik beregnes beløpet». | Alle; mock finnes. Månedvelger åpner historikk på samme flate. |
| Poster | Utgifter og inntekter, måned/filter, detalj, opprett/rediger/slett. Inntekt har Forventet eller Mottatt. | Alle leser; egne endres, admin alle. Mock finnes; detaljskjema er spine-only. |
| Budsjett | Kategorier, månedlig ramme, faktisk forbruk og overforbruk. Administrer kategorier og grenser. | Alle leser; admin skriver. Mock finnes; detaljskjema er spine-only. |
| Regninger | Kommende, forfalte og betalte; detalj, gjentakelse, beløp, forfall, «Merk som betalt». | Foreslått: alle kan markere systemregning betalt; eierskap/admin styrer øvrig redigering. Mock finnes; detaljskjema er spine-only. |
| Sparing | Mål, fremdrift, fast månedsbidrag, innskudd og ekstra innskudd; måldetalj. | Alle leser; foreslått admin for måldefinisjoner, alle kan sette inn; egne innskudd/admin alle. Mock finnes; detaljskjema er spine-only. |
| Mer | Lenker til Regninger og Familie og innstillinger; logg ut. | Alle; mock finnes. |
| Familie og innstillinger | Medlemmer/roller, familienavn, invitasjoner, konto/e-post, PWA-installasjonshjelp, in-app-varsler. | Admin sender/trekker invitasjoner og forvalter familie; andre ser forklaring. Mock finnes; detaljskjema er spine-only. |

Mobilmeny har nøyaktig **Oversikt · Poster · Budsjett · Sparing · Mer**. Regninger og Familie og innstillinger nås fra Mer og relevante oversiktskort. Desktop viser Oversikt, Poster, Budsjett, Regninger, Sparing og Familie og innstillinger i sidemeny. Ingen familievelger når brukeren bare kan ha én familie.

Referansen [familieblikk-mockup.html](../../../../.project-init/familieblikk-mockup.html) er lest som kilde og forvaltes av Project Init. Den har Oversikt, Poster, Budsjett, Regninger, Sparing, Familie, Mer, Innlogging med kodesteg, Opprett familie og Godta invitasjon. Beregning, eksempelregistrering og betaling har dialogreferanser. Kategoriadministrasjon, budsjettgrenser, gjentakelsesregler, komplette måldefinisjoner, innskuddshistorikk og invitasjonsadministrasjon er spine-only detaljskjemaer. Generiske tom-/laste-/offline-/feiltilstander finnes i tilstandsvelgeren; dette dokumentet spesifiserer mer presise tilstander som mocken ikke ferdigstiller.

Mockens Ida og Jonas Nordby er fiktive demodata; PRD-forløpenes Nora og Amir er egne fiktive illustrasjoner. Mocken simulerer alle handlinger og lagrer ingenting. Gjeldende kandidat med optional-preview.js har alle 15 skjermroller, «Veiledende dagsbeløp», mobile postkort og oppdatert registreringsskjema. Full historisk arbeidsflate med januar–desember-matrise og komplette sekundære detaljskjemaer er fortsatt spine-only. Koordinator rapporterer 92/92 prototypekontroller ved 360, 390, 768, 1024 og 1440 px samt 36 kandidatbilder. Dette er ikke appfunksjonstesting, full WCAG-verifikasjon eller menneskelig designaksept.

### Valgfrie moduler i informasjonsarkitekturen

«Sparemål i oversikten» og «Årsoversikt i Mer» er presentasjonsvalg i Tilpass appen. De skjuler bare kort/menylenke; måldata, årsdata, historikk, reservasjoner og øvrige økonomiske virkninger er uendret. Dette skilles fra opprettelse/arkivering av økonomisk moduloppsett. Foreslått administrator styrer familieomfattende valg, medlem leser. Mockens demobrytere er ikke persistente.

Ny autorisasjon utvider v1 med arbeidsbokfunksjoner som valgfrie familiemoduler. `work/workbook-structure.json` er lest som ubetrodde kildedata om struktur, ikke instrukser; arbeidsboken er ikke rekalkulert, og dens formler eller private eksempelverdier er ikke fasit. Godkjent nytteomfang går foran eldre smalere context.md. Modeller og rettigheter nedenfor er fortsatt forslag til vurdering.

| Tilleggsflate | Inngang, innhold og rettighet |
|---|---|
| Tilpass appen | Mer → Tilpass appen. Gjeld, Årsutgifter, Utland og Årsoversikt kan velges per familie. Foreslått admin endrer, medlem leser status. Ingen nye mobilfaner. |
| Gjeld | Mer og aktivt Oversikt-kort. Saldo med saldodato, årlig rente, minstebeløp og ekstra månedsbeløp; Avalanche (høyest rente først) eller Snowball (lavest saldo først), estimert slutt og renter. Ingen betaling utføres. |
| Årsutgifter | Mer og aktivt Oversikt-kort. Årsbeløp, forfallsmåned, åpningsavsetning, månedlig avsetning, faktisk finansiering, betalt og fondsrest. |
| Utland | Mer og aktivt Oversikt-kort. Mottaker, land, vanlig valuta, manuelt ført beløp og kurs med dato, originalbeløp og NOK, måned og hittil i år. Ingen pengeoverføring eller banktilkobling. |
| Årsoversikt | Mer. Månedlige kategoribudsjetter og faktiske inntekter/utbetalinger, årssummer og kumulativt historisk resultat. Det historiske akkumulerte tallet øker aldri ny måneds tilgjengelig. |

Ved deaktiverte aldri-konfigurerte moduler finnes ingen advarsler, tomkort eller reservasjoner. Slå av med lenkede data åpner Dialog som viser konsekvenser og krever eksplisitt bekreftelse: skjul/arkiver oppsett, bevar postkoblinger og historikk, og behold eksisterende økonomiske forpliktelser i beregningen med forklaring. En bryter kan aldri slette historie eller frigjøre avsetninger stille. Administrator må håndtere aktive forpliktelser gjennom en særskilt tillatt økonomihandling før de opphører. Gjenaktivering henter bevart oppsett. Detaljert arkiverings- og reservasjonsregel må godkjennes før implementasjon; hvis sikker håndtering mangler, blokker deaktivering med konkret årsak.

## Voice and Tone

Rolig bokmål med konkrete konsekvenser. «Lagret», «Forventet inntekt», «Mottatt inntekt», «Ubetalte regninger», «Reservert til sparing» og «Tilgjengelig å bruke» er faste begreper. Unngå skyld og belønninger rundt privatøkonomi.

| Situasjon | Tekst |
|---|---|
| Dagsramme | «Budsjettanslag per dag. Ikke en bankbeholdning eller garanti.» |
| Underskudd | «Underskudd denne måneden. Se beregningen og planlagte reserver.» |
| Offline | «Du er frakoblet. Koble til internett for å lagre.» |
| Lagrefeil | «Vi kunne ikke lagre. Opplysningene står i skjemaet. Prøv igjen.» |
| Annen eiers post | «Bare den som opprettet posten eller en administrator kan endre den.» |
| Tom måned | «Ingen poster denne måneden. Legg til første inntekt eller utgift.» |
| Inntekt | «Forventet inntekt er til planlegging og er ikke med i tilgjengelig beløp.» |

## Component Patterns

| Komponent | Atferd |
|---|---|
| Navigation | Aktiv side markeres og annonseres. Tilbake beholder valgt måned/filter. Hovedinnhold får fokus etter sidenavigasjon. |
| Metric | «Slik beregnes beløpet» åpner Dialog med regnestykke, dato og hva som er inkludert. Historikk viser månedsresultat uten dagsramme. Forventet inntekt blandes aldri med mottatt. |
| Button | Lagre låses under forespørsel og viser «Lagrer…». Suksess først etter bekreftet lagring. Nytt klikk/retry skal ikke gi ekstra innskudd eller utgift. |
| Form | Synlige etiketter, valuta/dato, eier og kategori der relevant. Utgift: beløp, dato, kategori, beskrivelse. Inntekt: beløp, dato, beskrivelse, Forventet/Mottatt. Betalingsdato kreves ved Mottatt. Bevar gyldige felt ved feil. |
| List | Klikk/Enter på rad åpner detalj. Egen tekstet handlingsmeny med rediger/slett der tillatt. Filter angir aktiv måned, type og eventuell status; null treff tilbyr å nullstille filter. |
| Progress | Vis alltid tellere i tekst. Kategorioverskridelse har «X kr over budsjett». Målprogresjon bæres videre til neste måned. |
| Dialog | Åpning flytter fokus inn, Escape/Avbryt lukker og returnerer fokus. Sletting oppgir konkret navn og beløp. Ulagrede endringer varsles ved navigasjon. Beregningsdialog er lesbar uten handling. |
| Feedback | Status annonseres uten å stjele fokus. Ved manglende rettighet skjules skrivehandlinger med synlig forklaring i detaljen; direkte lenke gir begrenset-tilgang-flate. |

Foreslåtte regningsfelt: navn, beløp, kategori, forfallsdato, gjentakelse og oppretter. Før «Merk som betalt» vises beløp og dato og at handlingen registrerer en utgift; appen betaler ingen regning. AD-2 foreslår at alle medlemmer kan markere systemgenererte familieregninger betalt; dette er en uttrykkelig unntaksregel til eierskapsredigering, til godkjenning. AD-3 foreslår 10 minutters kode, 60 sekunders sendepause og 7 dagers invitasjon. Vis reelle frister og begrensninger fra tjenesten. Invitér viser e-post og familie før sending. Utløpt, tilbakekalt eller feil konto gir forklaring og vei til administrator, uten å vise andre familiers økonomi.

## State Patterns

Felles gulv for alle dataskjermer: layouttilpasset lasting, feil med prøv igjen, merket sist oppdaterte data ved stale visning, synlig tastaturfokus og begrenset tilgang. AD-8 foreslår ingen offline familielesing: erstatt privat innhold med generisk «Koble til for å se budsjettet». Ingen frakoblede endringer settes i kø; et åpent skjema kan beholde tekst i minnet mens siden står åpen, uten lagringsløfte. Ikke cache familiesvar eller vis gamle familiers data etter utlogging/medlemskapsendring. Forslaget samsvarer med mockens offlineflate og er fortsatt til menneskelig vurdering.

| Flate | Spesifikke tom-, feil- og grenseforhold |
|---|---|
| Innlogging/kode | Tom e-post, ugyldig adresse, sender, sendefeil, kodefeil, utløpt kode, for mange forsøk og offline. Bevar e-post; vis tjenestens faktiske frister etter foreslått AD-3, ikke lokal demonstrasjonsnedtelling som sikkerhetsgaranti. |
| Familieport/invitasjon | Ingen familie, opprettingsfeil, ugyldig/utløpt/tilbakekalt invitasjon, allerede medlem, allerede i annen familie, mottaker stemmer ikke. Ingen stille flytting mellom familier. |
| Oversikt/historikk | Ingen inntekter eller poster gir nullverdier med forklaring; forventet inntekt kan fortsatt vises. Negativt tilgjengelig synlig. Manglende sammenligningsmåned: «Ingen sammenligning ennå». Delvis lasting må ikke se ut som et fullstendig regnestykke. |
| Poster | Ingen poster, ingen filtertreff, slettet post, annen eiers post, mottatt/forventet. Samtidig endret post gir lesbar konflikt og henting av ny versjon; ikke overskriv stille. |
| Budsjett | Ingen kategorier, kategori uten ramme («Ingen ramme satt»), nullramme og overforbruk. Medlemmer ser lesevisning med adminforklaring. Historiske rammer endres ikke ved redigering av nåværende måned. |
| Regninger | Ingen regninger, kommende, forfalt, betalt, båret fra forrige måned, lagrefeil og allerede betalt ved samtidig handling. Betalt-status returneres fra lagring; dobbelt betaling lager ikke ny utgift. |
| Sparing | Ingen mål, null fremdrift, nådd/overfylt mål, ingen månedsinnskudd, ekstra innskudd, feil og begrenset rettighet. «Planlagt» og «Satt inn» har separate etiketter. |
| Mer/familie | Ingen varsler, ingen ventende invitasjoner, medlem/admin, sending, sendt, feil, tilbakekalt, rolle endret under åpent skjema. Siste admin og utmelding er uavklarte produktvalg og tilbys ikke uten avklart regel. |

## Interaction Primitives

Valgfri modul: av → aktivering/oppsett → aktiv uten data → aktiv med data → skjult/arkivert med bevarte koblinger. Tilpass appen viser familieomfang og hvem som kan endre. Bryterens lagring følger samme nett-, feil- og konfliktregler som andre skjemaer; vis aldri aktivt modulvalg før lagring er bekreftet. Gjeld har «Manglende rente/saldodato», «Planen dekker ikke renter» og «Ingen beregnbar sluttdato» fremfor falsk null. Årsfond kan være underfinansiert/negativt med beløp i tekst. Utland uten kurs viser «NOK-beløp kan ikke beregnes» og blokkerer bokføring inntil gyldig kurs eller faktisk NOK-beløp er oppgitt. Årsoversikt uten historikk viser manglende data, ikke målte null. Tilleggsflater arver lasting, tomtilstand, offline og rettighetsfeil fra felles tilstandsmønster.

Trykk, klikk og tastatur gir samme funksjoner. Ingen sveip, dra eller hover er påkrevd. Beløpsfelt åpner desimaltastatur, e-post bruker e-posttastatur, kode kan limes inn og støtter tilgjengelig autofyll. Ingen automatisk lagring ved blur. Kalenderfelt lar dato skrives direkte.

Månedbytte oppdaterer alle tall, lister og etiketter samlet. Vis tydelig «Oktober 2026» og «Historikk» for avsluttet måned. I inneværende måned sammenlignes samme kalenderdagsspenn (eksempel 1.–20.) i hver sammenligningsmåned; avsluttede måneder sammenlignes i sin helhet. Kortere måneder avgrenser spennet til siste dato. In-app-varsler gjelder kommende/forfalte regninger; ingen e-post eller push utover e-postkode/invitasjon er en varslingskanal i scope.

## Accessibility Floor

Mål: WCAG 2.2 AA, må verifiseres ved implementasjon. Dokumentets språk er nb; overskrifter, landmarks, knapper, tabeller og skjemaetiketter er semantiske. Alle trykkflater minst `{spacing.touch}`, synlig fokus bruker `{colors.focus}`. Vanlig tekst `{colors.text}` og `{colors.muted}` må møte DESIGN.md sine kontrastmål.

Feil knyttes til felt og oppsummeres ved innsending med fokus på første feil. Resultat/status får rolig live-annonsering; KPI-endringer annonseres samlet, ikke siffer for siffer. Fremdrift har tilgjengelig navn, nåverdi og maksimum; overforbruk finnes som tekst. Ved 200 % tekst og 320 CSS-px bredde beholdes funksjoner uten horisontal siderulling. Redusert bevegelse respekteres; ingen informasjon krever animasjon.

## Responsive & Platform

Ved høyst 850 px viser mocken bunnmeny, over 850 px sidemeny. Høyst 600 px gir én innholdskolonne, mellom 601 og 850 px beholdes noen to-kolonnegrupper. Detaljskjema på mobil foreslås som helskjerm; mocken bruker foreløpig dialog på alle størrelser. Fast Lagre/bunnmeny må aldri dekke felt, feil eller tastaturfokus. Installasjon er et frivillig valg med nettlesertilpasset hjelp; vanlig nettleser er en fullverdig inngang. Ingen mørk modus eller native app forutsettes.

## Beregningskontrakt til vurdering

Godkjente prinsipper: bare mottatt inntekt teller; ubetalte regninger og planlagt sparing reserverer; betaling erstatter regningsreserve med utgift én gang; spareinnskudd skal ikke trekkes dobbelt; månedlig forbruk/nullstilling og historikk må skilles.

**Foreslått samlet kontrakt, ikke endelig godkjent:** Arkitekturens AD-10 er autoritativ for utvidet beregning: A = I + W_netto − E − B − S_netto − G − F. For hvert mål er N brutto innskudd minus brutto uttak i måneden; S_netto = sum max(plan, max(N,0)), W_netto = sum max(−N,0), beregnet per mål før summering. I er mottatt inntekt, E ordinære netto utgifter inkludert Utland, B ordinære ubetalte regninger, G gjeldsreserve og F årsavsetning. Uttak/gjeninnskudd innen samme månedsplan skaper dermed ikke nytt handlingsrom. Oversparing på ett mål oppveier ikke et annet måls plan. Dagsramme deler A på gjenstående dager inkludert i dag, bare i gjeldende måned. Dato, øreavrunding og regnskapsklasser følger foreslått AD-4–5 og AD-10–13, ikke en egen UX-beregningsmotor.

Historisk kontantresultat følger alle faktiske netto betalingsklasser i AD-10: mottatt inntekt + spareuttak − ordinære netto utgifter − netto gjeldsbetalinger − netto årsutgiftsbetalinger − spareinnskudd. Planer/reservasjoner er ikke kontantstrøm. Hold dette adskilt fra disponeringsindikatoren A og fra videreførbare mål-/fondssaldoer.

Fiktiv demo per 20. oktober 2026: mottatt 62 000 kr, utgifter 28 450 kr, ubetalte regninger 8 650 kr. Buffer plan 4 000 kr og innskudd 4 500 kr (4 000 ordinært + 500 ekstra); Ferie plan 2 000 kr og innskudd 0 kr. Sum plan 6 000 kr, faktisk 4 500 kr, reserve 6 500 kr. Tilgjengelig 18 400 kr; 12 dager inkludert i dag gir 1 533,33 kr/dag. Marker all demo som «Fiktive eksempeldata». Forventet inntekt står separat og påvirker ingen av disse tallene.

Foreslåtte presiseringer til godkjenning: administrator oppretter/endrer måldefinisjoner, alle medlemmer kan registrere innskudd; planendring gjelder valgt inneværende eller fremtidig måned og fremover, aldri avsluttet måned (AD-7). Uinnbetalt gammel plan blir historikk, ikke ny gjeld. Avklar fortsatt tilbakedatering/historiske postendringer, angre betalt regning, serieendringer og utmelding/siste administrator. AD-3 og AD-8 foreslår frister og offlinepolitikk som over; de er ikke lenger ubeskrevne alternativer. Grensekopiering, sammenligning og regningscarryover forklares uten å antyde overføring av gammelt tilgjengelig beløp.

## Key Flows

### 8 — Nora velger familiens moduler

1. Nora åpner Mer → Tilpass appen og ser hvilke funksjoner familien har aktivert.
2. Hun aktiverer Gjeld og Årsutgifter og bekrefter familiens valg; Amir ser de samme valgene med leseadgang.
3. **Vendepunkt:** Nye relevante sider finnes under Mer, mens mobilens fem hovedvalg er uendret.

Feil: lagrefeil beholder tidligere modulstatus. Deaktivering med lenkede data oppgir bevarte forpliktelser og historikk; avbryt endrer ingenting. Aldri brukt modul avslått gir ingen tomadvarsler.

### 9 — Amir undersøker gjeldsplanen

1. Han åpner Gjeld med registrert saldo/saldodato, rente, minimum og ekstra beløp.
2. Han sammenligner Avalanche og Snowball med synlige modellforutsetninger. Forslag: administrator lagrer plan/oppsett, alle kan undersøke alternativer uten å lagre; egne faktiske betalinger føres via Poster med gjeldskobling.
3. **Vendepunkt:** Han ser estimert sluttmåned og rentekostnad adskilt fra registrerte saldoer; dette er en prognose uten banktilgang.

Feil: manglende saldo/rente eller utilstrekkelig betaling gir forklaring fremfor oppdiktet gjeldfri dato. Betaling påvirker gjeld og månedens utbetaling én gang; nøyaktig rente- og reservasjonsmodell må vedtas i beregningskontrakten.

### 10 — Nora fordeler en årsutgift

1. Hun åpner Årsutgifter og registrerer årsbeløp, forfall og eventuell åpningsavsetning.
2. Appen viser foreslått månedsavsetning og avvik frem til forfall. Jevn årsfordeling foreslås som årsbeløp/12; første delår og underfinansiering vises eksplisitt.
3. **Vendepunkt:** Ved faktisk betaling kobles én post til årsutgiften; reserve/finansiering og utbetaling forklares uten dobbelt fradrag.

Feil: manglende finansiering vises som gap, ikke skjult gjeld. Samme forpliktelse kan ikke reserveres både som vanlig regning og årsutgift uten en eksplisitt erstatningskobling. Arkivering beholder historien og aktive forpliktelser.

### 11 — Amir registrerer penger sendt utenlands

1. Han velger aktiv Utland-modul fra Mer, mottaker, land, valuta, dato og beløp.
2. Han oppgir faktisk kurs eller dokumentert NOK-beløp og ser originalbeløp, NOK og eventuell avgift hver for seg.
3. **Vendepunkt:** Bekreftet post vises i måned og hittil i år og inngår én gang i familiens NOK-utbetalinger. Familieblikk har bare registrert handlingen, ikke overført penger.

Feil: manglende/ugyldig kurs blokkerer lagring. NOK er fast basis; kursendring for nye poster endrer ikke historisk bokført NOK stille. Ingen private mottakernavn eller saldoer fra arbeidsboken brukes i demo.

### 12 — Nora ser året og korrigerer en refusjon

1. Hun åpner Årsoversikt, velger år/måned og ser budsjett, faktisk og historisk kumulativt resultat med tydelige etiketter.
2. Hun åpner en opprinnelig utgift i Poster og velger Refusjon; foreslått eget positivt beløpsfelt, dato, kategori og kobling til originalen fremfor negativt utgiftsfelt.
3. **Vendepunkt:** Refusjonen reduserer faktisk netto utgift i refusjonsmåneden én gang og øker den månedens tilgjengelig. Historisk årssum oppdateres, men gammelt overskudd overføres aldri automatisk.

Feil: retur av allerede refundert beløp, refusjon uten original og refusjon som krysser år krever tydelige regler; forslag er samlet refusjon høyst originalbeløp og egen økonomisk dato. Admin korrigerer andres poster; medlemmer sine egne. Et historisk tall er aldri en lovnad om bankbeholdning.

### 13 — Amir følger et mer detaljert sparemål

1. Han ser åpning spart, målbeløp, måldato, faktisk fremdrift og planlagt månedsbeløp i Sparing.
2. Appen viser beregnet behov per måned og forventet ferdigdato som anslag; manglende måldato eller null sparefart viser «Kan ikke anslås».
3. Han registrerer et innskudd eller tillatt uttak med dato og mål. Foreslått administrator endrer åpningssaldo/målplan, medlemmer registrerer egne innskudd/uttak.
4. **Vendepunkt:** Fremdrift er åpning + faktiske innskudd − uttak. Plan alene skaper ingen fremdrift, og måldato gjør gapet forståelig.

Feil: uttak som overstiger målbeholdning på effektiv dato stoppes under foreslått regel. Ved redigering kontrolleres også alle senere målbevegelser, slik at ingen senere saldo blir negativ. Åpningssaldo er historisk grunnlag, ikke ny månedsinntekt. Uttak og gjeninnskudd følger AD-10 sin netto-per-mål-kontrakt over; de kan ikke gi negativ sparereserve eller kunstig handlingsrom. Reglene er foreslått til menneskelig aksept.

Sporing til PRD: **UJ-1 – Nora samler familien** dekkes av flyt 1 og 7 (FR-1–3); **UJ-2 – Amir sjekker handlingsrommet** av flyt 2 og 3 (FR-4–5, FR-11–12); **UJ-3 – Nora følger opp regninger** av flyt 5 (FR-8–9, FR-13); **UJ-4 – Amir sparer gjennom månedsskiftet** av flyt 4 og 6 (FR-6–7, FR-10). FR-14 dekkes av felles tilstander, plattformregler og feilbaner. Nora og Amir er fiktive illustrasjoner som i PRD. Egne slettinger er foreslått i PRD A2, ikke et nytt godkjent rettighetskrav.

### 1 — Nora kommer inn i familiens budsjett

1. Fiktive Nora åpner invitasjonen, ser familienavnet og oppgir e-post.
2. Hun limer inn engangskoden og bekrefter invitasjonen.
3. **Vendepunkt:** Oversikt viser riktig familie og hennes medlemsrolle. Ny bruker uten invitasjon oppretter i stedet familien i Familieport.

Feil: utløpt kode lar henne sende ny; ugyldig invitasjon tilbyr kontakt med administrator. Eksisterende familietilhørighet blokkerer nytt medlemskap med forklaring.

### 2 — Nora vil vite hva familien har igjen

1. Hun åpner Oversikt på telefon og ser valgt måned og 18 400 kr tilgjengelig.
2. Hun leser dagsramme og åpner «Slik beregnes beløpet».
3. Hun følger regningsreserven til Regninger og spareavsetningen til Sparing.
4. **Vendepunkt:** Hun kan forklare hvorfor beløpet avviker fra samlet inntekt. Hun velger forrige måned og ser historiske tall uten dagsramme.

Feil: ufullstendige data viser «Beregningen er ikke tilgjengelig ennå», med prøv igjen. Negativt resultat vises som underskudd.

### 3 — Amir fører utgift og mottatt inntekt

1. Fiktive Amir velger Poster → Ny post → Utgift, fyller beløp, dato og kategori og lagrer.
2. Han ser bekreftet post og oppdatert kategori. Han kan redigere eller slette sin egen post med bekreftelse.
3. Han oppretter forventet lønn; tilgjengelig er uendret. Når lønnen kommer, endrer han samme inntekt til Mottatt med dato.
4. **Vendepunkt:** Det er én inntektspost, og tilgjengelig øker først ved mottak.

Feil: offline blokkerer lagring og beholder skjema mens det er åpent. En annen eiers post er lesbar uten redigering; admin kan korrigere den. Samtidig endring krever ny innlasting.

### 4 — Nora planlegger kategorier og neste måned

1. Nora som administrator åpner Budsjett, legger til kategori og setter felles månedsramme.
2. Hun ser brukt/ramme og tekst om overforbruk. Et vanlig medlem ser samme oversikt med leseadgang.
3. Ved ny måned ser hun kopierte kategorier/rammer, nullstilt månedsforbruk og gamle rammer i historikken.
4. **Vendepunkt:** Sammenligningen forklarer utviklingen uten at gammelt overskudd blir nytt tilgjengelig beløp.

Feil: lagrefeil beholder gammel bekreftet ramme og uendret historikk; ingen ramme viser en tekstetikett fremfor null som implisitt grense.

### 5 — Nora følger opp regninger (UJ-3)

1. Nora åpner forfalt regning fra Oversikt eller Mer → Regninger.
2. Hun kontrollerer beløp/dato og velger «Merk som betalt» for en post hun kan endre.
3. **Vendepunkt:** Regningen er Betalt, reservasjonen fjernes og én utgift vises i Poster. Tilgjengelig faller ikke dobbelt.

Feil: et samtidig klikk returnerer allerede betalt, uten ny utgift. Ubetalt regning ved månedsskifte er fortsatt synlig/reservert med opprinnelig forfall. Endring av gjentakelse krever avklart serieregel før bygging.

### 6 — Amir sparer gjennom månedsskiftet (UJ-4)

1. Amir åpner Sparing, velger Buffer og ser målprogresjon, månedsplan og faktiske innskudd hver for seg.
2. Han legger til 500 kr som ekstra innskudd og bekrefter.
3. **Vendepunkt:** Målet vokser, månedsreserven følger foreslått per-mål-regel, og tilgjengelig viser samme tall som beregningsforklaringen. Ved ny måned bæres målprogresjonen videre.

Feil: mislykket innskudd endrer ingen tall; retry gir ikke duplikat. Foreslått adminregel for måloppretting/planredigering og alle-medlemmer-regel for innskudd må godkjennes før bygging.

### 7 — Nora inviterer og Amir sjekker innstillinger

1. Nora åpner Familie og innstillinger fra sidemeny eller Mer, fyller mottakerens e-post og sender invitasjon.
2. Hun ser Sendt og kan trekke en ventende invitasjon tilbake. Amir som medlem ser medlemmer og egen konto uten adminhandlinger.
3. Amir åpner in-app-varsel til en regning, går tilbake og finner frivillig installasjonshjelp.
4. **Vendepunkt:** Familien deler rett budsjett, og rollene gjør det tydelig hvem som kan endre hva.

Feil: sendefeil bekrefter ikke sending. Rolleendring under et skjema stopper lagring med forklaring. Utlogging fører til innlogging og fjerner familieinnhold fra skjermen.





## Godkjent endring 2026-10-20 — forhåndsregistrert eier

Robel svarte på SMTP-/kodeavklaringen: «nei ikke kode bare pre-registered hvis det er greit for forst omgang». Dette endrer innloggingskravet for første eier: en eksplisitt lokalt forhåndsregistrert konto med passord kan eie familien og bekrefte kildeimport uten SMTP. E-postadressen er eierbinding fra brukerens instruksjon; den skal ikke feilaktig merkes e-postverifisert. Bevar separat opphavsmetode for kontoen/medlemskapet og autentisert passordøkt. Passord hasjes med Django, behandles privat, aldri i Git/image/logg. Ingen anonym tilgang, automatisk konto-overtakelse eller globale startdata. Eksisterende engangskodeflyt bevares for senere bruk. Privat kilde kan importeres bare til denne eksplisitt bundne eierens egen familie; idempotens, avklaring, avstemming, isolasjon og persistenskrav gjelder fortsatt. Ingen nye avhengigheter eller ekstern utrulling følger av endringen.


### Utvidelse av forhåndsregistrering — godkjent av Robel

«ikke bare meg men som admin jeg kan også registrere familien og andre familie». Familieadministratorer kan opprette egne familiemedlemmer med passord uten e-postkode. Den eksplisitt klargjorte eieren får en separat registreringsrett til å opprette andre private familier med egen administrator. Registreringsrett gir ikke budsjettinnsyn eller medlemskap i de andre familiene. Vanlige medlemmer kan ikke registrere brukere; andre familieadministratorer kan bare administrere egen familie med mindre separat registreringsrett gis eksplisitt. Eksisterende kontoer overtas ikke, og én familie per bruker gjelder. Nye familier starter tomme; Robels kilde er fortsatt bare hans egen familie. Gjeldende passordregler, CSRF, økter, feilforsøksgrenser og hemmelighetsgrenser gjelder alle forhåndsregistrerte kontoer.
