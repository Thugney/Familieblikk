---
id: SPEC-familieblikk-calendar
status: implemented-local-verified
companions:
  - recurrence-rules.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md
  - ../../planning-artifacts/architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md
sources:
  - ../../../work/calendar-request.json
---

# Familieblikk – felles familiekalender

## Why

Robel ønsker familieavtaler som del av eksisterende Familieblikk, med samme kontoer og familie. Hvert medlem har egen kalender i tillegg til felles familiekalender; alle i husholdningen kan se hverandres kalendere og familiens samlede oversikt. En avtale kan tilordnes flere familiemedlemmer uten å bli kopiert. Funksjonsomfang og kalenderkandidat ble akseptert med «Ja, bygg kalenderen inn nå». Kalenderen er nå implementert og verifisert lokalt; implementasjonsstatus og avgrensninger står i recurrence-rules.md. Den nye forbruks-/planleggingskandidaten avventer separat vurdering.

## Capabilities

- **CAP-1**
  - **intent:** Familiemedlemmer kan se familiens avtaler i eksisterende app.
  - **success:** Samme innloggede økt åpner familiens kalender med dato og tittel; et annet hushold får verken avtaler eller detaljer, også ved kjent post-ID.
- **CAP-2**
  - **intent:** Medlemmer kan opprette avtaler med tittel, start/slutt eller heldag og valgfritt sted/notat.
  - **success:** Skjemaet skiller synlig mellom «Felles familieavtale» og «Valgte familiemedlemmer», med ett eller flere medlemmer i sistnevnte valg. Gyldig lagring gjør én avtale synlig for familien; tom tittel og slutt før start avvises med feltfeil uten dataendring, og gjentatt innsending oppretter ikke dublett.
- **CAP-3**
  - **intent:** Oppretteren og familiens administrator kan endre og slette avtaler; andre medlemmer kan lese.
  - **success:** Å være valgt deltaker gir ikke redigeringsrett. Serveren håndhever dette ved hver handling, avbryt endrer ingenting, og en gammel redigering overskriver ikke en nyere uten varsel.
- **CAP-4**
  - **intent:** Familien kan bruke ukentlig og månedlig gjentakelse.
  - **success:** Forekomster vises én gang med konsistente datoer; endrings-/sletteomfang og kortmånedsregel er forståelig før bekreftelse og følger samme regel etter ny innlasting. Aksepterte regler, kanttilfeller og implementasjonsavgrensninger står i recurrence-rules.md.
- **CAP-5**
  - **intent:** Familien kan bruke kalenderen på mobil og desktop med tydelige tilstander.
  - **success:** Tastatur og berøring åpner oversikt, detalj og skjema; lasting, ingen avtaler, feil, frakobling og manglende rettighet har tekst og vei videre. Lagrefeil beholder inndata uten falsk bekreftelse; frakoblet lagring avvises, og utlogging fjerner privat kalenderinnhold.

- **CAP-6**
  - **intent:** Familien kan se felles og personlige kalendere og tilordne samme avtale til valgte familiemedlemmer.
  - **success:** «Alle» samler familiens avtaler uten dupliserte forekomster, «Felles» viser fellesavtaler, og personvalg viser avtalene tilordnet valgt medlem. To valgte deltakere ser samme kanoniske avtale i hver sin kalender og én gang i samlet visning; endring/sletting oppdaterer samme forekomst med uendret oppretter-/adminrett. Fremmed families deltaker avvises av serveren uten delvis lagring.

- **CAP-7**
  - **intent:** Et medlem kan svare om en avtale passer og endre sitt eget svar; familien kan se svarene.
  - **success:** Valgte deltakere kan svare på personavtaler, og alle nåværende medlemmer kan svare på fellesavtaler. Status er «Ikke svart», «Passer» eller «Passer ikke», med ett svar per medlem/forekomst. Bare medlemmet selv kan sette, endre eller fjerne eget svar; oppretter/administrator kan ikke svare for andre. Serveren avviser svar fra feil familie eller en ikke-berettiget deltaker uten dataendring. Svaret gir ingen rett til å redigere avtalen.

## Constraints

