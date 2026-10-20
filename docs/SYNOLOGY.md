# Hent Familieblikk til Synology

Repository: `https://github.com/Thugney/Familieblikk` (privat). Bruk `main` til NAS, `develop` til integrasjon og `codex/` til endringer. Se også [drift](DRIFT.md).

## Kode og private familiedata flyttes separat

Git inneholder kode, migrasjoner og dokumentasjon. Det inneholder aldri databasebackup, arbeidsbok, importpakke, eierbinding, passord eller `.env`. En tom database får derfor ikke familiens data bare ved `git pull`.

For å videreføre den eksisterende familien anbefales gjenoppretting av den verifiserte private PostgreSQL-backupen. Da beholdes konto, passord, familie-ID, importutkast og bokførte poster. Flytt også `private-data/family-budget/` separat hvis kildevisning og avklaring skal være tilgjengelig på NAS. Denne mappen er allerede bundet til den importerte familien. Ikke kjør ny eierprovisionering mot en tom database med en binding som peker til den eksisterende familien.

## Første oppstart med eksisterende familie

1. Bekreft at NAS-en støtter Container Manager og de valgte Linux-imagene. Klon det private repoet til en egen prosjektmappe, og velg `main`.
2. Kopier `.env.example` til `.env` på NAS. Sett lange, ulike hemmeligheter, korrekt domene, HTTPS/proxy og ønsket port. E-post er valgfritt ved passordinnlogging. Bruk `POSTGRES_DB=familieblikk` og `POSTGRES_USER=familieblikk_owner` for kommandoene under, eller tilpass dem til egne verdier.
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

Start deretter prosjektet med begge Compose-filene i Container Manager, eller:

```text
docker compose -f docker-compose.yml -f docker-compose.import.yml up --build -d
```

Importmappen monteres skrivebeskyttet og bakes aldri inn i imaget. Behold monteringen så lenge familien trenger kildevisning eller avklaringsutkast. Uten den er vanlige bokførte data fortsatt i databasen, men kildeavklaringssiden er utilgjengelig.

6. Koble Synologys HTTPS-reversproxy til appens lokale port. Logg inn på `/passord/` med eksisterende konto. Kontroller september 2026 og kildeimporten, og ta en ny backup etter kontrollen. Startpassordet kan endres under Familie og innstillinger.

## Senere oppdateringer

Ta backup først. Hent godkjent kode med `git pull --ff-only origin main`, bygg og start med samme Compose-filer, prosjektnavn og databasevolum. Bruk aldri `down -v` for en oppdatering. Verifiser innlogging og data etterpå.

Denne veiledningen klargjør overføringen. Ingen faktisk NAS-utrulling eller gjenoppretting på NAS er utført fra denne chatten.
