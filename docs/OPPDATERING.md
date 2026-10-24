# Hent rettelser på eksisterende Synology-prosjekt

Kjør i SSH-terminalen på NAS-en, fra samme prosjektmappe som allerede kjører Familieblikk. Kontoen må ha tilgang til Docker. Kommandoene nedenfor er for NAS-ens Linux-shell. De skal ikke kjøres i PowerShell på PC-en.

Denne oppdateringen endrer ingen Compose-filer, avhengigheter eller databasemigrasjoner. Den endrer heller ikke familiens feilregistrerte regninger automatisk. Eksisterende `.env`, importmontering, prosjektnavn og volumer skal beholdes.

Blokken forutsetter at eksisterende prosjekt bruker `docker-compose.yml` og `docker-compose.import.yml`, slik den overførte profilen er dokumentert i DRIFT.md. Den stopper dersom den ikke finner den kjørende databasen for dette prosjektet. Ikke fortsett med et nytt prosjekt eller en tom database.

```sh
(
set -eu
test -f .env
test -f docker-compose.yml
test -f docker-compose.import.yml
git diff --quiet
git diff --cached --quiet

nas_compose() {
  docker compose -f docker-compose.yml -f docker-compose.import.yml "$@"
}

nas_db=$(nas_compose ps -q db)
test -n "$nas_db"
nas_project=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$nas_db")
test -n "$nas_project"
nas_volume_before=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$nas_db")
test -n "$nas_volume_before"

umask 077
nas_backup="../familieblikk-backup-$(date +%Y%m%d-%H%M%S)"
mkdir "$nas_backup"
cp .env "$nas_backup/.env"
sha256sum .env > "$nas_backup/env.sha256"
printf '%s\n' "$nas_project" > "$nas_backup/compose-project.txt"
printf '%s\n' "$nas_volume_before" > "$nas_backup/database-volume.txt"
nas_compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$nas_backup/database.dump"
test -s "$nas_backup/database.dump"
docker exec -i "$nas_db" pg_restore --list < "$nas_backup/database.dump" > /dev/null

git fetch origin
git switch codex/entry-links-plain-language
git pull --ff-only origin codex/entry-links-plain-language
sha256sum -c "$nas_backup/env.sha256"

docker compose -p "$nas_project" -f docker-compose.yml -f docker-compose.import.yml config --quiet
docker compose -p "$nas_project" -f docker-compose.yml -f docker-compose.import.yml up -d --build

nas_db_after=$(docker compose -p "$nas_project" -f docker-compose.yml -f docker-compose.import.yml ps -q db)
test -n "$nas_db_after"
nas_volume_after=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$nas_db_after")
test "$nas_volume_before" = "$nas_volume_after"
sha256sum -c "$nas_backup/env.sha256"
docker compose -p "$nas_project" -f docker-compose.yml -f docker-compose.import.yml ps -a
docker compose -p "$nas_project" -f docker-compose.yml -f docker-compose.import.yml logs --tail=30 migrate app push-worker document-worker
printf 'Backup: %s\nDatabasevolum bevart: %s\n' "$nas_backup" "$nas_volume_after"
)
```

`migrate` skal avsluttes med kode 0. `db`, `app`, `push-worker` og `document-worker` skal kjøre. Logg inn igjen og kontroller samme budsjett, novemberinntekter og regninger. Bevar backupen privat; den inneholder database og hemmeligheter. Listen fra `pg_restore` kontrollerer arkivformatet, men erstatter ikke en full gjenopprettingstest.

Ved lokale Git-endringer eller feil i et steg stopper blokken. Bevar feilmeldingen og avklar før du går videre; ikke bruk reset, ny import eller restore for å få en vanlig oppdatering gjennom. Ikke kjør `down -v`, volumfjerning eller prune, og ikke erstatt `.env` med eksempelfilen.
