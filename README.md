# Familieblikk

Norsk familieøkonomi i NOK: inntekter, utgifter, månedsbudsjett, regninger og sparing, med valgfrie moduler for gjeld, årsutgifter og penger sendt utenlands. Hver familie har egne data og medlemsroller. Tilgjengelig beløp er et budsjettanslag; appen utfører ingen bankbetalinger. Lagring krever nett.

Repository: [Thugney/Familieblikk](https://github.com/Thugney/Familieblikk) (privat). Stabil gren: `main`; integrasjon: `develop`; funksjoner: `codex/`.

## Kjør lokalt

Bruk prosjektets `.venv` og Python 3.12 med avhengighetene i `requirements.lock`. Sett miljøvariablene fra `.env.example`, med en lokal PostgreSQL-database, `POSTGRES_HOST=127.0.0.1` og `DJANGO_DEBUG=1`. Kjør fra prosjektroten:

```powershell
.\scripts\start-local.ps1
```

Første bruker kan forhåndsregistreres lokalt og logge inn på `/passord/` uten SMTP. Den særskilt autoriserte eieren kan registrere egne familiemedlemmer og nye, adskilte familier med egen administrator. Dette gir ingen tilgang til de andre familienes budsjett. E-postadressene markeres ikke som verifiserte. SMTP må konfigureres dersom e-postkoder og e-postinvitasjoner tas i bruk. Konsoll-, fil- og minnebasert e-post er bare lokal testing; slike koder sendes ikke til innboksen.

## Docker på Synology

Se [førstegangs overføring til Synology](docs/SYNOLOGY.md) for å ta med den eksisterende private familien og passordkontoen, i tillegg til koden.

Hent godkjent kildekode til NAS-prosjektmappen og opprett en privat `.env` fra `.env.example`. Bruk ulike passord for databaseeier og approlle. Opprett prosjektet med `docker-compose.yml` i Container Manager, eller kjør:

```powershell
docker compose config --quiet
docker compose up --build -d
```

Migrasjonstjenesten klargjør databasen før webappen starter. Databasevolumet bevares ved containerbytte. Konfigurer HTTPS før NAS-bruk. SMTP er bare nødvendig hvis e-postkodene eller e-postinvitasjonene tas i bruk. Se [driftsveiledningen](docs/DRIFT.md) for miljø, GitHub-oppdateringer, roller, backup og gjenoppretting.

## Privat familieimport

Den faktiske arbeidsboken, importpakken, eieradressen og importkvitteringene ligger under gitignored `private-data/`. De skal aldri legges i repositoryet eller Docker-imaget. Autorisert import bruker separat skrivebeskyttet montering via `docker-compose.import.yml` og krever riktig administrator med dokumentert eierproveniens: eksplisitt forhåndsregistrert eier med autentisert passordøkt, eller faktisk verifisert e-postkode. Nye familier får ingen eksempelposter eller andre familiers data.

## Verifisert status

Lokalt er 57 Django/PostgreSQL-tester og 78 nettleserkontroller bestått. Separat backup/gjenoppretting har identiske radantall, og approllens forsøk på skjemaendring avvises. Service worker har en egen kjørbar Node-test i CI.

Den faktiske arbeidsboken er nå importert til den eksplisitt forhåndsregistrerte eierens egen familie i den lokale Docker-installasjonen. Alle 72 kilderader er bevart nøyaktig som poster eller synlige avklaringsutkast. Reimport, ny passordinnlogging etter containerutskifting, separat avstemt gjenoppretting og annen families tilgangsavslag er dokumentert privat. Ukjente datoer/klasser må fortsatt avklares før bokføring. Faktisk NAS-utrulling gjenstår. Passordinnlogging er ikke e-postverifisering.
