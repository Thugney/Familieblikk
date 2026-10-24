---
title: 'Åpne riktig budsjett og forstå fremtidige måneder'
type: bugfix
created: '2026-10-24'
status: done
---

## Bestilling og avgrensning

Senere autorisasjon 2026-10-24: Robel bestilte uttrykkelig commit og push av alle rettelsene. Publiser bare den verifiserte funksjonsgrenen; selve NAS-oppdateringen utføres av Robel. Faktiske feilregistreringer endres ikke automatisk. Se `docs/OPPDATERING.md` for bevaringskontroller og konkrete NAS-kommandoer.

Brukeren ber om å fortsette den pågående feilrettingen: unngå unødvendig budsjettvalg når én tilgang finnes, forbedre budsjettsiden og rydde gamle delingsforslag fra aktive oppgaver, skjule varseloppsett når enheten er aktiv, og forklare fremtidig månedsbeløp og hvor feil kan rettes. Bestillingen autoriserer lokal implementasjon, ikke endring av faktiske økonomiposter, tilgangsregler, commit, push eller utrulling.

## Kontrakt

- Automatisk åpning av eneste tillatte budsjett ved normal inngang. Eksplisitt administrasjon er tilgjengelig med manage=1. Aldri gjett budsjett når flere finnes, gjenbruk tilbakekalt tilgang eller ignorer ugyldig eksplisitt area.
- Aktuelle delingsforslag vises som oppgaver. Utdaterte eller fullførte forslag vises i sammenfoldet historikk; ingen sletting eller endring av tilganger som sideeffekt av lesing.
- Budsjettsiden bruker eksisterende grønne/offwhite flater, Figtree, avrundinger og knapper. Kort med tydelig navn, tilgang og åpnehandling; oppretting og historikk er sekundære. Mobil stables, lange navn brytes, fokus beholdes.
- Hele varselboksen skjules bare ved bekreftet aktiv enhetsbinding på andre sider enn Varsler. Varsler er alltid tilgjengelig i menyen. Ukjent, feil, utløpt og frakoblet status skal kunne forstås og håndteres.
- Fremtidig oversikt merkes som anslag etter faste trekk, ikke penger tilgjengelig nå. Vis forventet inntekt, regninger, sparing, gjeld og årsutgifter separat. Annet planlagt forbruk er ikke ferdig avstemt i dette tallet; lenke går til full månedsplan for den valgte måneden.
- Bruk lagret planinntekt når den finnes; ellers foreslå allerede registrerte forventede inntekter i samme budsjett og måned. Manglende inntekt forblir ukjent, eksplisitt null beholdes. Verken dette anslaget eller et utkast bokfører mottatt inntekt.
- Vis snarveier til inntektsposter, regninger, sparing og gjeld. Rett en regning eller stopp serie via eksisterende eksplisitte bekreftelsesflyt. Ingen automatisk klassifisering etter postnavn.

## Verifikasjon

Syntetiske integrasjonstester for én/flere/ingen/tilbakekalt budsjettadgang, eksplisitt administrasjon, gammel versus aktiv historikk, forventet versus mottatt inntekt, null/ukjent, valgt fremtidig måned og skrivevern. Node-regresjoner for varselboksen og planfanen. Nettleser på syntetiske data ved mobil, nettbrett og PC. Fersk uavhengig kontroll før ferdigmelding. Faktisk app undersøkes bare for å forklare brukerens synlige data; private detaljer skal ikke inn i kildekoden eller spesifikasjonen.

## Resultat

Publiseringskontroll: siste fulle kjøring består med 565 Django-tester og 68 Node-/Compose-kontroller. Regresjon bekrefter at gjentakende gjeldsregning og høyere månedsplan telles én gang både før og etter betaling. Tekstene forklarer nå kategorimerke versus posttype og skillet mellom vanlige regninger og gjeld. Ingen beregningsregel er endret av denne siste presiseringen. Lokal bevart eierprofil er avstemt lesende mot 72 kildeposter; `.env`, Compose- og private kildefiler bevaringskontrolleres før/etter publisering. Dette er ikke en kontroll av den fysiske NAS-databasen.

Lokalt implementert og kontrollert, ikke publisert. 563 Django-tester besto full kjøring; etter siste justering av fremtidssiden besto 14 berørte tester, inkludert ny kontroll av videreført spareplan og ikke-materialisert regning. Alle 68 Node-kontroller består. Ingen nye migrasjoner eller avhengigheter. Syntetisk nettleser viste automatisk åpning for én tilgang, eksplisitt administrasjon, sammenfoldet og bevart historikk og riktig valgt planmåned uten horisontal overflyt ved 390, 768 og 1440 px i kontrollerte visninger.

Fersk kildekontroll fant tre feil som ble rettet: fremtidig GET materialiserte poster, gjeldsminimum manglet i anslaget, og ukjent inntekt hadde feil kildeforklaring. Oppfølgende kontroll fant motstridende kort for sparing og regninger; fremtidssiden bruker nå samme projiserte grunnlag som planleggeren og har egne seksjoner. Siste uavhengige kontroll fant ingen gjenstående blokkering. Ingen faktisk familiepost ble korrigert automatisk. Maskinlesbare bevis: `work/budget-followup-verification.json`.
