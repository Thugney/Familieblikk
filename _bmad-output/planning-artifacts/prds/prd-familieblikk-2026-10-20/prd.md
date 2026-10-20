---
title: Familieblikk – produktkrav
status: draft
created: 2026-10-20
updated: 2026-10-20
sources: [context.md, addendum.md]
approval: Produktomfang godkjent; beregningsdetaljer og visuell utforming venter på menneskelig godkjenning.
---

# PRD: Familieblikk

## Formål og visjon

**Senere autorisert presisering:** Arbeidsboken er Robels faktiske familiebudsjett. Kravet FR-22 nedenfor erstatter tidligere formuleringer om at faktisk import ikke er autorisert. Den skal både inspirere funksjonene og levere startdata til hans egen verifiserte familieprofil i v1. Lagring av kilde og importforberedelse er autorisert; endelig designaksept og appimplementasjon er fortsatt separate steg.

Familieblikk er en gratis, norskspråklig budsjettapp i NOK for familier som vil forstå hva de kan bruke nå, samtidig som regninger og sparing er tatt høyde for. En rolig oversikt skal gjøre forskjellen mellom forventet inntekt, mottatte penger og allerede reserverte penger forståelig. Beløpene er budsjettanslag, ikke bankbalanse eller en økonomisk garanti.

Dette dokumentet gir krav til UX, arkitektur og senere oppgaver. Godkjent produktgrunnlag er `context.md`; ingen brukerundersøkelse, markedsanalyse eller dokumentert brukereffekt foreligger. Krav-ID-er beholdes ved senere revisjon. Dokumentet er et utkast til gjennomgang, ikke tillatelse til å implementere. Teknologier og leverandører velges senere. Arbeidsboken E:\Family_Budget_Expandable.xlsx er senere tilført som referanse til dagens arbeidsflyt; inspeksjon og avgrensning er dokumentert i addendum.md. Den endrer ikke godkjent omfang.

## Målgruppe og behov

Medlemmer av en husholdning skal kunne registrere egne inntekter og utgifter, forstå familiens samlede handlingsrom og følge regninger og sparemål. Administratorer skal i tillegg styre deltakelse og felles budsjettoppsett. En bruker tilhører én husholdning; flere uavhengige husholdninger kan bruke tjenesten.

### Illustrerende brukerforløp

Forløpene nedenfor er konstruerte eksempler fra godkjent omfang, ikke faktiske intervjuobjekter eller bekreftet brukeratferd.

- **UJ-1 – Nora samler familien.** Nora logger inn med e-postkode, oppretter en husholdning og inviterer Amir. Amir bekrefter invitasjonen gjennom innlogging. Begge ser husholdningens data; en invitasjon til en annen husholdning må håndteres uten å opprette dobbelt medlemskap.
- **UJ-2 – Amir sjekker handlingsrommet.** Amir åpner oversikten på mobilen. Forventet lønn vises separat. Etter at han registrerer lønnen som mottatt, øker tilgjengelig beløp. En ny matutgift reduserer beløpet og oppdaterer kategoriens forbruk. Beregningsforklaringen viser hvilke summer som inngår.
- **UJ-3 – Nora følger opp regninger.** Nora ser en forfalt, ubetalt regning fra forrige måned. Den reserverer fortsatt penger. Hun markerer den betalt; reservasjonen erstattes av én utgift. Et nytt trykk skal ikke opprette en ny utgift.
- **UJ-4 – Amir sparer gjennom månedsskiftet.** Et sparemål har planlagt månedsbeløp. Amir registrerer et innskudd, og fremdriften øker uten at månedsbeløpet trekkes på nytt. Neste måned videreføres fremdriften, mens månedens inntekter og utgifter starter på nytt.

## Begreper

| Begrep | Betydning |
|---|---|
| Husholdning | Avgrenset fellesskap med egne medlemmer, kategorier, inntekter, utgifter, regninger og sparemål. |
| Medlem / administrator | Medlem eier egne registreringer; administrator kan også endre og slette andres registreringer og administrere felles oppsett. |
| Budsjettmåned | Kalenderperioden som oversikten og kategoriens månedsgrense gjelder for. |
| Forventet / mottatt inntekt | Planlagt inntekt / inntekt registrert som faktisk mottatt. Bare sistnevnte gir handlingsrom. |
| Utgift | Registrert faktisk forbruk, inkludert én utgift per betalt regningsforekomst. |
| Regningsforekomst | Én konkret betalingsforpliktelse med beløp, forfallsdato og betalingsstatus; tilbakevendende regninger gir egne forekomster. |
| Reservasjon | Beløp holdt av til en ubetalt regningsforekomst eller planlagt sparing. |
| Månedsgrense | Husholdningens felles budsjett for én kategori i én budsjettmåned. |
| Planlagt sparing / innskudd | Beløp reservert til sparemål / faktisk registrert overføring til sparemål. Innskudd er ikke vanlig forbruk. |
| Tilgjengelig beløp | Mottatt inntekt minus utgifter og gjenstående reservasjoner etter reglene nedenfor. Kan være negativt. |
| Dagsbeløp | Budsjettanslag for tilgjengelig beløp fordelt på gjenstående kalenderdager. |

