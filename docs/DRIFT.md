# Familieblikk på Synology

Kildekoden er klargjort for privat GitHub-repository og Synology Container Manager. Ingen ekstern utrulling er utført. Bekreft NAS-modell, Linux CPU-støtte for Python/PostgreSQL-image, DSM/Container Manager-versjon, lagringssti, HTTPS-domene og SMTP før lansering.

## Lokal utvikling

Bruk `.venv\Scripts\python.exe` og den godkjente `requirements.lock`. Ikke installer globalt. Sett miljøvariablene fra `.env.example` i PowerShell, med `DJANGO_DEBUG=1`, `POSTGRES_HOST=127.0.0.1` og en lokal PostgreSQL 17-database. Kjør `scripts\start-local.ps1`. Testene bruker en egen PostgreSQL-testdatabase, og databasebrukeren må kunne opprette den. Ingen SQLite-konfigurasjon brukes som PostgreSQL-bevis.

## GitHub og NAS

Opprett privat repository under riktig GitHub-konto etter eksplisitt godkjenning. Bruk `main` som stabil gren, `develop` for integrasjon og `codex/` for funksjoner; beskytt hovedgrenene med pull request og bestått CI. Ingen commit eller push utføres automatisk. Gjennomgå Git-indeksen for private filer og hemmeligheter før første commit. GitHub Actions-filen kjører Django-tester med isolert PostgreSQL og minnebasert testepost, aldri ekte SMTP.

Klon repositoryet til en egen NAS-prosjektmappe med en begrenset lesetilgang. Hent godkjent release med `git pull --ff-only`. Opprett `.env` lokalt fra `.env.example`; den skal ikke legges i Git. Opprett prosjekt i Container Manager med `docker-compose.yml`. Behold navnet `familieblikk` og samme databasevolume ved oppdatering. Ikke bruk `down -v`. Bygg image og start prosjektet. Engangstjenesten `migrate` kjører skjemaendringer med eierrollen og oppretter/oppdaterer en separat begrenset approlle. Webappen starter først etter vellykket migrering, bruker bare approllen og får ikke eierpassordet i miljøet. Sett forskjellige `POSTGRES_USER`/`POSTGRES_PASSWORD` og `POSTGRES_APP_USER`/`POSTGRES_APP_PASSWORD`; ta backup før hver oppdatering. Test migrering på separat gjenopprettingsdatabase først ved større oppgraderinger.

Compose publiserer appen på loopback port 8000. Koble Synologys HTTPS-reversproxy til denne porten, sett korrekt domene i `DJANGO_ALLOWED_HOSTS` og `CSRF_TRUSTED_ORIGINS`, og bruk sikre cookies. Sett `DJANGO_HTTPS=1` når HTTPS videresendes korrekt. Sett `DJANGO_TRUST_PROXY=1` bare når Synology-proxyen fjerner klientens X-Forwarded-Proto og setter sin egen korrekte verdi. Vurder `DJANGO_HSTS_SECONDS` først etter at HTTPS er verifisert. Databasen er kun på et privat internt nett og har ingen publisert port. Deaktiver debug. Første eier kan bruke den eksplisitt autoriserte lokale forhåndsregistreringen nedenfor uten SMTP. SMTP kreves bare hvis e-postkode eller e-postinvitasjoner tas i bruk.

## Private data og første eierimport

Den originale arbeidsboken og importpakken er aldri med i Docker-bygget. Overfør den private `family-budget`-mappen separat med begrensede filrettigheter. Bruk `docker-compose.import.yml` i tillegg og sett `PRIVATE_IMPORT_PATH` til denne mappen. Monteringen er skrivebeskyttet. Eier logger inn på `/passord/` med den forhåndsregistrerte kontoen og åpner Mer → Familiens kildeimport. En eventuell senere e-postkodeflyt kan også brukes etter faktisk verifisering. Systemet sammenligner eieradressen med privat `profile-target.json`, krever autentisert eierøkt med riktig registreringsproveniens og administratorrolle, og kontrollerer kildefilens SHA-256. Ingen konto blir opprettet fra arbeidsbokens personnavn.

Bekreft import, gjennomgå avklaringsutkast og kontroller datoer/klasser før bokføring. Udokumenterte datoer og kurser skal ikke gjettes. Samme serie/kilde kan kjøres på nytt uten duplikater. Endret kilde avvises for eksplisitt diff/avstemming. Nye familier har ingen seeddata. Ikke kall importen ferdig før eierens autentiserte skjermbilder, rad-/beløpsavstemming, annen-familie-avslag og re-login/omstart er dokumentert privat. Kjør deretter appen uten importoverstyringen.

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
