# Sikkerhetskontroll – 24. oktober 2026

Denne releasen herder Familieblikk mot ressursmisbruk og reduserer angrepsflaten rundt innlogging og skanning. Den installerer ingen ny applikasjonsavhengighet. Den endrer ikke `.env`, databasevolumer, Compose-navn, private importdata eller nøkler.

## Funn og tiltak

| Funn | Tiltak |
|---|---|
| En innlogget bruker kunne velge år 9999 og utløse 95 678 månedlige databaseoperasjoner per regningsserie. Gamle kildeankre ga tilsvarende effekt. | Kontrollerte arbeidsgrenser før materialisering og lesende beregninger. Ingen stille avkorting av historikk; for omfattende perioder gir en forklarende feil. |
| Sperret passordinnlogging fortsatte å beregne kostbare passordhasher. Vellykkede forsøk brukte ingen arbeidskvote. | Sperrede forespørsler avvises før konto-/hasharbeid. Passord på over 1024 tegn avvises før hashing. Egen kvote teller alle hashforsøk: 20 per adresse og 120 per socket-IP på 15 minutter; de eksisterende feilkvotene 5/30 beholdes. |
| Samtidige forespørsler kunne passere e-postkodekvoter før en annen transaksjon registrerte sendingen. | PostgreSQL-låser serialiserer IP- og adressekontrollen, også før første kode finnes. Låseforsøk venter høyst ett sekund per låsegruppe; SMTP har fem sekunders socket-timeout. |
| Ingen Content Security Policy begrenset konsekvensene av eventuell fremtidig script-injeksjon. | Lokale scripts, ingen inline-script/eval, ingen innramming/objekter/ekstern skjemasending; kamera, skrifter og PWA beholdes. Inline-stiler beholdes for eksisterende grafer/UI. |
| Native bilde-/OCR-prosesser arvet appens hemmeligheter i miljøvariabler. | Begrenset miljø og ingen core dumps; dette er ekstra beskyttelse, ikke en full prosess-sandkasse. |
| Eldre PDF-jobber kunne fortsatt nå Poppler med uavklarte sikkerhetsvarsler. | Automatisk OCR av eldre PDF-jobber stoppes. Bruk manuell utfylling eller nytt kamerabilde. Eksisterende originalfiler og økonomidata slettes ikke. |
| Baseimaget inneholdt eldre Debian-pakker selv med låst Python-miljø. | Bygget oppdaterer eksisterende Debian-pakker før installasjon av allerede godkjent OCR-runtime. Brotli `1.1.0-2+deb13u1` og liblzma5 `5.8.1-1+deb13u2` er kontrollert i testimaget. |

Arbeidsgrenser: maksimalt 600 måneder per beregningsløp, en valgt periode innen 599 måneder fra nå, og 10 000 beregningssteg samlet per forespørsel eller selvstendig skriveoperasjon. Oppdatering av fremtidige avledede planer teller også. Engangsregninger teller ett steg, og gammel gjeld uten renteberegning eller uendrede datoer ved enkle navneendringer avvises ikke unødvendig. Beløp beholder samme regneregler. Feilen betyr at datoene må kontrolleres; lagret historikk forkortes ikke.

## Avhengigheter og gjenværende begrensninger

Alle **27** direkte/transitive versjoner i `requirements.lock`, inkludert Windows- og Linux-spesifikke pakker, ble slått opp mot OSV og PyPI uten kjente sårbarhetstreff. Kontrollen kjører også ved push/PR i GitHub Actions. En utilgjengelig eller ufullstendig kilde gir feilstatus; det regnes ikke som et rent resultat. CI bygger dessuten produksjonsimaget og kontrollerer de to rettede Debian-versjonene, brukeren uten root, pakkekonsistens og norske/engelske OCR-modeller.

Kjør på nytt med eksisterende Python:

```powershell
.\.venv\Scripts\python.exe scripts\audit-dependencies.py
```