## Funksjonelle krav

### Tilgang og samarbeid

**FR-1 – Innlogging.** Brukeren kan logge inn med engangskode sendt til e-post. Akseptanse: gyldig kode åpner riktig bruker; feil, utløpt eller allerede brukt kode gir ingen tilgang og viser en forståelig feil. Eksakte kodegrenser fastsettes i arkitekturen før implementering.

**FR-2 – Husholdning og invitasjon.** Brukeren kan opprette en husholdning og administrator kan invitere familiemedlemmer. Akseptanse: godtatt invitasjon gir tilgang bare til angitt husholdning; gjentatt godkjenning oppretter ikke dobbelt medlemskap; en bruker som allerede har en husholdning kan ikke bli medlem av en til (UJ-1). Håndtering av bytte og siste administrator er åpent i OQ-3.

**FR-3 – Rettigheter.** Alle medlemmer ser delte registreringer og kan endre egne; administrator kan endre/slette alle og styre invitasjoner, kategorier og månedsgrenser. Akseptanse: medlem kan ikke endre en annens registrering eller felles oppsett ved direkte forespørsel; avvist handling endrer ingen data. [ASSUMPTION A2: Medlemmer kan også slette egne registreringer.]

### Inntekter, utgifter og kategorier

**FR-4 – Inntekt.** Medlem registrerer beløp, dato og forventet/mottatt status for egen inntekt. Akseptanse: husholdningens mottatte inntekter summeres; forventet inntekt vises separat og gir null bidrag til tilgjengelig beløp; en statusendring teller inntekten én gang (UJ-2).

**FR-5 – Utgifter.** Medlem registrerer egen utgift med beløp, dato og kategori. Akseptanse: lagret utgift oppdaterer husholdningens månedsforbruk, kategori og tilgjengelig beløp én gang; retting eller tillatt sletting erstatter tidligere påvirkning og legger den ikke oppå. Beløp må være positivt og ha høyst to desimaler. Refusjoner følger utvidelsen i FR-20.

**FR-6 – Kategorier og grenser.** Administrator vedlikeholder kategorier og én felles månedsgrense per kategori. Akseptanse: alle medlemmer deler samme grense; kategorier har navn og farge; historiske utgifter beholder lesbar kategori når kategorien ikke lenger brukes; grenseendring for oktober endrer ikke september.

**FR-7 – Månedsskifte.** Ny budsjettmåned starter med null nye inntekter og utgifter, og viderefører kategorier og deres grenser. Akseptanse: overskudd fra forrige måned øker ikke nytt tilgjengelig beløp; historikk bevares; ubetalte regningsforekomster og sparemålsfremdrift videreføres (UJ-4). [ASSUMPTION A1: Europe/Oslo og kalenderdato styrer måned og dag; mottaksdato styrer inntekt, betalingsdato styrer utgift.]

### Regninger og sparing

**FR-8 – Tilbakevendende regninger.** Familien registrerer tilbakevendende regninger med beløp og forfall. Akseptanse: hver aktuell forekomst vises én gang; ubetalte forekomster fra tidligere måneder beholder identitet og reservasjon; en gammel forekomst kopieres ikke til en ekstra gjeldspost ved månedsskifte. [ASSUMPTION A3: Første versjon støtter månedlig gjentakelse; forfallsdag 29–31 flyttes til siste dag når måneden er kortere. Andre intervaller avklares i OQ-2.]

**FR-9 – Betaling.** En tillatt handling markerer en regningsforekomst betalt og oppretter én tilknyttet utgift. Akseptanse: betaling og fjerning av reservasjon lykkes samlet; dobbeltklikk, gjentatt forespørsel og samtidige betalingsforsøk gir totalt én utgift; betalt regning reserverer null. Betaling av gammel regning teller i betalingsmåned under A1 (UJ-3). Endring/sletting av en tilknyttet utgift kan ikke etterlate motstridende betalingsstatus; konkret korrigeringsflyt avklares i OQ-4.

