---
id: SPEC-familieblikk-spending-planning
status: draft-design-pending
companions:
  - calculation-rules.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md
sources:
  - ../../../work/spending-planning-request.json
---

# Forstå forbruket og planlegg neste måned

## Why

Robel opplever at regnearkpreget årsvisning, seks kategorier om gangen, tekniske prosenter og manuell søking skjuler hvor pengene går. Familien skal kunne forstå hele forbruket med valgfrie filtre og bruke inntekt, utgifter og sparing til å lage neste måneds plan sammen. Intensjonen er bekreftet gjennom direkte tilbakemelding; konkret visning og beregningsforslag nedenfor venter på menneskelig designvurdering.

## Capabilities

- **CAP-1**
  - **intent:** Familien kan forstå hele forbruket uten skjulte kategorier.
  - **success:** Alle relevante bekreftede kategorier kan finnes fra samme forbruksvisning, også små beløp; totalsummen stemmer med grunnlaget og ingen kategori forsvinner i et stille topp-N-utvalg.
- **CAP-2**
  - **intent:** Familien kan avgrense forbruk etter kategori, periode og søketekst uten manuell søkeknapp.
  - **success:** Endret valg eller tekst oppdaterer graf, beløp og treff samstemt; siste filtervalg gjelder også ved svar i feil rekkefølge, og nullstill, lasting, feil og ingen treff er forståelige.
- **CAP-3**
  - **intent:** Familien kan forstå året grafisk i stedet for å lese en stor nullfylt matrise.
  - **success:** Månedsutvikling og kategorifordeling viser samme valgte grunnlag; inntekt blandes ikke inn som forbruk, og manglende datagrunnlag skilles fra målt null. Grafens innhold er også tilgjengelig i tekst.
- **CAP-4**
  - **intent:** Familien kan undersøke hva som forklarer en kategori.
  - **success:** Valgt kategori åpner periodens utvikling og tilhørende bekreftede poster; tilbake beholder filtre, og andre familiers poster kan ikke leses ved direkte ID.
- **CAP-5**
  - **intent:** Familien kan lage et redigerbart utkast til neste måned fra inntekt, kjente forpliktelser, sparing og øvrig forbruk.
  - **success:** Hvert beløp viser grunnlag og planstatus; manglende beløp må fylles ut og presenteres ikke som faktisk null. Planlagt rest vises separat fra mottatt inntekt og dagens tilgjengelige beløp; endring av utkast endrer ingen bokførte data.
- **CAP-6**
  - **intent:** Familien kan velge historikk som utgangspunkt for variable kategoribeløp.
  - **success:** Valgte avsluttede måneder, antall observasjoner og eventuell ufullstendighet vises; uavklarte importutkast er utelatt, og hvert forslag er redigerbart uten automatisk vedtatt budsjett.
- **CAP-7**
  - **intent:** Administrator kan bekrefte familiens ferdige månedsplan eksplisitt.
  - **success:** Før eventuell lagring vises valgt målmåned, endringer og rest; eksisterende plan overskrives ikke uten endringsoversikt og versjonskontroll. Avbryt, manglende adminrett eller konflikt endrer ingen data; historiske grenser og faktiske kildeposter beholdes.

## Constraints

- Integrert i samme Familieblikk, NOK, Europe/Oslo og eksisterende konto-/familierettigheter, også forhåndsregistrerte passordkontoer. Alle medlemmer kan lese og drøfte; eventuell lagring av felles plan er administratorhandling.
- Planutkast er forventning, aldri mottatt inntekt, bankbalanse, økonomisk garanti eller nytt fritt overskudd fra tidligere måned. Bill-/kategori-/spare-/gjelds-/fondskoblinger må ikke telles dobbelt; presiseringer i calculation-rules.md.
- Ingen AI, ny tilbyder, avhengighet, kredentialtilgang eller ekstern rådgivning. Kandidaten bruker fiktive data; private arbeidsbokverdier og legitimasjon leses ikke av dette arbeidet.
- Eksisterende merkevare, fireflislogo, tema og tilgjengelighet videreføres. Dette featureforslaget erstatter dense matrise/toppseks som standard for disse flatene; øvrig akseptert budsjettatferd og den fortsatt ventende kalenderkandidaten beholdes.
- Kun spesifikasjon/designkandidat er produsert. Implementering, faktisk lagring, tester, gjennomgang og eksakt menneskelig aksept er ikke utført eller godkjent gjennom dokumentet. Ingen commit/push eller appkodeendring.

## Non-goals

- Automatisk bokføring, automatisk gjettet budsjett, autosave, endring av rå importdata eller innlemming av uavklarte utkast i bekreftede tall.
- Regnearkmatrise som primær årsflate, skjulte utgiftskategorier, investeringsråd, bankintegrasjon eller endring av kalenderomfanget.

## Success signal

I en fiktiv kandidat kan familien finne en kategori utenfor de seks største, filtrere en periode uten søkeknapp, forklare årets forbruksutvikling og justere neste måneds utkast med synlig planlagt rest. Senere verifikasjon må avstemme grafer mot bekreftede poster og bekrefte at utkast/avbryt ikke endrer historikk, og at kun eksplisitt administratorbekreftelse kan lagre riktig målmåned uten versjonstap.

## Assumptions

- **A1:** Forbruk viser NOK-beløp først; prosenter er valgfri detalj, ikke hovedforklaring. Uten grense vises faktisk forbruk uten fremdriftsstolpe eller teknisk «ingen plan»-status. Hele kategorilisten er tilgjengelig; eventuell intern rulling/legende er et visningsforslag.
- **A2:** Periodevalg foreslås som måned, tre kalendermåneder, år og egendefinert datospenn; kategoridetalj viser månedstrend og relaterte poster. Nøyaktig standardperiode og plassering bekreftes i kandidaten.
- **A3:** Deterministisk, redigerbart utkast fra forventet inntekt, bekreftede gjentakende forpliktelser, fast sparing og øvrige planbeløp; ukjent grunnlag blokkerer en fullstendig rest fremfor å bli null. Ingen automatisk lagring.
- **A4:** Variabelt kategoriforslag er aritmetisk gjennomsnitt av bekreftet nettoforbruk i eksplisitt valgte avsluttede måneder; manglende/sparsom historikk merkes. calculation-rules.md beskriver avgrensningen.

## Open Questions

- **OQ-1:** Robel vurderer A1–A4 i eksakt kandidat før implementering: visuell gruppering, perioder/reaktivt søk, forslagets historikkgrunnlag og bekreftelsesflyt. Bekreftet intensjon skal ikke spørres om på nytt.
- **OQ-2:** Avstem mapping til eksisterende månedsplanmodell og eksplisitt forventet inntektsgrunnlag før en implementeringsoppgave: ingen nye felt, API eller persistens er besluttet av denne designkontrakten.
