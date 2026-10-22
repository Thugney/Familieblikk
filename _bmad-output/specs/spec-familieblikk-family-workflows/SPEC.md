---
id: SPEC-familieblikk-family-workflows
companions:
  - bill-corrections.md
  - acceptance-tests.md
  - phased-scope.md
  - source-discovery.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md
  - ../../planning-artifacts/architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md
  - ../../../context.md
  - ../../../rules.md
sources:
  - ../../../work/family-workflows-handoff.json
---
# Familieblikk – trygge familiearbeidsflyter

Kandidat 2026-10-22. Eksakt menneskelig designaksept: **avventer**. Plan og fiktiv forhåndsvisning er ikke implementasjonsgodkjenning. Nyere eksplisitte kontekstendringer og gjeldende tilgangspolicy overstyrer eldre antakelser i adopterte dokumenter.

## Why
Familien trenger å rette feilregistrerte regninger uten å miste historikk eller telle pengene dobbelt. Brukeren har bekreftet at eksisterende moduler nå er synlige etter lagrede familievalg; innstillingene bevares, og videre oppdagelsesforbedring er kandidat. lokal dokumentregistrering og delte handlelister følger i separate trinn.

## Capabilities
- **CAP-1**
  - **intent:** Familien kan rette eller avbryte én regning, gjenopprette den og stoppe fremtidig serie med uttrykkelig virkningsdato.
  - **success:** AT-01–04 viser at valgt forekomst endres, mens historikk og andre reelle forpliktelser bevares.
- **CAP-2**
  - **intent:** Familien kan rette feil betalingsregistrering og registrere faktisk refusjon som forskjellige handlinger.
  - **success:** AT-05–07 viser én aktiv betaling, korrekt reserve og uendret original ved faktisk refusjon.
- **CAP-3**
  - **intent:** Familien kan følge endringer og gjenopprette nye slettinger uten å overskrive nyere handlinger.
  - **success:** AT-08–11 viser varig aktør/tid/før/etter, aktuelle rettigheter, konflikt og idempotent gjentakelse.
- **CAP-4**
  - **intent:** Familien kan eksportere tillatte poster og finne eksisterende moduler; administrator kan aktivere familiens visning.
  - **success:** AT-12–13 viser filtrert CSV uten skjulte data og at familievalg ikke gir nye medlemsrettigheter eller endrer økonomi.
- **CAP-5**
  - **intent:** Familien kan senere registrere fakturaer og kvitteringer fra lokale dokumentforslag.
  - **success:** P2-kriteriene i phased-scope.md viser bekreftelse før bokføring og kobling uten dobbeltføring gjennom dokumentkjeden.
- **CAP-6**
  - **intent:** Familien kan senere samarbeide om handlelister og bekrefte en handletur som faktisk utgift.
  - **success:** P3-kriteriene viser at kjøptmarkering ikke bokfører, og gjentatt fullføring gir samme ene utgift.

## Constraints
- Trinnrekkefølge: retting/historikk/oppdagelse/CSV, deretter dokumenter, deretter handlelister. Senere trinn er bevart omfang, ikke byggemandat nå.
- NOK i øre, Europe/Oslo-datoer og eksisterende autoritative beregningsmotor; ingen dobbelt reserve/utgift eller automatisk overføring av gammelt overskudd.
- Familieisolasjon, ferske modulrettigheter og oppretter/admin gjelder også historikk, eksport, relasjoner, retry og gjenoppretting. Bevar forhåndsregistrerte kontoer uten nytt e-postkodekrav.
- Lokal behandling på Synology og eksplisitt bekreftet utgift per handletur er avklart. OCR-motor er ikke valgt.
- Bevar norsk UI, Figtree, farger, fireflislogo, loader, kalender og fungerende push. Bare fiktive data i ny kandidat; eksisterende aksepterte skjermbilder/baselines endres ikke.
- Bevar .env, POSTGRES_DB, Compose-prosjektnavn/datavolum, PRIVATE_IMPORT_PATH, privat kilde og nøkler. Ingen down -v, prune, drop/flush/truncate, restore/import/seed eller eierklargjøring ved vanlig oppdatering.
- Ingen avhengighetsinstallasjon, commit, push eller NAS-utrulling er autorisert for dette omfanget. Releasetest krever Compose-kontrakt og lesende avstemming av reelle kildeposter.

## Non-goals
- Bankbetaling/banktilkobling, ekstern OCR, automatisk bokføring, redesign og gjenoppbygging av gamle slettede poster uten bevart grunnlag.
- Kvitteringslinjer/kategorisplitting og nye varslingskanaler er utenfor dette planleggingsomfanget.

## Success signal
Etter senere godkjent implementasjon kan en autorisert bruker rette en fiktiv feilbetalt regning, se hele historikken, gjenopprette en ny sletting og eksportere samme tillatte utvalg. Én aktiv økonomisk virkning består ved retry, samtidighet og omstart, mens de private originaldataene er lesende avstemt uendret.

## Assumptions
- Datamodell og handlinger i bill-corrections.md er implementasjonskandidater, ikke vedtatte detaljer. Stoppdato foreslås inklusive. Én hovedkategori per tur og separate turer for forskjellige butikker er foreslått første avgrensning, ikke endelig produktaksept.

## Open Questions
- Godkjenner Robel den eksakte trinn-1-kandidaten etter uavhengig gjennomgang?
- Aksepteres én hovedkategori per tur og separate turer per butikk i første versjon, ved detaljering av trinn 3?
- Hvilken lokal OCR-motor, fast versjon og ressursramme passer faktisk NAS? Dokumentgrenser/oppbevaring og detaljert design for trinn 2/3 må avgjøres før bygging.