**FR-10 – Sparemål.** Familien kan ha sparemål med målbeløp, fast månedsbeløp og innskudd, inkludert ekstra innskudd. Akseptanse: fremdrift er summen av faktiske innskudd og videreføres; planlagt sparing alene øker ikke fremdrift; ingen innskudd regnes som vanlig utgift i tillegg til sparingstrekket. [ASSUMPTION A4: Uten uttak beregnes fradrag per sparemål som maks(planlagt månedsbeløp, faktiske innskudd i måneden). Ved uttak gjelder nettoformelen i samlet beregningskontrakt. Uinnbetalt plan for en avsluttet måned blir historikk, ikke ny gjeld. Endring av plan gjelder valgt måned og fremover, ikke avsluttede måneder.]

### Oversikt og appopplevelse

**FR-11 – Beregning og forklaring.** Oversikten viser tilgjengelig beløp og dagsbeløp, med forklaring av mottatt inntekt, utgifter, regningsreservasjoner og sparing. Akseptanse: negative beløp vises med minus; forventet inntekt merkes tydelig; eksemplene i beregningskontrakten består; teksten forklarer at beløpet er et budsjettanslag (UJ-2).

**FR-12 – Månedsoversikt og historikk.** Oversikten viser faktisk forbruk mot månedsgrense per kategori, kommende/forfalte regninger, sparemålsfremdrift og historiske sammenligninger. Akseptanse: valgt måned merkes; historikk bruker den månedens grenser; overforbruk vises numerisk og med tekst, ikke bare farge. [ASSUMPTION A5: For åpen måned sammenlignes dag 1 til i dag med samme datospenn i forrige måned, avkortet til siste dato når måneden er kortere. Avsluttede måneder sammenlignes som hele måneder. Absolutte summer brukes; manglende historikk vises som manglende data, ikke målt null.]

**FR-13 – Varsler.** Kommende og forfalte regninger gir varsler inne i appen. Akseptanse: ubetalte forfalte forekomster kan identifiseres fra appen; betalte forekomster fremstår ikke som ubetalte; ingen eksterne varsler sendes. Varslingsvindu avklares i OQ-2.

**FR-14 – PWA og nettkrav.** Appen fungerer på mobil og desktop med norsk tekst og NOK, og kan installeres der nettleseren støtter det. Akseptanse: støttede installerte flater åpner som app; frakobling viser tydelig tilstand; lagring uten nett avvises uten å late som den lyktes. Lasting, tomtilstand, feil og manglende rettigheter har egne forståelige tilstander. Ulagret inndata ved feil beholdes der det er mulig, og ny sending må ikke duplisere en lagret registrering.

## Beregningskontrakt til godkjenning

Detaljene under er et presiseringsforslag under A1 og A4, ikke en ny godkjent produktbeslutning. UX og arkitektur kan illustrere dem, men implementering må vente på menneskelig bekreftelse.

For aktiv budsjettmåned m:

- I = mottatte inntekter med mottaksdato i m.
- E = faktiske utgifter med betalingsdato i m. Innskudd til sparemål er utelatt.
- B = summen av ubetalte regningsforekomster med forfall senest ved utgangen av m, også eldre forfalte forekomster. Senere måneders forekomster er utelatt.
- P(g) = planlagt sparing i m for sparemål g; D(g) = faktiske innskudd til g i m.
- S = summen av maks(P(g), D(g)) per sparemål i kjernescenario uten uttak. En overbetaling til ett mål dekker ikke planen til et annet mål.
- Tilgjengelig beløp A = I − E − B − S.
- Dagsbeløp = A / antall kalenderdager igjen i m, inkludert i dag. [ASSUMPTION A6: Beregningen beholder presisjon; dagsbeløpet rundes ned mot minus uendelig til nærmeste øre. Oversikten viser hele NOK ved å runde videre ned, mens detaljforklaringen viser to desimaler. Negativt dagsbeløp beholdes. Dette er foreslått avrunding, ikke godkjent design. Avsluttede måneder viser historisk tilgjengelig beløp og ikke et dagsbeløp beregnet med dagens dato.]

Regningseksempel: I=30 000, E=5 000, B=10 000, P=2 000, D=0 gir A=13 000. Innskudd på 2 000 gir fortsatt A=13 000; D=2 500 gir A=12 500. Når en reservert regning på 1 000 betales, blir E=6 000 og B=9 000: A forblir 12 500. Gjentatt betalingsforsøk endrer ingenting.

Månedsskifteeksempel: Ny måned har I=0, E=0, ubetalt gammel regning B=1 000 og ny plan P=2 000. A=−3 000 selv om forrige måned hadde overskudd. Når 20 000 faktisk mottas, blir A=17 000. Ingen forventet inntekt påvirker disse summene.

Historikk må skille periodens forbruk fra senere betaling av gammel gjeld. [ASSUMPTION A7: Historisk oversikt viser reservasjoner ved månedsslutt og forbruk etter effektive datoer. Dette kan lagres som et månedsbilde eller rekonstrueres fra daterte hendelser; lagringsmåten avgjøres i arkitekturen. En regning betalt senere var fortsatt reservert ved tidligere månedsslutt. Rettelser med historisk effektiv dato kan oppdatere tidligere tall og merkes; dagens betalingsstatus brukes aldri som historisk fasit.]

