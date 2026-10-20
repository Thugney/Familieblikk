---
name: Familieblikk
description: Rolig, lys familieøkonomi på norsk, mobil og desktop.
status: draft
updated: 2026-10-20
sources:
  - ../../../../context.md
  - ../../../../work/workbook-structure.json
colors:
  canvas: '#F5F7F4'
  surface: '#FFFFFF'
  primary: '#17644B'
  primary-foreground: '#FFFFFF'
  text: '#172B25'
  muted: '#53675D'
  border: '#DFE6DF'
  input-border: '#B8C6BD'
  soft-green: '#E8F2EC'
  category-blue: '#456EB1'
  category-ochre: '#9B6C18'
  category-purple: '#8260A4'
  category-food: '#B27C2C'
  category-children: '#B26074'
  category-leisure: '#508B79'
  category-other: '#6D7781'
  danger: '#AD3F38'
  danger-soft: '#FBEDEE'
  focus: '#456EB1'
typography:
  body:
    fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif'
    fontSize: 15px
    fontWeight: '400'
    lineHeight: '1.5'
  title:
    fontSize: 30px
    fontWeight: '650'
    lineHeight: '1.2'
  section:
    fontSize: 18px
    fontWeight: '650'
    lineHeight: '1.3'
  kpi:
    fontSize: 53px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.025em
  kpi-mobile:
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.15'
  caption:
    fontSize: 14px
    lineHeight: '1.45'
rounded:
  sm: 9px
  md: 10px
  lg: 18px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '6': 24px
  '8': 32px
  touch: 44px
  sidebar: 224px
  content-max: 1240px
components:
  navigation:
    active-background: '{colors.soft-green}'
    active-text: '{colors.primary}'
  metric:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.lg}'
  button:
    height: '{spacing.touch}'
    radius: '{rounded.md}'
  form:
    border: '{colors.input-border}'
    radius: '{rounded.sm}'
  list:
    background: '{colors.surface}'
  progress:
    background: '{colors.soft-green}'
  dialog:
    radius: '{rounded.lg}'
  feedback:
    error: '{colors.danger}'
---

## Brand & Style

Familieblikk skal gi familien ro og et forståelig bilde av måneden. Godkjent retning er en moderne, lys norsk PWA. Alle konkrete visuelle valg her er **forslag til vurdering**, ikke godkjent sluttdesign. Ingen UI-pakke eller fontavhengighet er valgt.

Paret DESIGN.md og EXPERIENCE.md er kontrakten dersom en illustrasjon avviker. [Foreslått interaktiv referanse](../../../../.project-init/familieblikk-mockup.html) viser komposisjon og tilstander; Project Init viser den for menneskelig vurdering. Den er en lokal designprototype, ikke en fungerende økonomitjeneste.

## Colors

Bakgrunnen bruker `{colors.canvas}`, mens innhold ligger på `{colors.surface}`. Mørk tekst `{colors.text}` og sekundærtekst `{colors.muted}` gir tydelig leserekkefølge. `{colors.primary}` fremhever tilgjengelig beløp, dagsramme og primærhandling. Et negativt beløp beholder fortegn og får teksten «Underskudd» og `{colors.danger}` på lys flate.

Kategorier kombinerer navn og farge: Bolig blå, Mat og dagligvarer varm oker, Transport lilla, Barn dempet rosa, Fritid grønn og Annet grå. Dette gjengir faktiske mockdata. Farger er gjenkjenningshjelp, aldri eneste betydningsbærer. `{colors.border}` og `{colors.input-border}` gjengir mockens kanter; nødvendig kontrollavgrensning må forsterkes hvis kontrasttesten ikke består.

Kontrastmål ved implementasjon: minst 4,5:1 for normal tekst og 3:1 for stor tekst, fokus og nødvendige grafiske kontrollmarkører. Ingen godkjent kontrastmåling foreligger ennå; faktiske kombinasjoner må testes ved implementasjon.

## Typography

