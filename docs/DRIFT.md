# Familieblikk på Synology

Kildekoden er klargjort for privat GitHub-repository og Synology Container Manager. Ingen ekstern utrulling er utført. Domenet er blikk.betilab.com via brukerens eksisterende Cloudflare Tunnel på Synology. Bekreft NAS-ens Linux CPU-støtte for imagene, Container Manager og lagringssti. SMTP er valgfritt ved passordinnlogging.

## Lokal utvikling

Bruk `.venv\Scripts\python.exe` og den godkjente `requirements.lock`. Ikke installer globalt. Sett miljøvariablene fra `.env.example` i PowerShell, med `DJANGO_DEBUG=1`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, `DJANGO_TRUST_PROXY=0`, tom `CSRF_TRUSTED_ORIGINS`, `POSTGRES_HOST=127.0.0.1` og en lokal PostgreSQL 17-database. Kjør `scripts\start-local.ps1`. Testene bruker en egen PostgreSQL-testdatabase, og databasebrukeren må kunne opprette den. Ingen SQLite-konfigurasjon brukes som PostgreSQL-bevis.

## GitHub og NAS

Privat repository er Thugney/Familieblikk. Brukeren har godkjent publisering av denne versjonen. Bruk `main` som stabil gren, `develop` for integrasjon og `codex/` for funksjoner; bruk pull requests for hovedgrenene. GitHub-kontoens betalingsgrense har tidligere blokkert CI, og privat grenbeskyttelse krevde GitHub Pro; ingen av delene skal påstås aktivert uten ny kontroll. Ingen commit eller push utføres automatisk. Gjennomgå Git-indeksen for private filer og hemmeligheter før første commit. GitHub Actions-filen kjører Django-tester med isolert PostgreSQL og minnebasert testepost, aldri ekte SMTP.

Klon repositoryet til en egen NAS-prosjektmappe med en begrenset lesetilgang. Hent godkjent release med `git pull --ff-only`. Opprett `.env` lokalt fra `.env.example`; den skal ikke legges i Git. Opprett prosjekt i Container Manager med `docker-compose.yml`. Behold navnet `familieblikk` og samme databasevolume ved oppdatering. Ikke bruk `down -v`. Bygg image og start prosjektet. Engangstjenesten `migrate` kjører skjemaendringer med eierrollen og oppretter/oppdaterer en separat begrenset approlle. Webappen starter først etter vellykket migrering, bruker bare approllen og får ikke eierpassordet i miljøet. Sett forskjellige `POSTGRES_USER`/`POSTGRES_PASSWORD` og `POSTGRES_APP_USER`/`POSTGRES_APP_PASSWORD`; ta backup før hver oppdatering. Test migrering på separat gjenopprettingsdatabase først ved større oppgraderinger.