## Kvalitetskrav og akseptanse

Disse tersklene er foreslåtte, målbare akseptansekrav, ikke målte resultater. [ASSUMPTION A8: Produktansvarlig bekrefter terskler og testgrunnlag før implementering.]

- **NFR-1 – Isolasjon:** Alle lese- og skrivehandlinger må avvise en bruker uten medlemskap i aktuell husholdning. Akseptanse omfatter to husholdninger, kjente fremmede post-ID-er og alle datatyper i FR-2–FR-13. Ingen data eller summer fra fremmed husholdning returneres.
- **NFR-2 – Konsistens:** Betaling, inntektsstatus og innskudd skal gi samme summer ved oppfriskning, gjentatt forespørsel og to samtidige handlinger. Test med minst to klienter skal gi én effekt per handling; avvist lagring gir null effekt. Konflikter må vises og skal ikke usynlig overskrive nyere data.
- **NFR-3 – Tilgjengelighet:** Alle primærflyter kan brukes med tastatur; fokus er synlig, felter har navn og feil knyttes til felt. Normal tekst har minst 4,5:1 kontrast. Farge er aldri eneste betydningsbærer. Primærflyter testes ved 200 % tekstforstørrelse.
- **NFR-4 – Responsivitet:** Ved bredder 360, 768 og 1440 CSS-piksler kan primærflytene gjennomføres uten horisontal siderulling eller skjulte handlinger. Formatering bruker norsk beløps- og datoformat konsekvent.
- **NFR-5 – Respons:** Med testdata for 24 måneder, 5 medlemmer og 10 000 registreringer skal oversikt være brukbar innen 3 sekunder og lagringsbekreftelse innen 2 sekunder ved minst 95 av 100 målinger under avtalt testnett. [ASSUMPTION A8: Testnett er 10 Mbit/s og 100 ms rundtur; endelig nettlesermatrise og målepunkt fastsettes før implementering.]
- **NFR-6 – Personvern:** Ingen engangskoder eller private budsjettbeløp i vanlig diagnostikk. Utlogging fjerner tilgang til husholdningsdata på en delt enhet; frakoblet visning og mellomlagring må ikke gi neste bruker tilgang. Sletting, oppbevaring og gjenoppretting besluttes i OQ-5 før lansering; ingen påstand om juridisk etterlevelse er verifisert.

## Omfang og uttrykk

Første versjon omfatter FR-1–FR-21 etter omfangsendringen 2026-10-20. Den er gratis og har et rolig, lyst uttrykk, tydelige kategorifarger og lesbare beløp. Foreslått grønn aksent, off-white bakgrunn og mobil/desktop-navigasjon i `context.md` er designretning, ikke akseptert design.

Bankintegrasjon, automatisk betaling, bankbalanse, investeringsråd, medlemsvise grenser, flere husholdninger per bruker, mørk modus og varsler utenfor appen er utenfor godkjent omfang. Registrering av innskudd eller utenlandsoverføring utfører ingen bankoverføring. Import av Robels konkrete kilde til egen verifisert familie er autorisert og påkrevd i FR-22; generelt offentlig importprodukt eller globale seeddata følger ikke av dette. Valutakonvertering til fast NOK, refusjoner og spareuttak er inkludert gjennom FR-18–FR-20, med beregningsdetaljer til godkjenning.

## Suksess og motmål

Ingen kvantitative adopsjonsmål, brukertestresultater eller forretningsgevinster er godkjent. Foreslått releasekriterium er at alle akseptansekriterier består og at Robel godkjenner visuell utforming og beregningsforklaring. Foreslått senere brukervalidering: et familiemedlem kan forklare hvorfor tilgjengelig beløp endret seg ved inntekt, regning og innskudd uten hjelp. Rekruttering og terskel avtales før testen. Flere registreringer eller lengre skjermtid er ikke suksessmål; de kan skjule ekstra arbeid og misforståelser.

## Åpne beslutninger og forutsetninger

Robel eier produktbeslutningene; arkitektur- og UX-ansvarlige foreslår løsninger.

