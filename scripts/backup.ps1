param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $target) { throw 'Backupfilen finnes allerede. Velg et nytt filnavn.' }
$documentsTarget = "$target.documents.tar"
if (Test-Path -LiteralPath $documentsTarget) { throw 'Dokumentarkivet finnes allerede. Velg et nytt filnavn.' }
$container = docker compose ps -q db
if ($LASTEXITCODE -or -not $container) { throw 'Databasen kjører ikke.' }
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/familieblikk-backup.dump'
if ($LASTEXITCODE) { throw 'Databasedump feilet.' }
docker cp "${container}:/tmp/familieblikk-backup.dump" $target
if ($LASTEXITCODE) { throw 'Kopiering feilet.' }
Get-FileHash -LiteralPath $target -Algorithm SHA256
# Originaler er immutable og slettes aldri automatisk. Kopier etter DB-snapshot:
# alle filer referert i dumpen finnes fortsatt; eventuelle nyere filer er ufarlige.
$appContainer = docker compose ps -q app
if ($LASTEXITCODE -or -not $appContainer) { throw 'Appen må kjøre for sikkerhetskopiering av dokumentvolumet.' }
. (Join-Path $PSScriptRoot 'Copy-NativeOutput.ps1')
Copy-NativeOutputToFile -Executable 'docker' -NativeArguments @('compose', 'exec', '-T', 'app', 'tar', '-cf', '-', '-C', '/private-documents', '.') -DestinationPath $documentsTarget
Get-FileHash -LiteralPath $documentsTarget -Algorithm SHA256