Systemfont gir rask oppstart uten nedlasting. Tokens gjengir lest mock: hovedbeløp 53 px, 45 px under 1150 px, 44 px ved 601–850 px og 48 px ved høyst 600 px. Dagsramme er 36 px desktop og 27 px på liten mobil. Hovedtekst er 15 px desktop og 14 px mobil. Beløp har tabulære sifre, synlig minus og norsk formatering. Hovedkort avrunder dagsbeløp til hele kroner; beregningen viser 1 533,33 kr. Inndata støtter desimalkomma.

Gjeldende tekstforslag følger oppdatert mock: grunntekst 15 px desktop og 14 px mobil, støttende etiketter minst 12 px, sentrale dataverdier 17 px eller større. Utviklerens forhåndsvisningsverktøylinje er 12 px. Caption-token er en 14 px rolle, ikke et universelt minimum for alle etiketter. Test med 200 % tekst før apputgivelse må bekrefte at etiketter, handlinger og beløp forblir brukbare; dette er ingen påstand om full WCAG-verifikasjon.

## Layout & Spacing

Lest mock bytter til bunnmeny ved høyst 850 px. Desktop har 224 px sidemeny (190 px ved høyst 1150 px), 40 px innholdsmarg (24 px ved høyst 1150 px, 55 px fra 1600 px), og maks 1240 px innholdsflate. Ved høyst 600 px er sidemargen 18 px og innholdet én kolonne; 601–850 px beholder utvalgte to-kolonnegrupper. Bunnmeny og safe area får egen bunnplass. Hovedkort/dagsramme bruker omtrent 1,7:1 desktop; kategorier/regninger og sammenligning/sparing omtrent 1,35:1.

Oversikt begynner med måned og familie, deretter tilgjengelig/dagsramme, støttetall, kategorier, regninger og sparing. Ingen stor dekorativ velkomstflate. Tabeller blir tekstede kort på smal skjerm; beløp høyrejusteres uten å miste etiketten.

## Elevation & Depth

Hvite kort skilles fra lerretet med rolig kant. Kun dialoger får svak skygge. Ingen glød, gradient eller tredimensjonale økonomikort. Hierarkiet kommer fra størrelse, gruppering og grønt hovedbeløp.

## Shapes

Kort og dialog bruker `{rounded.lg}`, knapper `{rounded.md}`, felt `{rounded.sm}`. Statusmerker kan bruke `{rounded.full}`. Ikoner er enkle konturer og ledsages av tekst for navigasjon og vesentlige handlinger; ingen ny ikonpakke forutsettes.

## Components

| Komponent | Visuell kontrakt |
|---|---|
| Navigation | Aktivt valg har grønn tekst, lys grønn flate og tydelig markør. Ikon og norsk etikett beholdes på alle fem mobilvalg. |
| Metric | Hovedkort i grønt med hvitt beløp; dagsramme som underordnet grønn verdi på lys flate. Forventet inntekt på separat hvitt kort, merket «Ikke med i tilgjengelig». Historisk måned erstatter dagsramme med «Avsluttet måned». |
| Button | Minst 44 px trykkflate er foreslått gulv; oppdatert hovedkortlenke er 44 px. Primær grønn/hvit, sekundær hvit med kontrollkant, slett rød tekst med bekreftelse. Fokus i mock: 3 px blå ring med 3 px avstand. |
| Form | Vedvarende etikett over felt, hjelpetekst og feil rett under. Utgift/Inntekt og Forventet/Mottatt er tekstede valg, ikke bare fargede brytere. |
| List | Poster, regninger, mål og medlemmer har navn, sekundærinformasjon, beløp/status og tekstet handling. Forfalt får tekst og rød markør, ikke bare rødt tall. |
| Progress | Kategorinavn, brukt/ramme og rest eller overforbruk i tekst. Mål viser spart/målbeløp. Fyll klippes ved 100 %, men tekst viser hele overforbruket. |
| Dialog | Tydelig tittel, kort forklaring, primærhandling og avbryt. På mobil helskjerms redigering med synlig tilbake og lagre. Ikke flere dialoglag. |
| Feedback | Lastereservasjon følger ferdig layout. Tomtilstand har konkret neste handling. Offline, feil og begrenset tilgang har tekst og relevant vei videre. |