| ID | Beslutning og tidspunkt |
|---|---|
| OQ-1 | Bekreft A1, A4, A6 og A7: tidsgrenser, månedlig sparetrekk, dagsbeløp og historisk reservasjon. Blokkerer implementering av beregningene; design kan vise tydelig merkede forslag. |
| OQ-2 | Bekreft A3, tillatte gjentakelsesintervaller og hvor tidlig kommende regninger varsles. Før regningsoppgaver anses implementeringsklare. |
| OQ-3 | Bekreft A2 og regler for medlemsfjerning, husholdningsbytte, gjeninvitert bruker, siste administrator og eierskap til gamle registreringer. Før tilgangsoppgaver anses implementeringsklare. |
| OQ-4 | Bestem korrigering av betalte regninger, refusjoner og eventuelle spareuttak; minimum er at rettinger bevarer regningskobling og korrekte summer. Før relevante oppgaver er implementeringsklare. |
| OQ-5 | Oppbevaring, kontosletting/husholdningssletting, gjenoppretting, driftsansvar og tilgang til frakoblet historikk. Arkitektur må foreslå avgrenset løsning før lansering. |
| OQ-6 | Bekreft A5 og A8, støttede nettlesere og brukerprøve. Før endelig testplan og lanseringsakseptanse. |
| OQ-7 | Valider at den godkjente utvidelsen FR-15–FR-21 dekker familiens faktiske arbeidsflyt og prioriter hvilke moduler de ønsker. Før v1 omtales som full erstatning for arbeidsboken. |

Forutsetningsindeks: **A1** kalender/tidssone og bokføringsdato; **A2** sletting av egne registreringer; **A3** månedlig gjentakelse og kort måned; **A4** spareberegning og planendringer; **A5** historisk sammenligning; **A6** dagsbeløp/avrunding; **A7** historisk reservasjon; **A8** foreslåtte kvalitetsterskler/testgrunnlag. Alle er foreslåtte presiseringer, ikke godkjente utvidelser.

## Overlevering og status

Kildegjennomgang mot `context.md` er utført under utarbeidelsen: godkjent omfang er dekket, og tekniske valg er holdt åpne. En separat uavhengig gjennomgang organiseres av orkestratoren etter at PRD, UX og arkitektur foreligger. Dette er ingen utført brukertest eller godkjenningsgate. Endelig menneskelig godkjenning av design og åpne beregningsbeslutninger gjenstår; implementering er ikke autorisert.


## Omfangsendring godkjent 2026-10-20: valgfrie Excel-funksjoner

Dette avsnittet erstatter tidligere utelatelser av gjeldsmodul, årsavsetninger, utenlandsoverføringer, utvidede sparemål og refusjoner. Robel godkjente i samtalen å inkludere funksjonene i arbeidsboken og la familien velge om de vil bruke dem. Godkjenningen gjelder produktomfang og planlegging; implementering, faktisk dataimport og endelig beregningsdesign er fortsatt ikke godkjent. NOK forblir fast basisvaluta. Tidligere FR-ID-er beholdes; FR-10, FR-12 og FR-5 utvides av kravene nedenfor.

**FR-15 – Valgfrie moduler og preferanser.** Administrator kan aktivere gjeld, årsavsetninger og utenlandsoverføringer per husholdning; sparemålsdelen på oversikten og inngangen til årsvisning kan også skjules etter familiens behov. Disse to synlighetsvalgene endrer ingen planer, beregninger eller posteringer; sparefunksjoner og historikk forblir tilgjengelige via øvrig navigasjon. Akseptanse: uaktivert eller ukonfigurert modul oppretter ingen planbeløp, reservasjon eller prognose; preferanser deles i husholdningen; deaktivering med eksisterende data sletter eller endrer ikke faktiske posteringer. [ASSUMPTION A9: Deaktivering stopper fremtidige nye planer først fra valgt virkningsdato; eksisterende forpliktelser og avsluttet historikk må fortsatt kunne sees og gjøres opp. Bekreft konkret avviklingsflyt før implementering.]

**FR-16 – Gjeld og nedbetalingsplan.** Familien kan registrere gjeldspost med navn, saldo på en dato, årlig rente, minimum per måned og ekstra månedsbeløp. Familien kan velge Avalanche (høyeste rente først) eller Snowball (laveste saldo først). Akseptanse: faktiske betalinger knyttes til riktig gjeldspost og teller én gang; oversikt skiller oppgitt saldo, estimert nåsaldo og simulert plan; planen viser estimert gjeldsfri måned, total rente og rente spart mot minimumsbetalinger. Uten gjeld vises tomtilstand; utilstrekkelig betaling gir tydelig varsel fremfor en oppdiktet sluttdato. [ASSUMPTION A10: Månedlig simulering bruker årlig rente/12, minimum på hver gjeld og resten til prioritert gjeld; frigjorte minimumsbetalinger går videre i planen. Horisont 360 måneder; lengre plan merkes utenfor horisont. Rentetiming, avrunding, lik prioritet og saldoavstemming må bekreftes i beregningsdesign. Dette er anslag, ikke långivers saldo eller økonomiske råd.]

