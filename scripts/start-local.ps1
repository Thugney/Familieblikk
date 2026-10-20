param([switch]$Test)
$ErrorActionPreference = 'Stop'
if (-not $env:DJANGO_SECRET_KEY) { throw 'Sett DJANGO_SECRET_KEY i miljøet.' }
if (-not $env:POSTGRES_PASSWORD) { throw 'Sett POSTGRES_PASSWORD for lokal PostgreSQL.' }
$python = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
& $python manage.py check
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python manage.py migrate --noinput
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ($Test) { & $python manage.py test budget.tests --verbosity 2 } else { & $python manage.py runserver 127.0.0.1:8000 }
exit $LASTEXITCODE
