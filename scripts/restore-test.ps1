param([Parameter(Mandatory=$true)][string]$BackupFile)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $BackupFile).Path
$container = docker compose ps -q db
if ($LASTEXITCODE -or -not $container) { throw 'Databasen kjører ikke.' }
# En separat, ny database. Eksisterende familiedata overskrives aldri.
$restoreDatabase = 'restorecheck_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
docker cp $source "${container}:/tmp/restorecheck.dump"
if ($LASTEXITCODE) { throw 'Kopiering feilet.' }
docker compose exec -T db sh -c "createdb -U `"`$POSTGRES_USER`" $restoreDatabase"
if ($LASTEXITCODE) { throw 'Kunne ikke opprette separat gjenopprettingsdatabase.' }
docker compose exec -T db sh -c "pg_restore -U `"`$POSTGRES_USER`" -d $restoreDatabase --exit-on-error /tmp/restorecheck.dump"
if ($LASTEXITCODE) { throw 'Gjenoppretting feilet.' }
Write-Output "Gjenopprettet i separat database $restoreDatabase. Avstem radantall og summer før eventuell produksjonsgjenoppretting."