Standard Compose bruker `network_mode: host` for app, migrering og database. Webserveren lytter på `0.0.0.0:6451`; samme port er standard i Docker-imaget. Ingen `ports:`-mapping eller ekstra host-overstyring brukes. Tidligere `APP_PORT`/`APP_BIND` i en eksisterende `.env` ignoreres. Bruk den eksisterende Cloudflare-tunnelen for `blikk.betilab.com` med tjeneste `http://192.168.20.135:6451`, som er NAS-adressen bekreftet av Robel. Ingen ekstra reversproxy, TLS-sertifikat eller cloudflared-tjeneste legges til prosjektet. Sett eventuell HTTP Host Header til `blikk.betilab.com`. Se [Cloudflares origin-innstillinger](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/#httphostheader).

`.env.example` og Compose-standardene bruker `DJANGO_ALLOWED_HOSTS=blikk.betilab.com`, `CSRF_TRUSTED_ORIGINS=https://blikk.betilab.com`, `DJANGO_TRUST_PROXY=1`, `DJANGO_HTTPS=0` og debug av. Oppdater disse verdiene også i en eksisterende privat `.env`, som ellers overstyrer standardene. Cloudflare håndterer offentlig HTTPS; appen bruker HTTP til origin og gjenkjenner `X-Forwarded-Proto: https` for sikre cookies og korrekt CSRF-kontroll. Cloudflare [setter denne headeren fra klientens protokoll](https://developers.cloudflare.com/fundamentals/reference/http-headers/#x-forwarded-proto). [Django krever en betrodd proxy](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header) for slik tolkning: begrens direkte tilgang til port 6451 i NAS-brannmuren, slik at bare tunnelkoblingen når origin. Offentlig HTTP skal videresendes til HTTPS av den eksisterende Cloudflare-konfigurasjonen. Første eier bruker den autoriserte forhåndsregistreringen uten SMTP; SMTP kreves bare ved e-postkode eller e-postinvitasjon.

PostgreSQL deler også host-nettverket, men bindes kun til `127.0.0.1`, som standard port **6452**. App og migrering bruker denne localhost-adressen, aldri Docker-navnet `db`. Sett `POSTGRES_PORT` i NAS-ens `.env` hvis 6452 allerede er opptatt; verdien brukes konsekvent av database, helsesjekk, app og migrering. Port 6451 må være ledig for webappen. Compose setter `PGPORT` i databasecontaineren, slik at backup-/restore-verktøy bruker riktig Unix-socket-port. Den versjonerte `docker/postgres/pg_hba.conf` monteres skrivebeskyttet og krever SCRAM-passord for TCP på localhost, også ved bruk av et eksisterende databasevolum. Unix-socket inne i databasecontaineren beholdes for driftskommandoene. Eierpassordet sendes fortsatt ikke til appcontaineren.

Oppsettet retter seg mot Linux/Synology. Docker Desktop krever at **Enable host networking** er aktivert for tilgang fra Windows til host-porten; dette er en Docker-innstilling, ingen alternativ bridge-modus i hostingfilen. Se [Dockers host-nettverksdokumentasjon](https://docs.docker.com/engine/network/drivers/host/). Testet Linux-hostnamespace er ikke bevis på fysisk NAS-utrulling.

## Eksisterende databasevolum og passordformat

Ta backup og kontroller passordformatet **før** et eldre volum flyttes til det nye host-oppsettet. Kjør kontrollen i den fortsatt kjørende databasecontaineren via Unix-socket. Bytt rollenavnene i eksemplet hvis din `.env` bruker andre navn:

```text
docker compose exec db psql -U familieblikk_owner -d familieblikk
SELECT rolname, CASE
  WHEN rolpassword LIKE 'SCRAM-SHA-256$%' THEN 'SCRAM'
  WHEN rolpassword LIKE 'md5%' THEN 'MD5 - konverter forst'
  ELSE 'Passord mangler eller er ukjent'
END AS passordformat
FROM pg_authid WHERE rolname IN ('familieblikk_owner', 'familieblikk_app');
```

Kontrollen viser bare format, aldri passordhashen. Begge roller må bruke SCRAM for TCP med den nye HBA-filen. Hvis en rolle fortsatt har MD5, behold den kjørende containeren og bruk samme interaktive psql-økt:

```text
SET password_encryption = 'scram-sha-256';
\password familieblikk_owner
\password familieblikk_app
```

Skriv inn de tilsvarende eksisterende databasepassordene fra privat `.env` i de skjulte promptene. Da endres bare lagringsformatet; passordverdiene og familiens appkontoer beholdes. Kjør formatkontrollen på nytt, avslutt med `\q`, og start først deretter host-oppsettet. Ikke legg passord i SQL, kommandoargumenter eller logger, og ikke slett eller opprett volumet på nytt. En SCRAM-regel kan ikke bruke en MD5-verifikator; se [PostgreSQLs dokumentasjon om passordautentisering](https://www.postgresql.org/docs/17/auth-password.html).

## Private data og første eierimport

Compose setter også `password_encryption=scram-sha-256` eksplisitt ved hver PostgreSQL-oppstart. Dette overstyrer en eldre MD5-standard i volumets konfigurasjon, slik at senere oppdatering av approllens passord fortsatt lager SCRAM-verifikatorer. Forhåndskontrollen ovenfor trengs likevel for allerede lagrede passord.

Den originale arbeidsboken og importpakken er aldri med i Docker-bygget. Overfør den private `family-budget`-mappen separat med begrensede filrettigheter. Bruk `docker-compose.import.yml` i tillegg og sett `PRIVATE_IMPORT_PATH` til denne mappen. Monteringen er skrivebeskyttet. Eier logger inn på `/passord/` med den forhåndsregistrerte kontoen og åpner Mer → Familiens kildeimport. En eventuell senere e-postkodeflyt kan også brukes etter faktisk verifisering. Systemet sammenligner eieradressen med privat `profile-target.json`, krever autentisert eierøkt med riktig registreringsproveniens og administratorrolle, og kontrollerer kildefilens SHA-256. Ingen konto blir opprettet fra arbeidsbokens personnavn.

Bekreft import, gjennomgå avklaringsutkast og kontroller datoer/klasser før bokføring. Udokumenterte datoer og kurser skal ikke gjettes. Samme serie/kilde kan kjøres på nytt uten duplikater. Endret kilde avvises for eksplisitt diff/avstemming. Nye familier har ingen seeddata. Ikke kall importen ferdig før eierens autentiserte skjermbilder, rad-/beløpsavstemming, annen-familie-avslag og re-login/omstart er dokumentert privat. Behold importoverstyringen så lenge kildevisning og avklaringsutkast trengs; de bokførte dataene ligger uavhengig i databasen.

## Backup, gjenoppretting og omstart

Ta kryptert databasebackup til separat lagring og begrens tilgang; dumpen inneholder familiens data og sesjoner. `scripts\backup.ps1 -Destination <ny-absolutt-sti>` bruker binærsikker `docker cp`. `scripts\restore-test.ps1 -BackupFile <sti>` gjenoppretter bare til en ny separat database. På NAS kan tilsvarende `pg_dump -Fc` og `pg_restore --exit-on-error` kjøres i DB-containeren. Oppbevar krypteringsnøkkel utenfor NAS og test faktisk gjenoppretting regelmessig. Angi konkret oppbevaring og ansvar før lansering.

Før lansering: noter kategorier/poster/importutkast og finansielle summer; ta backup; erstatt app- og DB-container uten å slette volum; logg inn igjen og avstem identiske data; gjenopprett til separat database og avstem igjen. Bekreft at gammel utlogget sesjonscookie ikke gir tilgang. Disse kontrollene er releasekrav og må utføres på faktisk PostgreSQL, ikke antas ut fra Compose-filen.

## Privilegieprøve

Etter oppstart skal appforbindelsen kunne registrere og lese budsjettposter, men en `CREATE TABLE`-prøve i en rollback-transaksjon skal avvises. Approllen skal ha `rolsuper=false`, `rolcreatedb=false`, `rolcreaterole=false`, ikke eie tabeller og ikke ha CREATE på public-skjemaet. Migrasjonstjenesten skal være avsluttet med kode 0. Ikke del eller skriv ut full Compose-config: interpolerte miljøverdier inneholder hemmeligheter. Bruk `docker compose config --quiet` for strukturkontroll.


## Lokal forhåndsregistrering uten SMTP

Den første eieren opprettes kun med `python manage.py provision_owner --confirm --family-name "Min familie" --password-stdin`, med passord sendt privat via stdin. Alternativet er miljøvariabelen `FAMILIEBLIKK_OWNER_PASSWORD` kun i den enkelte kommandoprosessen. Passordet skal ikke stå i kommandoargumenter, URL, logger, Git eller Docker-image. Bruk den skrivebeskyttede private importmonteringen under oppsettet; kommandoen kontrollerer originalens SHA-256 og den eksplisitte eierbindingen. Minstekrav er 12 tegn og Django-passordvalidering; bruk et langt tilfeldig startpassord.

Kommandoen oppretter en tom egen familie og en administrator med `identity_method=preregistered_owner`, eksplisitt proveniens og `verified_at=NULL`. Gjentakelse med samme eierproveniens oppretter ingen ny konto og endrer ikke passordet. Eksisterende kontoer overtas eller nullstilles aldri. Ingen e-post sendes, og e-postverifisering påstås ikke.

Passordinnlogging finnes på `/passord/`, og egen passordendring på `/passord/endre/`. Bare eksplisitt forhåndsregistrerte, aktive kontoer kan bruke passordveien. Feilforsøk begrenses per adresse og IP; mutasjoner krever CSRF og innlogging roterer sesjonen. `DJANGO_PREREGISTERED_LOGIN=0` deaktiverer denne innloggingsveien. Eksisterende e-postkodeflyt beholdes for senere bruk.

I Familie og innstillinger kan administrator registrere nye medlemmer eller administratorer i sin egen familie med bekreftet startpassord. Den første eieren har i tillegg en særskilt registratortillatelse til å opprette en ny adskilt familie med egen administrator. Vanlige administratorer får ikke denne tillatelsen automatisk. Registrering gir aldri økonomitilgang til den nye familien, flytter ingen eksisterende konto og sender ingen e-post. Del startpassordet privat; den nye brukeren kan endre det etter innlogging. Importen av arbeidsboken er fortsatt begrenset til den eksakte private eierbindingen, også om andre familier er forhåndsregistrert.

## Kalendervarsler og oppdatering av den overførte NAS-profilen

Behold eksisterende `.env`, `POSTGRES_DB`, `DJANGO_SECRET_KEY`, databasevolum og privat importoverstyring når koden oppdateres. Ikke kopier `.env.example` over den private filen og ikke kjør eierklargjøring, import eller restore på nytt. `Familieblikk-Synology-overforing.zip`, eventuell mappe med samme navn og `private-data/` er ignorert av Git; Docker-bygget tillater bare applikasjonskilde og låste avhengigheter. Vanlig oppstart migrerer den eksisterende databasen, klargjør pushnøkkel og gir eksisterende approlle tilgang til de nye tabellene. Den oppretter ingen familier eller kontoer.

Bruk samme prosjektmappe/-navn og Compose-filer som ved overføringen. Når importoverstyringen allerede brukes, er oppdateringskommandoen:

```text
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.import.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.import.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.import.yml ps
```

Migrering skal avsluttes med kode 0, og `app`, `db` og `push-worker` skal kjøre. Pusharbeideren bruker host-nettverk og den samme begrensede approllen, uten eierpassord eller privat importmontering. Ingen nye `.env`-verdier kreves. VAPID-privatnøkkel og nettleserabonnementer er kryptert i eksisterende PostgreSQL med en nøkkel avledet fra opprinnelig `DJANGO_SECRET_KEY`. Ta med den uendrede hemmeligheten og databasen i privat backup. Endres hemmeligheten uten migrering av krypteringen, stopper oppstart fremfor å erstatte eksisterende pushidentitet.

Hvert familiemedlem velger **Aktiver varsler** på sin egen enhet. Oppfordringen vises på alle innloggede familiesider til enheten er aktivert; bjellen åpner Varsler med enhetsvalg og ulestantall. Nettleserens tillatelsesprompt vises bare ved dette valget. HTTPS kreves utenfor localhost. På iPhone må appen legges til på Hjem-skjerm og åpnes derfra først. **Send testvarsel til meg** køer bare et varsel til den aktuelle innloggede enheten og er begrenset til én gang per minutt. Test aldri andre familiemedlemmers enheter uten deres separate samtykke. Regningsoversikten og private kalendervarsler er fortsatt tilgjengelige i appen når push er avslått eller mangler støtte.

Kalenderlagring oppretter mottakervarsler og kø i samme databasetransaksjon. Nye avtaleserier, nye deltakere lagt til eksisterende avtaler og endrede godta/avslå-svar varsler; egne handlinger og uendrede svar sender ikke til personen selv. Worker sjekker familie, aktiv konto, ekte Django-økt, utløp og gjeldende passordhash før hver sending. Utlogging/deaktivering stopper fremtidig sending. Meldinger allerede overtatt av nettleserens pushtjeneste kan ikke trekkes tilbake; transportens TTL er 24 timer med høy prioritet. Dette garanterer ikke umiddelbar OS-visning. Låseskjermen viser bare generisk aktivitetstype. Detaljer åpnes gjennom innlogging og mottaker-/familiekontroll.

Nettfeil, HTTP 429 og 5xx prøves igjen opptil åtte forsøk innen 24 timer. Retry-After respekteres opptil én time per venting. HTTP 404/410 sperrer utgåtte abonnementer; øvrige avslag vises som leveringsfeil. Worker kan startes på nytt uten å miste køen. Lease og databaselås hindrer samtidige arbeidere i å sende samme jobb; etter prosessdød overtas jobben etter to minutter. En prosess kan dø etter at leverandøren har mottatt meldingen, før databasekvitteringen lagres: transporten gir derfor minst-én-gang-levering, med stabil Topic/varsel-tag som erstatter samme synlige varsel ved ny sending. Fysisk OS-visning avhenger av nettleser, tillatelse, nett og operativsystemets fokusinnstillinger.

Ved feilsøking: `docker compose logs --tail=50 push-worker migrate` viser generiske feil uten abonnementstokener eller private nøkler. Ikke skriv ut full Compose-config eller databaseinnhold i delte logger. Offisiell transport: [pywebpush](https://github.com/web-push-libs/pywebpush), [Mozilla Autopush](https://mozilla-services.github.io/autopush-rs/http.html) og [Apple Web Push](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers).


## Bindende databevaring ved hver commit, push og vanlig oppdatering

Kontroller at den eksisterende `.env`, `POSTGRES_DB`, Compose-prosjektnavn, databasevolum, `PRIVATE_IMPORT_PATH` og alle nøkler bevares. Bruk bare kompatible migrasjoner på eksisterende database. Aldri kjør `down -v`, volumfjerning eller prune, flush/drop/truncate, ny restore/import/seed, eierklargjøring eller erstatning av nøkler som del av en vanlig oppdatering. Destruktiv datamigrering krever separat, uttrykkelig godkjenning. Releasetest skal kontrollere både Compose-kontrakten og lesende avstemming av de private kildepostene; syntetisk omstartstest alene beviser ikke bevaring av den faktiske profilen.


Teststatus følger bare den aktuelle innloggede enhetens testjobb. «Venter» betyr kø, «sender» betyr at arbeideren sender, og «forsinket» betyr at et nytt forsøk er planlagt. «Pushtjenesten har tatt imot» betyr leverandøraksept, aldri kvittering for OS-visning. Automatisk kontroll er tidsavgrenset; **Kontroller teststatus** gjenopptar den uten å sende et nytt testvarsel. Ved ventende kø kontrolleres `push-worker` separat; å åpne appen er ikke en leveringsmekanisme. Etter utlogging/ny innlogging må enheten aktiveres igjen, også når nettleserens tillatelse fortsatt er gitt.
