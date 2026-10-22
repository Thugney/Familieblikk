# Kameraskanning og handlelister

Velg **Skann kvittering** i menyen. Ta et tydelig bilde eller velg et JPEG/PNG-bilde, kontroller forhåndsvisningen og velg Skann bildet. Bildet behandles bare på familiens egen server. PDF-opplasting tilbys ikke. Du kan alltid velge manuell utfylling.

Gjennomgå beløp, dokumentdato og betalingsmottaker; velg kategori. For en ubetalt faktura bekrefter du også forfallsdato. Forslag er usikre og brukes bare når du selv velger dem. Motstridende tall/datoer blir stående tomme. Lagre utkastet og bekreft deretter én utgift, én ubetalt engangsregning eller kobling til en eksisterende post. OCR antar aldri at en faktura er betalt.

Utydelige linjer kan gjøre at beløp eller dato utelates selv om andre felt gjenkjennes. Fyll inn fra kvitteringen eller ta et tydeligere bilde. Lokal gjenkjenning kan fortsatt lese feil; kontroll før bekreftelse er en del av flyten, og det gis ingen garanti for automatisk nøyaktighet på alle bilder.

Tilgang administreres separat for Dokumenter og Handlelister. Listeadgang gir ikke budsjett- eller skanneadgang. En koblet skanning følger også økonomipostens gjeldende tilgang. Skanning, utkast og varestatus oppretter aldri økonomiske poster. Hver bekreftet handletur gir én utgift; en sen skanning kobles til samme utgift uten å endre beløpet.

## Midlertidige bilder

Nye bilder ligger bare i `scan-spool` på `/private-scans` (`PRIVATE_SCAN_ROOT` ved annen hosting). Lageret er separat fra eldre originaler og inngår ikke i backup. Filnavn, full gjenkjent tekst, EXIF og miniatyrbilder lagres ikke i databasen. Et bildeavtrykk brukes kun til å avvise gjenbruk av samme forespørselsnøkkel med annet innhold, aldri for duplikatsøk. Duplikatsøk bruker gjennomgåtte felt og tillatte eksisterende poster.

Mottak er begrenset til 10 MiB per forespørsel i minnet; multipartbilder skrives ikke i generelle midlertidige mapper. Dekodet bilde er begrenset til 25 megapiksler. Decoder- og OCR-arbeidsfiler ligger i avgrensede private undermapper i skannelageret og ryddes ved normal avslutning. Nettleserens forhåndsvisning finnes bare i sidens minne og frigjøres når bildet byttes/forkastes eller siden forlates.

Arbeideren lagrer strukturerte forslag og ryddebehov i én transaksjon før den sletter bildet. Ryddebehov beholdes til sletting er bekreftet og gjenopptas etter avbrudd uten å kjøre OCR på nytt. Mislykket OCR sletter også bildet; gjennomgåtte manuelle felt beholdes. Avbryt skanning forkaster ubekreftet utkast, ugyldiggjør pågående OCR og rydder bildet. En bekreftet økonomipost kan ikke slettes med denne handlingen. Nytt bilde starter en ny skanning.

Ubehandlede/avbrutte bilder utløper etter 15 minutter; foreldreløse mottaks- og arbeidsfiler ryddes etter samme grense. Arbeideren rydder ved oppstart og hver arbeidsrunde. Når arbeideren/serveren er nede, skjer rydding først når den starter igjen. Dette er ikke en garanti om fysisk sletting mens serveren er avslått. Etter sletting må ny OCR bruke et nytt bilde.

## Drift, oppdatering og backup

Allerede godkjent Docker-motor: Tesseract 5.5.0-1+b1 med norsk/engelsk språkdata; Poppler beholdes for eksisterende eldre dokumenter. Ingen ekstern OCR-tjeneste eller nye avhengigheter. Én global OCR-lås, 1 CPU, 768 MiB minne og begrensede underprosesser. Push har egen kø/arbeider. Containerne må dele samme private skannelager og database; oppsettet kan flyttes til annen Docker-host senere.

Migrasjonene 0015 og 0016 er additive. 0016 merker eksisterende dokumenter som eldre originaler uten å endre filene eller økonomien. Eldre originaler ligger fortsatt i `documents` på `/private-documents` og slettes aldri av skanneryddingen. Appen og arbeideren får skriveadgang til `scan-spool`; arbeiderens eldre dokumentlager er fortsatt skrivebeskyttet.

Bevar eksisterende `.env`, databasenavn, Compose-prosjektnavn, databasevolum, `PRIVATE_IMPORT_PATH` og nøkler. Ingen vanlig oppdatering kjører import, seed, restore, volumfjerning eller eierklargjøring. `scripts/backup.ps1` lager databasebackup og arkiv av **kun eldre originaler** fra `/private-documents`. Skannelageret tas aldri med. En gjenopprettet database kan inneholde en ventende skanning uten bilde; den viser da manuell utfylling eller nytt bilde, og skaper ingen økonomipost. Gjenoppretting krever separat autorisasjon; et vanlig pull/build skal ikke utløse den.