Django 5.2.18 inkluderer sikkerhetsrettelsene fra 6. oktober. Se [Djangos sikkerhetsutgivelse](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/). [Debians sikkerhetsdatabase](https://security-tracker.debian.org/tracker/) ble brukt til versjonskontroll av 125 installerte kildepakker. Baseline hadde 245 åpne/ubestemte eller nyere-rettede varsler; to hadde tilgjengelige pakkerettelser. Dette er en kildepakkeoversikt, ikke 245 påviste angrep mot appen. Flere gjelder verktøy/funksjoner som appen ikke bruker. Ingen av disse var merket high/medium av Debian; mange hadde ennå ingen vurdering, og det betyr **ikke** at de er ufarlige.

Ny kontroll av det ferdige imaget fant **ingen gjenstående tilgjengelige versjonsrettelser** i den samme Debian-kontrollen, men **243 åpne/ubestemte kildepakkevarsler** gjenstår. Releasen gjør derfor **ikke** krav på «null sårbarheter i operativsystemet». Åpne upstream-varsler, ukjente feil, NAS-operativsystemet, tunnelprogrammet og nettleseren inngår i den gjenværende risikoen. Native dekodere har tids-/minnegrenser og kjører uten root, men deler fortsatt tjenestens bruker og nettverk. PDF-parseren er tatt ut av den automatiske køflyten; nye skanninger tillater bare PNG/JPEG. Ikke fjern eller erstatt private data som et sikkerhetstiltak.

## Cloudflare Free – klargjort oppsett, ikke aktivert av denne releasen

Ingen Cloudflare-kontotilkobling var tilgjengelig; dashboardet viste innlogging. Tre lesende HEAD-forespørsler til den offentlige innloggingen, `/.env` og `/.git/config` fikk 403 fra Cloudflare. Dette viser at kanten avviste kontrollene, men bekrefter verken hvilke regler som er aktive eller appens produksjonsheadere. NAS/tunnelinnstillinger er ikke endret.

1. Kontroller at **Free Managed Ruleset** er aktiv i Security. Gratisplanen inkluderer dette og automatisk DDoS-beskyttelse, men ikke hele det betalte managed-rules-utvalget. Se [Cloudflare WAF-planer](https://developers.cloudflare.com/waf/) og [samspill mellom sikkerhetsfunksjonene](https://developers.cloudflare.com/waf/feature-interoperability/).
2. Bruk den ene gratis **Rate limiting rule** på innloggingsstiene. Uttrykk:

   ```text
   http.request.uri.path in {"/passord/" "/innlogging/" "/kode/"}
   ```

   Start med **10 forespørsler per 10 sekunder per IP**, handling **Block**, varighet **10 sekunder**. Dette er et anbefalt startnivå; kontroller familiens normalbruk. Gratisplanen støtter bare path/verified-bot i uttrykket, IP som tellegrunnlag og 10-sekunders perioder; ikke lim inn et betalt eksempel med host, metode eller 15-minutters vindu. Regelen gjelder disse stiene på hele sonen `betilab.com`, så sjekk om andre apper bruker samme stier før aktivering. Se [eksakte begrensninger](https://developers.cloudflare.com/waf/rate-limiting-rules/).
3. En av opptil fem gratis **Custom rules** kan blokkere vanlige forsøk på å hente private filer, avgrenset til denne appen:

   ```text
   http.host eq "blikk.betilab.com" and (
     starts_with(http.request.uri.path, "/.git") or
     starts_with(http.request.uri.path, "/.env") or
     starts_with(http.request.uri.path, "/private-data/") or
     starts_with(http.request.uri.path, "/work/")
   )
   ```

   Handling **Block**. Appen serverer allerede ikke disse filene; regelen stanser trafikken tidligere. [Gratis custom-rule-grenser](https://developers.cloudflare.com/waf/custom-rules/).
4. Kontroller HTTPS-omdirigering ved kanten og at cache-regler ikke overstyrer appens `private, no-store`. Ingen «Cache Everything» på innlogging, app, API eller dokumenter. Behold HTTP mellom eksisterende tunnel og NAS som avtalt. Ikke aktiver HSTS for alle underdomener uten å kontrollere de andre tjenestene.
5. Begrens tilgang til NAS-port **6451** til tunnelens faktiske lokale avsender med NAS-brannmuren. Ikke portvideresend 6451/6452 fra internett. PostgreSQL skal fortsette å lytte bare på localhost. Tunnelen kobler til lokalt; en liste med Cloudflares offentlige edge-IP-er alene er ikke riktig avsenderliste for denne origin-forbindelsen. [Beskytt origin](https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/).

Appens IP-kvote bruker fortsatt socket-avsenderen. Bak en tunnel kan flere besøkende dermed dele IP-kvote. Vilkårlige `CF-Connecting-IP`/`X-Forwarded-For`-headere stoles ikke på automatisk. Edge-regelen teller besøkendes IP før tunnelen. En fremtidig appendring til proxy-IP krever en eksplisitt betrodd avsendergrense.

Bot Fight Mode er ikke nødvendig som første tiltak: gratisvarianten kan ikke unntas gjennom custom rules og kan forstyrre API/PWA. Kontroller først innlogging, skanning, kalender og varsler dersom den aktiveres. [Cloudflares dokumentasjon](https://developers.cloudflare.com/waf/feature-interoperability/).

## Hent og bygg på NAS

Bruk samme eksisterende prosjektmappe og `.env`. Hent funksjonsgrenen `codex/security-hardening` med vanlig Git fetch/switch/pull. Dersom lokale sporede endringer finnes, avklar dem uten reset. Bygg appimaget med `docker compose build --pull --no-cache`, slik at Debian-kontrollen kjøres på nytt; start deretter med eksisterende Compose-oppsett og `docker compose up -d`.

Ingen ny import, restore, seed, nøkkeloppretting eller databasevolum er nødvendig. Ikke bruk `down -v`, prune eller en ny prosjektidentitet. Bekreft deretter innlogging, kjent historikk, budsjettdeling, kameraskanning, handleliste og kalender på mobil/PC.

## Verifikasjon

- **524 Django-tester bestod** i endelig Linux-image mot egen PostgreSQL-testdatabase (262,719 sekunder), inkludert isolasjon, rettigheter, CSRF, samtidighet, kamera, shopping, kalender og økonomiberegninger. Django system check og migrasjonsdriftkontroll bestod; ingen ny migrasjon er lagt til.
- **65 JavaScript-/Compose-kontroller** og **8 avhengighetsport-tester** bestod. Sårbarhetsfunn fra hver av de to kildene stopper CI; nettverksfeil blir ukjent/feil.
- Produksjonsimaget ble bygget. Alle **161 appfiler** ble sammenlignet byte for byte med arbeidskopien. `pip check`, UID 10001, fravær av private filer, rettede Debian-versjoner, ekte PNG-dekoding og norsk/engelsk OCR på en fiktiv kvittering bestod.
- Nettleseren gjennomførte syntetisk passordinnlogging, budsjettvalg, dynamisk oversikt, kalenderdialog, skanneside og varselside uten observerte konsoll-/CSP-feil. Fysisk mobilkamera, ekte push-levering og installert mobil-PWA må fortsatt prøves på brukerens enheter; ingen familiemedlemmer mottok testvarsler.
- Lesende avstemming av den faktiske lokale profilen bekreftet **72 kildeposter**, og **14 beskyttede konfigurasjons-/kildefiler** hadde identiske hasher før/etter. Dette er lokal bevaringsevidens; NAS er ikke oppdatert eller avstemt her.
- Tre uavhengige reviewlag fant 13 enkeltfunn, inkludert overlapp. Rettelsene dekker strengere nedlastings-CSP, feilside, arbeidsgrenser, historiske metadata, auth-venting/kvoter og test-/CI-hull. De ble kontrollert med målrettede regresjoner og den endelige fulle kjøringen. En ekstra sluttgjennomgang fra kildeagenten kunne ikke kjøres på grunn av review-tjenestens begrensning; den er ikke telt som bestått eller som uavhengig sluttgodkjenning.

Sporbar oppsummering: `.project-init/security-build-evidence.json`. Full lokal test-/reviewlogg ligger under gitignored `work/`; privat avstemmingsinnhold ligger bare under gitignored `private-data/`.