**FR-17 – Årlige og uregelmessige utgifter.** Familien kan registrere årlig beløp, forfallsmåned og dokumentert åpningsavsetning for et avsetningsfond. Akseptanse: månedsplan vises, fondets beholdning og faktiske betalinger vises separat, og betaling finansiert fra fondet trekker ikke disponibelt budsjett på nytt. Betaling utover fondet synliggjør finansieringsgapet; samme betaling kan ikke samtidig behandles som full vanlig utgift og fullt fondstrekk. [ASSUMPTION A11: Årsbeløp/12 er foreslått månedsplan, med eksplisitt avstemming av øre og aktiveringsmåned. Planlagt reservasjon er ikke automatisk en faktisk innbetaling til fondet. Historisk åpningsavsetning må ikke bli ny mottatt inntekt. Endelig bokføringsmodell skal følge felles beregningskontrakt i arkitekturen og bekreftes før implementering.]

**FR-18 – Utenlandsoverføringer.** Familien kan registrere mottaker, land/notat, opprinnelig beløp og valuta, dato og kurs til NOK. Akseptanse: opprinnelig beløp og brukt kurs bevares per registrering; senere endret standardkurs endrer ikke tidligere NOK-beløp; ukjent valuta eller manglende/ugyldig kurs flagges og kan ikke stille bli null eller inngå som validert beløp. Modul viser måned, hittil i år, andel av mottatt inntekt og gjennomsnitt med tydelig periode. Samme overføring teller én gang som utgift. Faktiske pengeoverføringer utføres ikke av appen. [ASSUMPTION A12: Kurs uttrykkes NOK per én enhet opprinnelig valuta; NOK bruker 1. Standardkurser er manuelt vedlikeholdte forslag som må bekreftes ved registrering; arbeidsbokens plassholderkurser gjenbrukes ikke. Gebyr må registreres separat eller inngå eksplisitt i faktisk NOK-kostnad, ikke telles begge steder.]

**FR-19 – Utvidede sparemål og uttak.** Sparemål kan ha åpningssaldo med effektiv dato og valgfri måldato. Oversikt viser faktisk oppspart beløp, gjenstående, nødvendig månedsbeløp og forventet ferdigdato ved valgt plan. Familien kan registrere uttak knyttet til målet. Akseptanse: åpningssaldo gir fremdrift uten ny månedsinntekt; innskudd/uttak påvirker fremdrift én gang; ingen måldato gir ingen oppdiktet nødvendig månedssparing; null spareplan eller utløpt måldato gir forståelig status. [ASSUMPTION A13: Uttak er en overføring fra tidligere avsatte penger og er ikke inntekt; eventuell virkning på denne månedens disponible beløp må forklares gjennom den felles posteringen. Uttak finansierer ikke samtidig både en vanlig utgift og en ekstra utbetaling. Øreavrunding, månedsantall og håndtering av mål nådd/overskredet avklares i beregningsdesign.]

**FR-20 – Refusjoner og validering.** Utgiftsrefusjoner kan registreres som egen type koblet til opprinnelig registrering, med effektiv dato og kategori. Akseptanse: refusjon reduserer netto forbruk én gang uten å fremstå som lønnsinntekt; manglende dato, kategori, påkrevd kobling eller valutakurs flagges ved feltet og i oversikten; ugyldige registreringer inngår ikke som bekreftede summer. [ASSUMPTION A14: Brukeren oppgir positivt beløp og eksplisitt refusjonstype; negative beløp i Excel kopieres ikke mekanisk inn. Refusjon i en annen måned føres på faktisk mottaksdato; eventuell maksimal tilbakeføring og utenlandsk kursdifferanse avklares før implementering.]

**FR-21 – Årsvisning.** Familien kan se månedlige faktiske summer, kategoriens årsbudsjett, avvik, årssummer og historisk akkumulert rest. Akseptanse: månedens historiske grenser summeres, ikke dagens grense ganger tolv; ufullstendig år merkes med periode; fremtidig budsjett skilles fra faktiske tall; akkumulert rest er historisk informasjon og øker aldri neste måneds tilgjengelige beløp. Valgfrie moduler vises bare når relevante og aktiverte, mens historiske faktiske posteringer bevares.

### Felles regneregel for utvidelsen

Ingen hendelse får redusere tilgjengelig beløp to ganger. Et vanlig beløp føres som utgift; en overføring til sparing eller fond føres som allokering; en senere betaling fra tidligere allokerte penger forbruker fondet uten nytt fullt budsjettstrekk. Hver gjeldspost og hvert sparemål vurderes separat; oversparing på ett mål må ikke dekke manglende sparing på et annet.

