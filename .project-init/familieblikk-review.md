# Familieblikk — plan og design til gjennomgang

## Hva du kan se nå

Et klikkbart, norsk designforslag med 15 skjermer for mobil og PC. Lys bakgrunn, rolige grønne hovedflater, tydelige beløp og kategorifarger. Alle navn og beløp i forhåndsvisningen er fiktive. Ingenting lagres eller sendes.

[Åpne skjermforslagene](http://127.0.0.1:4173/.project-init/familieblikk-mockup.html)

[Åpne Project Init-gjennomgangen](http://127.0.0.1:4173/.project-init/review.html)

## Familien bestemmer hvor mye den vil bruke

Kjernen er én families inntekter, utgifter, kategoribudsjett, regninger og sparemål. Familien kan ta i bruk gjeld/nedbetaling, årsutgiftsfond og utlandsoversikt etter behov. Visning av sparemål og årsoversikt kan også tilpasses. Å skjule en del sletter ikke historikk eller penger som allerede er bundet.

Den eksisterende Excel-arbeidsboken er både funksjonsreferanse og autorisert datakilde til Robels egen familieprofil. En byteidentisk kopi og alle faktiske rader er bevart privat i prosjektet. FR-22 krever at disse dataene faktisk finnes i riktig verifisert eierprofil før v1 kan være ferdig. Det finnes ennå ingen app/database å laste dem i. Kildens datoer og uavklarte rader beholdes; Excel-formlene er ikke erklært feilfrie eller rekalkulert. Private verdier inngår ikke i denne delbare designprototypen.

## Slik skal hovedbeløpet forstås

Bare mottatt inntekt teller. Vanlige utgifter, ubetalte regninger og planlagt sparing reduserer det disponible beløpet. Gjeld og årsutgifter får egne regnskapsgrupper når de brukes. Samme betaling skal påvirke budsjettet én gang. Netto uttak fra sparing vises separat, og uttak etterfulgt av gjeninnskudd skal ikke skape ekstra penger.

Grunneksemplet gir 18 400 kr igjen. Aktivering av de tre fiktive tilleggseksemplene gir 11 400 kr. Dette er budsjettanslag, ikke banksaldo. Måneden starter på nytt; fritt overskudd vises bare i historikken. Sparemål og øremerkede fond har egen videreført balanse.

## Foreslått teknisk startpunkt

Én Django-applikasjon med PostgreSQL og et responsivt grensesnitt i HTML/CSS/JavaScript. Dette samler tilgang og pengeregler på ett sted og passer den ønskede Docker-baserte driften. Appstakken er et gjennomgått forslag; ingen appavhengigheter, servere, databasekontoer eller e-posttjenester er opprettet. BMAD 6.12.4 er installert som planverktøy.

## Foreslått byggerekkefølge etter designaksept

1. Innlogging, invitasjoner og sikker adskillelse mellom familier.
2. Felles postmodell, dato-/beløpsregler og én beregningsmotor.
3. Kategorier, regninger, sparing og månedsskifte.
4. Valgfrie gjelds-, årsutgifts- og utlandsfunksjoner på samme postmodell.
5. Årsoversikt, PWA, tilgjengelighet og finpuss på mobil/PC.
6. Uavhengige funksjons-, sikkerhets- og gjenopprettingskontroller før publisering.

Dette er leveranserekkefølge, ikke et ferdig godkjent oppgavebrett. BMAD-epics og akseptanseoppgaver utledes etter at beregnings- og designkandidaten er akseptert.

## Kontroller og grenser

- 92 nettleserkontroller av designprototypen bestod på 360, 390, 768, 1024 og 1440 piksler.
- 36 kandidatbilder er tatt; de er ikke menneskelig godkjente referanser ennå.
- 12 regneeksempler bestod, inkludert dobbelttrekk, spareuttak/gjeninnskudd, månedsskifte og historiske kontantstrømmer. Dette er kontroll av foreslåtte regneeksempler, ikke appfunksjonstester.
- Uavhengig gjennomgang fant og fikk rettet utydelige regler for sparing, historikk, betalingstyper, sesjoner og valgfrie visninger.
- Detaljskjemaer og full januar–desember-matrise er spesifisert i UX-dokumentene; enkelte vises bare som flytforklaring i prototypen.
- Reell innlogging, lagring, familieisolasjon og installert PWA er ikke bygget eller testet.
- Project Init krever foreløpig også mørke skjermcaser for full visuell gate. Mørkt tema er ikke bestilt; denne begrensningen er dokumentert uten å utvide omfanget.
- Hosting, e-postleverandør, kontosletting/oppbevaring og gjenopprettingsmål må avklares før ekte familiedata og lansering.
- Git-repoet har ingen commits eller remote. Profesjonell main/develop/feature-struktur og GitHub-oppsett er fortsatt utestående; ingen commit eller push er utført.

## Din gjennomgang

Vurder om oversikten gir riktig følelse og prioriterer de riktige tallene. Se særlig på beregningsforklaringen og de valgfrie delene under Mer → Tilpass appen. PRD, UX og arkitektur er utkast til denne vurderingen. Produktomfangsgodkjenningen er beholdt; endelig visuell aksept, beregningsaksept og implementasjonsautorisasjon er ikke registrert.