- Norsk bokmål og Europe/Oslo; heldag er kalenderdatoer, ikke klokkeslett som forskyves ved tidssonebytte. Avtaler bruker eksisterende husholdningsavgrensning, innlogging og passordkontoer; ingen ny e-postkode kreves for forhåndsregistrerte kontoer.
- Familietilhørighet og oppretter bestemmes av serveren. Alle valgte deltakere må tilhøre samme husholdning; hver avtale og gjentatt forekomst har én kanonisk identitet på tvers av kalendervisninger. Personlig kalender betyr tilordning, ikke privat innhold i husholdningen. Rett til å registrere andre familier gir ikke kalenderinnsyn i dem. Gjeldende økt-, CSRF- og lese-/skrivekontroll gjelder; avvisning endrer ingen data.
- Eksisterende Django/PostgreSQL, prosjektets .venv og Synology Docker beholdes. Ingen nye avhengigheter, credentials, commit, push eller ekstern integrasjon følger av denne spesifikasjonen.
- Bruk akseptert fireflislogo, rolig sammenhengende arbeidsflate og eksisterende tilgjengelighets-/responsivitetskontrakt. Desktopprofil forblir nederst til venstre. Kalenderdato er en egen navigasjonstilstand; kalenderen skal ikke endre budsjettmåned eller budsjettberegninger utilsiktet.
- Bevar eksisterende faktiske familie-, budsjett- og importdata og atferd. Akseptert budsjettprototype og skjermbildebaselinjer endres ikke. Kalenderpreview bruker bare fiktive avtaler og merkes designforhåndsvisning.
- Ved motstrid i historiske companion-avsnitt gjelder nyere godkjent kontoendring i context.md/rules.md: forhåndsregistrerte passordkontoer er autorisert, og eldre krav om e-postverifisering gjeninnføres ikke gjennom kalenderen.

## Non-goals

- Google-/Outlook-synk, eksterne varsler/påminnelser, vedlegg, regningsforfall i kalender og endringer i bank-/budsjettlogikk.
- Separat app/chat, påkrevd dra-og-slipp, skjulte/private kalendere innen husholdningen og eksterne deltakerinvitasjoner inngår ikke i denne avgrensede funksjonen.

## Success signal

Verifikasjonsmålet er en demonstrasjon med to fiktive familier og administrator/to medlemmer viser opprettelse, heldag/tidsavtale, tillatt og avvist redigering, ukentlig/månedlig gjentakelse, én delt avtale hos to valgte medlemmer, person-/fellesfiltrering uten dubletter, egne synlige deltakelsessvar med avvist forsøk på å svare for andre og varig gjeninnlasting uten lekkasje eller endring av budsjett-/importsummer. Menneskelig kalenderaksept er registrert i .project-init/calendar-human-acceptance.json; faktisk lokal runtime er dokumentert i work/calendar-runtime-verification.json og work/calendar-docker-browser.json. Dette erstatter ikke manglende historiske Project Init-dekningsgater og er ikke en NAS-utrulling.

## Historiske forutsetninger – akseptert for kalenderkandidaten

- **A1 – Visningsforslag:** Månedsrutenett desktop, agenda mobil og måned/liste-valg; kalenderinngang i eksisterende navigasjon. Plassering og detaljutforming er forslag til preview.
- **A2 – Gjentakelsesforslag:** Én forekomst eller valgt og fremtidige; kort måned flyttes til siste dag uten å miste opprinnelig dag; valgfri sluttdato, ellers ingen sluttdato. Detaljer i recurrence-rules.md.
- **A3 – Tidsforslag:** Gjentatt tidsavtale beholder lokalt klokkeslett over sommertid; ugyldig/uklar tid krever eksplisitt avklaring. Detaljer i recurrence-rules.md.

- **A4 – Filterforslag:** «Alle» er unionen av felles- og personavtaler; «Felles» avgrenser til fellesomfang, mens personvalg avgrenser til eksplisitt tilordnede avtaler. Fellesavtaler kopieres ikke automatisk til personkalendere. Eventuelt valg av flere personer bruker union uten dubletter. Oppretteren legges ikke automatisk til som deltaker. Dette er visningspresiseringer til vurdering, ikke nye bekreftede brukerbeslutninger.

- **A5 – Svarforslag:** Gjentakelsessvar gjelder én forekomst og medlem. Endring av dato/tid/heldag eller deltakere/omfang nullstiller svar på de berørte forekomstene til «Ikke svart» innen bekreftet én/fremtidige-omfang; fortid bevares. UI viser nullstillingen før bekreftelse. Notat-, sted- og tittelendring alene beholder svar. Detaljer i recurrence-rules.md.

## Status for tidligere åpne spørsmål

- **OQ-1 lukket for kalenderen:** A1–A5 inngikk i den historisk aksepterte kandidaten; mottakets eksakte hashverdier beholdes uendret. Avsnittenes opprinnelige forslagsordlyd bevares som bakgrunn, ikke som en ny ventende kalendergate. Implementasjonens datogrenser og serieretting er dokumentert i companion.




