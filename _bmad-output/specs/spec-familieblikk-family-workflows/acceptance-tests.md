# Verifikasjonskontrakt

Dette er planlagte tester, ikke påståtte pass. Fiktiv preview validerer samhandling; den beviser ikke backend, transaksjoner eller NAS. Etter eksakt aksept kjøres Django/PostgreSQL-integrasjon, relevante nettleserflyter og lesende privat avstemming.

| ID | Oppsett/handling | Forventet bevis |
|---|---|---|
| AT-01 | Rett ubetalt ordinær 1 000 til 900 kr. | Samme ID/slot, reserve −100, tilgjengelig +100, neste måned uendret; audit før/etter. |
| AT-02 | Flytt oktoberforfall til november; materialiser begge måneder gjentatte ganger. | Oktober-slot flyttet én gang, opprinnelig oktober gjenoppstår ikke, november-slot består separat. |
| AT-03 | Avbryt feilført ubetalt forekomst; materialiser, restart, gjenopprett. | Avbrutt gir null reserve og ingen ny forekomst; gjenopprett gir én reserve og ny hendelse. |
| AT-04 | Arkiver med virkningsdato; skjul modul; gjenoppta senere. | Ingen nye slotter i stoppintervallet; eksisterende reelle ubetalte/betalte består; skjuling endrer ingen sum. Individuelle rettinger overlever serieendring. |
| AT-05 | Betal 1 000; angre feilregistrering; rett til 900; registrer på nytt. | Kun 900 aktiv utgift, ingen aktiv reserve, opprinnelig 1 000 bevart reversert. Gjenoppretting av gammel betaling avvises. |
| AT-06 | To samtidige betal/angre/gjenopprett og identisk retry. | Én aktiv betaling/hendelse per kommando; payload-endring med samme nøkkel og stale versjon gir konflikt uten bivirkning. |
| AT-07 | Refunder 200 av betalt 1 000; forsøk angre original og refundere 801 til. | Original beholdes, netto 800 på riktige datoer, ingen reserve; angre blokkeres; overskridelse avvises. Kryssår avstemmes. |
| AT-08 | Slett ny egen post, gjenopprett og inspiser audit. | Samme ID/sekvens/koblinger, varig før/etter/aktør/tid; eldre ufullstendig sletting lover ingen gjenoppretting. |
| AT-09 | Fremmed familie-ID, annen oppretter, tilbakekalt modul i åpent skjema/retry. | Avslag ved GET/POST/CSV/historikk; ingen metadata/summer; tilbakekall gjelder eksisterende økt og replay. |
| AT-10 | Bills-only medlem; gjeld/fond uten ekstra adgang; historisk snapshot med skjult lenke. | Tillatt ordinær betalingshistorikk synlig uten budget; sammensatte og historiske skjulte data avvises. |
| AT-11 | Endre nyere versjon og forsøk gammel gjenoppretting; trekk innskudd som finansierte senere uttak; rett fondsbetaling. | Konflikt/valideringsfeil bevarer alt. Fondsavstemming teller én gang; senere balanser gyldige. |
| AT-12 | CSV med periode/kategori/status, flere sider og tekst =1+1. | Samme tillatte fulle utvalg og sum som skjermfilter, dokumentert datobasis, korrekt norsk tegnsett/escaping og formelnøytralisering. |
| AT-13 | Admin aktiverer Gjeld; begrenset medlem åpner direkte URL. | Modul blir oppdagbar for tillatte medlemmer; medlem får ikke nye rettigheter; ingen økonomiske mutasjoner. |
| AT-14 | Mobil/PC med tastatur, offline, feil og tom historikk. | Menyer/dialoger kan brukes med fokus/etiketter; avbryt gjør ingenting; utkast beholdes ved feil; status bekreftes først etter lagring. |
| AT-15 | Kompatibel migrering og vanlig containeroppdatering på eksisterende testdatabase. | ID/beløp/dato/importreferanser og nye historikkrader består; migrering feiler tydelig ved slotkollisjon. Compose-kontrakt, .env/nøkler/volum og lesende avstemming av faktisk privat kilde kontrolleres separat. |

Alle økonomiske tester omfatter ordinær, gjeld og årsfond når relevant. Regresjon dekker konto/modulrettigheter, kalender/push, eksisterende beregningsmotor og privat import. Ingen testnotification til familien eller NAS-endring følger av denne planen.