Den tidligere formelen I−E−B−S dekker kjernen uten uttak, men er ikke alene fullstendig for den utvidede versjonen. Arkitekturen må gi en samlet kontrakt for allokeringer, fond, gjeldsplan, faktiske betalinger, refusjoner, uttak og finansieringsgap. Før denne kontrakten er avstemt og menneskelig godkjent er beregningsdesign en implementeringsblokker. NFR-1 og NFR-2 gjelder også alle de nye datatypene; rollekrav FR-3 gjelder registreringene og administratorstyring av moduloppsett.

### Nye åpne beslutninger

- **OQ-8:** Robel bekrefter A9–A14 og samlet beregningsdesign før implementering. Arkitekturansvarlig foreslår konkrete regler og testeksempler for dobbelttrekk, underfinansierte fond, refusjon på tvers av måneder og spareuttak.
- **OQ-9:** Bekreft hvilke moduler som er av/på ved første opprettelse, og hvordan en familie avslutter bruk av en modul med aktive poster. Ingen aktivert modul skal kreve innlegging av privat økonomi bare for å bruke kjernen.

Forutsetningsindeks utvides med **A9** modulavvikling, **A10** gjeldssimulering, **A11** årsavsetning, **A12** valutakurs og gebyr, **A13** spareuttak/prognose og **A14** refusjoner. OQ-7 er nå en validering av dekning og prioritering innen godkjent utvidelse; den er ikke lenger et spørsmål om funksjonene får være med. Full Excel-erstatning kan fortsatt ikke hevdes uten gjennomgang av arbeidsflyt og dataflytting. Ingen import er utført eller autorisert.


### Foreslått samlet beregningskontrakt for utvidet omfang

Dette presiserer og erstatter den midlertidige avgrensningen av kjerneformelen ovenfor. Hele kontrakten er fortsatt et forslag som må godkjennes i OQ-8.

`Tilgjengelig = I + W_net − E − B − S_net − G − F`.

- **I:** mottatt inntekt i måneden. **W_net:** summen av maks(−N(g), 0) per sparemål, der N(g)=månedens brutto innskudd minus månedens brutto uttak. Netto frigjorte øremerkede penger vises separat fra opptjent inntekt. Hvert uttak valideres mot målbeholdningen på effektiv dato og alle senere hendelser; et uttak i september kan ikke finansieres av et innskudd i oktober.
- **E:** ordinære utgifter, inkludert utenlandsoverføringer i NOK og netto refusjoner. Betalinger klassifisert som gjeld, fond eller sparing er ikke også ordinær utgift.
- **B:** ordinære ubetalte regningsforekomster med forfall til og med månedsslutt, inkludert tidligere forfalte. Gjelds- og fondsforekomster utelates fra denne summen.
- **S_net:** sum per sparemål av maks(P(g), maks(N(g), 0)), der P(g) er månedsplan og N(g) er brutto innskudd minus brutto uttak. Fremdrift er åpningssaldo + brutto innskudd − brutto uttak. Brutto uttak legges aldri direkte oppå en reservasjon basert på brutto innskudd: med plan 1 000, uttak 100 og nytt innskudd 100 er N=0, S_net=1 000 og W_net=0; tilgjengelig beløp er tilbake på utgangspunktet. Denne nettoformelen erstatter tidligere bruttoformuleringer når uttak finnes.
- **G:** sum per gjeldspost av maks(frosset månedsplan, faktisk betalt i måneden + ubetalte gjeldsforekomster med forfall til og med månedsslutt). Ekstrabetalingens plan fordeles i entydige kvoter per gjeldspost etter valgt strategi og fryses for måneden. Betaling skal erstatte en ubetalt forekomst, ikke telle begge.
- **F:** månedens årsavsetning + eksplisitt nødvendig påfyll ved manglende fondsdekning. Fondsbeholdning = åpningsavsetning + allokeringer − fondsbetalinger. Påfyllsforpliktelsen føres én gang, og senere betaling eller ny sending må ikke opprette et nytt trekk.

Hver faktisk postering har nøyaktig én regnskapsklasse. En regningsforekomst har uforanderlig type ordinær/gjeld/årsfond; betalingshandlingen velger nøyaktig én postering ut fra denne typen. En regningskobling peker til samme postering. Kategoriens ordinære forbruk utelater gjeldsbetalinger, fondsbetalinger og sparing. Det reserverte beløpet byttes mot faktisk påvirkning ved oppgjør; det opprettes aldri to utgiftseffekter for samme betaling. Avsatte fond og sparemål kan videreføres over måneder; fritt overskudd videreføres fortsatt ikke. Årsfondets planlagte avsetning er en budsjettallokering, ikke en bankbekreftet innbetaling; UI må skille disse begrepene. Underfinansiering må vises før oppgjør og redusere tilgjengelig beløp gjennom det ene påfyllet.

Syntetiske kontrollscenarioer, uten data fra arbeidsboken:

