---
title: 'Lesbar og kort fremtidsoversikt'
type: bugfix
created: '2026-10-24'
status: done
---

Brukeren avviser den publiserte fremtidsoversiktens uformaterte regningsliste. Rett samme leveranse innen eksisterende design og autorisasjon for alle feilrettelser/commit/push; NAS-oppdatering gjøres av brukeren. Ingen endring av faktiske økonomiposter, beregningsregler, migrasjoner eller avhengigheter.

Kontrakt: behold Figtree, grønn anslagsflate, kremhvite kort og eksisterende navigasjon. Oversikten viser et kort sammendrag med inntil fem ubetalte regninger sortert etter dato/navn, lesbar norsk dato, regningstype og høyrestilt beløp. Oppgi totalt antall og tilby alle via en eksplisitt utvidet oversikt (`bills=all`) med samme lesende beregningsgrunnlag; summer inkluderer fortsatt hele grunnlaget. Dette lar også lesere se alle virtuelle forfall uten GET-skriving. Lagrede regninger åpner sin eksakte lesbare historikk; virtuelle forfall åpner seriens lesbare historikk uten å materialisere data. Budsjett og måned bevares i URL-er. Ingen mottatt-status eller andre økonomiske felt endres ved visning.

Full månedsplan redigeres på eksisterende Budsjett & Plan-side. Fremtidsoversikten viser et kompakt plankort, viser manglende beløp ærlig og tilbyr riktig målmåned. Siste tre poster og alle-posters lenke bevares. Inneværende måneds forbruksoversikt og hele planleggerens funksjon beholdes. Mer forklaring samles i en tastaturtilgjengelig detaljvisning. Mobil stables; navn brytes, beløp forblir tydelige og trykkflater minst 44px. Ingen vesentlig informasjon baseres bare på farge.

Versjoner endrede statiske appressurser med innholdshash, slik at den nye presentasjonen ikke kombineres med tidligere lagret CSS/JavaScript. Ingen endring av autentisert caching eller service-worker-protokoll.

Verifiser: syntetisk GET uten databaseskriving, fem av mange inkludert eksakte historikklenker og hele beregningsgrunnlaget, lesertilgang, tom tilstand, lang tekst, mobil/nettbrett/PC, linkmål og faktisk knappgeometri, versjonerte ressurs-URL-er, aktuelle regresjoner og uavhengig kildekontroll. Faktiske familieverdier blir aldri testfixturer eller commit-innhold.

Resultat: 570 tester i full Django/PostgreSQL-kjøring, 68 Node-/Compose-kontroller og 13 berørte tester etter siste leserretting består. Ingen nye migrasjoner. Uavhengig review fant et problem med at lesere ikke kunne åpne alle virtuelle forfall via den gamle regningssiden; dette er rettet med lesende utvidet oversikt og egen regresjon. Ny kildekontroll uten gjenværende blokkere.

Syntetisk nettleser: fem standardrader, alle-ni-visning og tilbake til fem, samme økonomiske beløp i begge moduser, riktig valgt planmåned på full planleggerside, tastaturstyrt forklaring og ingen konsollfeil. Lange navn, hele handlingsflater og beløpskolonner er kontrollert ved 320/355/390/768/1440 px uten klipping eller overlapp. Bevis og skjermbilder: `work/compact-overview-verification.json`, `work/compact-overview-mobile.png`, `work/compact-overview-desktop.png`. Faktisk app ble bare lest; brukerens viewport bevares. NAS oppdateres fortsatt av brukeren.
