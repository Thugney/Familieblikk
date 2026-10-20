param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $target) { throw 'Backupfilen finnes allerede. Velg et nytt filnavn.' }
$container = docker compose ps -q db
if ($LASTEXITCODE -or -not $container) { throw 'Databasen kjører ikke.' }
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/familieblikk-backup.dump'
if ($LASTEXITCODE) { throw 'Databasedump feilet.' }
docker cp "${container}:/tmp/familieblikk-backup.dump" $target
if ($LASTEXITCODE) { throw 'Kopiering feilet.' }
Get-FileHash -LiteralPath $target -Algorithm SHA256
