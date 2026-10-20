# Lokal verifikasjon — 20. oktober 2026

Familieblikk er bygget og kjører lokalt i Docker på `http://127.0.0.1:4180`. Installasjonen har nå den faktiske eierens passordkonto og private familie med Excel-import, i tillegg til separate syntetiske testfamilier. Filbasert e-post brukes bare av testflyten. SMTP er ikke nødvendig for forhåndsregistrerte kontoer; ekte e-postlevering og NAS-utrulling er ikke verifisert.

| Kontroll | Observert resultat |
|---|---|
| Django/PostgreSQL | 57 tester bestått; systemkontroll uten feil; ingen manglende migrasjoner |
| Avhengigheter | Hashlåste pakker; kompatibilitetskontroll bestått i prosjektets `.venv` |
| Service worker | Kjørbar Node-test bestått for offentlig cache, utskifting og frakoblet side |
| Privat kilde og forhåndsvisning | 20 bevarings-/tilgangstester bestått med eksisterende regnearkruntime |
| Nettleser | 78 kontroller bestått: 13 sider ved fem bredder, ekte registreringer, utlogging, cachegrenser og installérbarhet |
| Visuell kontroll | Skjermbilder av faktisk app kontrollert på mobil/PC; sammenhengende flate, tre støttemål, tremånedersdiagram, bunntekst og bare venstre-nedre desktopprofil |
| Docker | Image bygget; migrasjon 0001–0008 kjørt; app og PostgreSQL startet |
| Minste databaseprivilegier | Approllen er ikke administrator og CREATE TABLE avvises |
| Imagegrenser | Kjører som vanlig bruker; `.env`, `private-data/` og `work/` finnes ikke i imaget |
| Gjenoppretting | Dump gjenopprettet i ny separat database; radantall og beløpssummer identiske |
| Containerutskifting | Ny passordinnlogging etter utskifting av app/DB bevarte faktisk eierfamilies importerte rader og summer; tidligere OTP-testfamilie er også kontrollert |
| Uavhengig gjennomgang | Reelle funn reparert og kontrollert på nytt; ett opprinnelig funn avkreftet mot eksisterende kode |

Lokale kjøringskvitteringer, gjennomgangsfunn og skjermbilder ligger i gitignored `work/`. Rådata, eierbinding og arbeidsbok ligger bare i gitignored `private-data/`. CI er skrevet, men er ennå ikke kjørt på GitHub.

## Faktisk eierimport

Brukeren godkjente eksplisitt forhåndsregistrering med passord i stedet for e-postkode, og administrativ registrering av medlemmer/andre familier. Eieren er opprettet med separat registreringsproveniens og registratortillatelse; e-postadressen er ikke feilaktig merket verifisert.

Alle 72 kilderader (inkludert innstillinger) finnes i bare eierens familie. Hver råverdi er sammenlignet med importpakken, alle bokførte transaksjoner med kildens beløp/dato/klasse, og alle målkoblinger med riktig familie. Ufullstendige eller tvetydige data er synlige utkast. Kildens september 2026 er bevart. Reimport endrer ikke identitet/radantall, og ny innlogging etter utskifting av begge containere gir samme tilstandsdigest. Separat gjenoppretting har identiske eierdata og passordidentitet. En annen autentisert familie ble nektet lesing av faktisk post, importutkast, privat kilde og ny import. Utlogging ugyldiggjorde gammel sesjon.

Private kvitteringer og faktiske skjermbilder ligger i `private-data/runtime/owner-verification/`. Startpassord ligger bare i `private-data/runtime/owner-access.json` og kan endres inne i appen. Ingen passord eller kildeverdier er publisert i denne rapporten.

## Før ekstern lansering

NAS-modell/arkitektur, Container Manager og HTTPS må konfigureres og verifiseres ved utrulling. SMTP er valgfritt for kode/invitasjoner. Privat GitHub-repository er opprettet, og første commit/push er eksplisitt autorisert av brukeren. Ingen faktisk NAS-utrulling er utført. Avklaringsutkast må gjennomgås av familien før de brukes som bokførte beløp; bevaring som utkast er ikke en bekreftelse på korrekt regnskapsklasse eller manglende dato.

Innloggingssiden bruker nå den godkjente demoens fire grønne fliser. Logo, skjemabredder og fravær av horisontal overflyt er kontrollert ved 360, 390, 768, 1024 og 1440 px. Passordinnlogging og faktiske kildeposter er kontrollert igjen etter Docker-rebuild.


## GitHub-status ved første publisering

Privat repository og grenene `main`, `develop` og `codex/build-familieblikk` er opprettet og pushet. `main` er standardgren. CI kan startes ved push, pull request eller manuelt.

Den første manuelle [CI-kjøringen](https://github.com/Thugney/Familieblikk/actions/runs/39489965135) ble stoppet før noen teststeg startet. GitHub oppgir at nylige kontobetalinger har feilet eller at forbruksgrensen må økes. Dette er en kontoblokkering; GitHub-testene er derfor ikke bekreftet grønne. Lokalt består 57 PostgreSQL/Django-tester, og innlogging/logo er kontrollert på fem bredder.

GitHubs grenbeskyttelses-API oppgir at private repoer på denne kontoen krever GitHub Pro. Grenbeskyttelse er derfor ikke aktivert. Repoet forblir privat. Ingen betalingsinnstillinger eller abonnement er endret.