1. **Kjernescenario, tilleggsmoduler av:** I=62 000, E=28 450, B=8 650, S=6 500, W_net=G=F=0 gir tilgjengelig 18 400 NOK.
2. **Utvidet scenario:** Samme syntetiske grunnlag, med utenlandsoverføring 1 500 inkludert som ekstra ordinær utgift, gjeldsreservasjon G=3 500 og årsavsetning F=2 000 gir tilgjengelig 11 400 NOK. Dette er et annet scenario, ikke en endring av forventet resultat i kjernescenarioet.

Akseptanse for FR-9 og FR-16–FR-20 skal inkludere gjenforsøk, samtidige oppgjør, gamle forfalte forekomster, tilbakeføring og månedsskifte. Ingen av disse scenarioene er kjørt applikasjonstest eller empirisk brukerbevis.

## FR-22 — Eget familiebudsjett fra den faktiske arbeidsboken

Robel har eksplisitt bedt om å lagre og bruke den faktiske arbeidsboken slik at dataene finnes i hans nåværende familieprofil når første versjon er ferdig. Dette er et eget releasekrav, ikke bare en inspirasjonsreferanse. Tidligere omtale av «ingen import autorisert» er historisk og erstattes av dette kravet.

- Originalfilen beholdes som en byteidentisk, privat prosjektkopi, med SHA-256 og kildereferanser. Den endres ikke under lesing eller import.
- Alle faktisk utfylte kilderader for kategorier, transaksjoner, gjeld, sparemål, årsutgifter, mottakere og innstillinger bevares. Formler, eksempel-/rapportceller og tomme malrader skilles fra faktiske innregistreringer. Ingen fiktive eksempeldata legges i Robels profil som erstatning for kildedata.
- Importen bindes til én eksplisitt angitt, e-postverifisert administrator og serverutledet familie. Ingen konto eller inntektsmottaker utledes fra personnavn i arket. Ingen annen familie får tilgang eller disse dataene som standard.
- Opprinnelige datoer og perioder bevares. En manglende dato skal ikke erstattes med dagens dato; en ufullstendig rad beholdes som en synlig importpost som trenger avklaring. Usikker klassifisering mellom utgift og gjeld må ikke føre til dobbel belastning.
- Månedlige kildebudsjetter og startsaldoer uten historisk gyldighetsdato beholdes med eksplisitt avklaringsstatus; ingen oppdiktet historikk opprettes. Arbeidsbokens plassholderkurser blir ikke godkjente kurser ved import.
- En gjenkjørt import av samme kilde gir ingen ekstra kopier. Endret kilde må vise forskjeller, og ikke overskrive brukerens senere korrigeringer i stillhet. Kildeark/-rad og importidentitet bevares på hver post.
- Før v1 er ferdig må en virkelig innlogget eier kunne se kildens data, inkludert avklaringsposter, i riktig familieprofil; innholdet består etter utlogging, ny innlogging og server-/databaseomstart. Radantall, koblinger og faktiske finansielle summer avstemmes etter besluttede importregler. En annen innlogget familie avvises fra alle importressurser.

**Status:** Privat kildekopi og importstaging kan forberedes nå. Ingen profilimport er utført: app, innlogging og database finnes ennå ikke. Eieradresse, importavklaringer og runtime-bevis gjenstår. Tilknyttede akseptansebevis må skille mellom data bevart, data avklart og data faktisk lastet og kontrollert i appen.


### Historisk kontantresultat og datovalg

Historisk kontantresultat er et annet mål enn månedens tilgjengelige beløp. Foreslått kontrakt fra arkitekturens AD-10 er `kontantresultat = mottatt inntekt + faktiske brutto spareuttak − netto ordinære utgifter − netto betalt gjeld − netto fondsbetalinger − brutto spareinnskudd`. Planer og ubetalte reservasjoner er utelatt. Alle ledd følger effektiv dato; dagens betalingsstatus erstatter ikke historisk hendelsesforløp. Netto betyr betalinger minus tilknyttede refusjoner/tilbakeføringer innen valgt periode. Ingen sum føres både som ordinær utgift og gjeld/fond/sparing.

Syntetisk kontroll: 62 000 + 1 000 − 29 950 − 3 500 − 9 600 − 4 500 = 15 450 NOK. Dette målet skal merkes kontantresultat og kan ikke brukes som tilgjengelig beløp eller videreføres som neste måneds frie midler. Månedsbildets reserver rekonstrueres etter effektive hendelser eller bevares i tilsvarende historisk bilde; senere betaling av gammel regning fjerner ikke tidligere måneds reservasjon bakover i tid. Korrigering med historisk effektiv dato må avstemmes mot hele det senere hendelsesforløpet, inkludert målbeholdning. Alle presiseringene er fortsatt foreslått beregningsdesign under OQ-8, ikke menneskelig akseptert.