## Do's and Don'ts

### Revidert komposisjon etter Robels visuelle tilbakemelding

Alle sider deler en sammenhengende hvit arbeidsflate, samme innholdsakse og rolige skillelinjer fremfor selvstendige avrundede kort. Farger og økonomiske figurer beholdes. Oversikten samler «Igjen å bruke» og dagsbeløp i ett grønt felt med en felles nøkkeltallstripe under. Seksjoner og lister følger samme linjering på alle navigasjonssider. Mobil stabler innholdet med delte skillelinjer. Overskriften er «Familiens økonomi»; seksjoner bruker beskrivende norsk som «Forbruk per kategori», «Forbruk over tid» og «Sparemål».

Toppfeltets månedsvelger og varsler har felles 44 px høyde. Prototypekontroller ligger i «Designvalg», adskilt fra appens funksjoner. Profilens initialer, navn og rolle er én venstrejustert gruppe med 12 px mellomrom. En felles semantisk bunntekst avslutter arbeidsflaten på alle sider, med Familieblikk, prototypestatus, Personvern og Hjelp og kontakt. Lenkenes dialoger forklarer dagens prototypestatus; de er ikke en ferdig juridisk erklæring eller en aktiv kundestøttetjeneste. Bunnteksten følger innholdet og reserverer plass for mobilnavigasjonen.

Valgfrie familiemoduler gjenbruker eksisterende komponentfamilier: Form for tekstede modulbrytere og prognosevalg, List for gjeld/årsposter/mottakere, Metric for summer og Progress for finansiering. Prognoser merkes «Anslag» med dato. Originalvaluta og NOK får egne etiketter. Årsmatrise kan rulle inne i navngitt tabellregion på desktop; mobil velger én måned med stablede kategorier. Ingen flagg eller farge alene identifiserer land, status eller modulvalg. Alle fem tilleggsskjermene gjeld, arsutgifter, utland, arsoversikt og tilpass finnes nå i mocken med optional-preview.js. Full januar–desember-matrise og komplette detaljskjemaer er fortsatt spine-only. Presentasjonsvalg «Sparemål i oversikten» og «Årsoversikt i Mer» skjuler bare presentasjon og endrer ingen data eller økonomiske virkninger.

| Gjør | Unngå |
|---|---|
| Vis hovedtallet og forklar beregningen | Å fremstille et budsjettanslag som bankbeholdning |
| Bruk kategori, beløp og tekststatus sammen | Å kreve fargesyn for å forstå økonomien |
| Behold negative tall og faktiske overskridelser | Å klippe tall til null eller skjule overforbruk |
| Vis ekte lagringsbekreftelse | Å late som en frakoblet endring er lagret |
| Gjør store trykkflater og lesbar typografi | Små ikonhandlinger som eneste vei til å redigere |

Forslag som krever menneskelig beslutning: konkret palett, kortkomposisjon, 850 px navigasjonsgrense og detaljnivå i hovedkort. Oppdatert mock bruker «Veiledende dagsbeløp», mobile postkort og minst 44 px hovedkortlenke. Koordinators designkontroller rapporterer 92/92 ved bredder 360, 390, 768, 1024 og 1440 med 36 kandidatbilder; dette er prototypeevidens, ikke appfunksjonstesting, full WCAG-revisjon eller menneskelig aksept. Ingen mørk modus er inkludert.


### Human visual acceptance — 2026-10-20

Robel accepted the revised design conditional on one desktop profile location: bottom left in the sidebar. Remove the duplicate personal avatar from the top-right header; retain month selection and notifications. The family identity near the brand is household context, not a duplicate personal profile. Mobile account access remains through Mer / Familie. No dependency installation or deployment approval is implied.
