# Hent Familieblikk til Synology

Repository: `https://github.com/Thugney/Familieblikk` (privat). Bruk `main` til NAS, `develop` til integrasjon og `codex/` til endringer. Se også [drift](DRIFT.md).

## Kode og private familiedata flyttes separat

Git inneholder kode, migrasjoner og dokumentasjon. Det inneholder aldri databasebackup, arbeidsbok, importpakke, eierbinding, passord eller `.env`. En tom database får derfor ikke familiens data bare ved `git pull`.

For å videreføre den eksisterende familien anbefales gjenoppretting av den verifiserte private PostgreSQL-backupen. Da beholdes konto, passord, familie-ID, importutkast og bokførte poster. Flytt også `private-data/family-budget/` separat hvis kildevisning og avklaring skal være tilgjengelig på NAS. Denne mappen er allerede bundet til den importerte familien. Ikke kjør ny eierprovisionering mot en tom database med en binding som peker til den eksisterende familien.

## Første oppstart med eksisterende familie

1. Bekreft at NAS-en støtter Container Manager og de valgte Linux-imagene. Klon det private repoet til en egen prosjektmappe, og velg `main`.
2. Kopier `.env.example` til `.env` på NAS. Sett lange, ulike hemmeligheter. Domenet er allerede satt til `blikk.betilab.com` for den eksisterende Cloudflare-tunnelen; ved eldre `.env` må verdiene i avsnittet under oppdateres. Hosting bruker alltid **host-nettverk** og webport **6451**, uten portmapping; sørg for at denne porten er ledig. `APP_PORT`/`APP_BIND` fra et eldre oppsett brukes ikke. Databasen lytter kun på `127.0.0.1:6452` som standard; sett `POSTGRES_PORT` til en annen ledig databaseport ved behov. Behold `docker/postgres/pg_hba.conf` fra repositoryet, som er montert skrivebeskyttet og krever passord også for localhost. E-post er valgfritt ved passordinnlogging. Bruk `POSTGRES_DB=familieblikk` og `POSTGRES_USER=familieblikk_owner` for kommandoene under, eller tilpass dem til egne verdier.
3. Overfør den private backupen og `family-budget/` til en separat, tilgangsbegrenset mappe på NAS. Behold egne backupkopier utenfor NAS.
4. Start bare databasetjenesten i det nye prosjektet. Gjenopprett bare til en ny, tom database; ikke overskriv en eksisterende installasjon.

```text
docker compose up -d db
docker compose ps
docker compose ps -q db
```

Når databasen er frisk, bruk den viste container-ID-en i kopieringskommandoen. Eksempelstien må erstattes med din faktiske private NAS-sti:

```text
docker cp /volume1/docker/familieblikk-private/owner.dump CONTAINER_ID:/tmp/owner.dump
docker compose exec -T db pg_restore --no-owner --no-privileges --exit-on-error --username familieblikk_owner --dbname familieblikk /tmp/owner.dump
```

`--no-owner --no-privileges` gjør at NAS-ens databaseeier får de gjenopprettede objektene. Migrasjonstjenesten oppretter separat, begrenset approlle og gir nødvendige rettigheter etterpå.

5. For kildevisning og avklaring, legg denne ekstra verdien i NAS-ens private `.env`, med din faktiske sti:

```text
PRIVATE_IMPORT_PATH=/volume1/docker/familieblikk-private/family-budget
```

Før webappen startes: begrens direkte innkommende TCP til port **6451** i NAS-brannmuren, og la den lokale tunnelkoblingen nå appen. Appen deler NAS-ens nettverk; den tidligere loopback-portmappingen er ikke lenger tilgangsgrense. Ingen ruterport skal åpnes for tunnelen.

Start deretter prosjektet med begge Compose-filene i Container Manager, eller:

```text
docker compose -f docker-compose.yml -f docker-compose.import.yml up --build -d
```

Importmappen monteres skrivebeskyttet og bakes aldri inn i imaget. Behold monteringen så lenge familien trenger kildevisning eller avklaringsutkast. Uten den er vanlige bokførte data fortsatt i databasen, men kildeavklaringssiden er utilgjengelig.

6. Bruk den eksisterende Cloudflare-tunnelen med offentlig vertsnavn **blikk.betilab.com** og tjeneste **HTTP / 192.168.20.135 / 6451**. Ingen ekstra Synology-reversproxy eller lokale TLS-sertifikater kreves. NAS-adressen `192.168.20.135` er bekreftet av Robel. La tunnelkoblingen nå denne adressen på port 6451. Appens database bruker fortsatt bare localhost. Behold HTTP og port 6451. Dersom tunnelen overstyrer HTTP Host Header, sett den til `blikk.betilab.com`.

NAS-ens private `.env` skal ha følgende ikke-hemmelige verdier (behold øvrige hemmeligheter):

```text
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=blikk.betilab.com
CSRF_TRUSTED_ORIGINS=https://blikk.betilab.com
DJANGO_TRUST_PROXY=1
DJANGO_HTTPS=0
```

Cloudflare leverer HTTPS ut mot brukeren. Appen leser bare tunnelens HTTPS-header for innlogging, CSRF og sikre cookies; origin-forbindelsen er vanlig HTTP. Se [Cloudflares headerdokumentasjon](https://developers.cloudflare.com/fundamentals/reference/http-headers/#x-forwarded-proto). La den eksisterende tunnelen håndheve HTTPS på det offentlige domenet.

App, migrering og database skal alle vise host-nettverk i Container Manager. Logg inn på `https://blikk.betilab.com/passord/` med eksisterende konto. Kontroller september 2026, kalenderen og kildeimporten, og ta en ny backup etter kontrollen. Startpassordet kan endres under Familie og innstillinger.

Kontroller fra en annen maskin at HTTPS-adressen fungerer, mens direkte HTTP til `NAS-IP:6451` er blokkert. Tillat den nødvendige origin-trafikken fra tunnelkoblingen til `192.168.20.135:6451`, men blokker øvrig direkte trafikk til webporten. Denne kontrollen må gjøres på den faktiske NAS-en.

## Oppgradering av et eksisterende databasevolum

Før det nye host-oppsettet erstatter en kjørende eldre installasjon, ta backup og følg [SCRAM-forhåndskontrollen i driftsveiledningen](DRIFT.md#eksisterende-databasevolum-og-passordformat). Gjenoppretting til en ny PostgreSQL 17-installasjon bruker nye SCRAM-passord fra NAS-ens `.env`; gjenbruk av et eldre volum kan kreve konvertering først. Volumet skal ikke slettes for å endre passordformat.

## Senere oppdateringer

Ta backup først. Hent godkjent kode med `git pull --ff-only origin main`, bygg og start med samme Compose-filer, prosjektnavn og databasevolum. Bruk aldri `down -v` for en oppdatering. Verifiser innlogging og data etterpå.

Denne veiledningen klargjør overføringen. Ingen faktisk NAS-utrulling eller gjenoppretting på NAS er utført fra denne chatten.
