# Trinn 1 – regningsretting og historikk

Alle detaljer under er kandidat til aksept. Handlingsmenyen skiller «Rett denne regningen», «Endre fremtidig serie», «Avbryt feilført regning», «Angre feilregistrert betaling», «Registrer refusjon», «Historikk» og «Arkiver serie». Vis før/etter og økonomisk virkning før bekreftelse; aldri kall bankbetaling utført. Gjenoppretting finnes i historikk for handlinger bevart etter innføring.

## Tilstand og virkning

| Fra | Handling | Til | Effekt |
|---|---|---|---|
| Ubetalt | Rett beløp/navn/kategori/forfall | Ubetalt, ny versjon | Samme ID og serie-slot; reserve beregnes på nytt. |
| Ubetalt | Avbryt feilføring | Avbrutt | Reserven opphører; rad og begrunnelse beholdes. |
| Avbrutt | Gjenopprett | Ubetalt | Reserve gjeninnføres etter ny validering; konflikt gir ingen endring. |
| Ubetalt | Merk betalt | Betalt | Én aktiv betaling erstatter reserve; gjeld/fond følger riktig klasse. |
| Betalt | Angre feilregistrering | Ubetalt | Betalingspost reverseres som registreringsfeil, reserve kommer tilbake. |
| Ubetalt etter angre | Rett, deretter registrer betaling på nytt | Betalt | Ny bekreftelse lager én aktiv betaling; gammel hendelse bevares. |
| Betalt | Registrer faktisk refusjon | Betalt + refusjon | Original betaling beholdes; positiv refusjon på mottaksdato, ingen ny regningsreserve. |
| Aktiv serie | Arkiver fra dato | Stoppet fra dato | Ingen nye slotter fra og med dato; eksisterende reelle forpliktelser består. |
| Stoppet serie | Gjenoppta fra valgt dato | Aktiv fra dato | Ingen skjult ettergenerering av hoppede måneder; eksplisitt ny revisjon. |

Forfalt er en avledet visning av ubetalt + dato, ikke en egen økonomisk tilstand. Betalt forekomst kan ikke avbrytes/redigeres direkte. Har betalingen aktive refusjoner, blokker angre/retting med forklaring; ingen automatisk sletting av refusjoner. Registreringsfeil i refusjon må rettes eksplisitt med egen historikk før ny vurdering. Reell refusjon er aldri en sletting av betalingen.

## Identitet, serier og arkivering

Tilføy stabil recurrence_slot (opprinnelig planlagt måned for månedlig serie, fast slot for engangsregning) med unik template + slot. due_date blir redigerbar uten identitetsendring. Datomigrering må avdekke kollisjoner og stoppe med rapport fremfor å slette/forene eksisterende rader. Avbrutte forekomster beholdes som tombstones; materialisering ser også disse. En flytting fra oktober til november skal aldri opprette oktober på nytt eller erstatte november-slotten.

Serierevisjoner har uttrykkelig startdato, versjon og før/etter. Forhåndsvis nøyaktig hvilke fremtidige ubetalte forekomster som berøres; standard grense er etter i dag og fra valgt dato. Betalte, forfalte, avbrutte og individuelt rettede forekomster beholdes. Ikke flytt regnskapsklasse eller gjeld/fond-kobling på eksisterende serie; opprett ny serie ved slik endring. Ingen blanket delete/update som hopper over historikk eller versjon.

Arkivering stopper generering, ikke reservering av allerede reelle ubetalte forpliktelser. Vis disse med mulighet for separat eksplisitt avbrytelse av feilførte forekomster. Skjuling av modul er bare navigasjon og kan aldri arkivere/avbryte noe.

## Bevarte poster og transaksjoner

Kandidat: behold Entry med active/reversed-status og reversert-tid/aktør/hendelsesreferanse; behold occurrence som historisk FK og erstatt dagens OneToOne med unik aktiv betaling per occurrence. Bevar opprinnelig ID, sekvens, original/refund-koblinger og importreferanser. Alle beregninger, balanser, valideringer og pending_bills må bruke aktive poster eksplisitt; historikk viser begge. Kompatibel migrering setter eksisterende poster aktive uten endring av beløp/dato/kilde.

Gjenoppretting reaktiverer samme post først etter kontroll av gjeldende modultilgang, oppretter/admin, forventet objekt-/hendelsesversjon, gyldige relasjoner, refusjonsgrenser og senere saldoer. Gjenoppretting av betaling krever at forekomsten fortsatt er ubetalt, ikke avbrutt og uten nyere aktiv betaling; ellers konflikt. Gammel idempotensnøkkel gjenbrukes ikke til en ny økonomisk handling. Ingen tidligere hendelse overskrives.

Alle mutasjoner er atomiske: Household-lås → ferskt Membership → gjeldende relasjoner/objekter i stabil rekkefølge → policy → forventet versjon → validering → lagring/hendelse → fondsavstemming. Gjenbruk access.lock_member/lock_relations og services.authorize. Betaling beholder dagens regel om at tillatt medlem kan registrere betaling; angre krever betalingspostens oppretter/admin. Forekomstretting krever forekomstens oppretter/admin. Én sammensatt handling krever rett til alle berørte objekter.

En unik kommando lagrer household, actor, operation, idempotency_key, payload-hash og resultat-ID/versjon. Autorisasjon evalueres før replay. Identisk retry returnerer samme resultat uten ny audit/økonomi; samme nøkkel med annet innhold gir konflikt. Stale expected_version gir konflikt og bevarer brukerens utkast. Ingen optimistisk bekreftet saldo før serverkvittering; offline gir ingen lagring.

Append-only endringshendelse lagrer objekttype/ID, familie, aktør, UTC-tid, handling, begrunnelse, før/etter-felter, økonomisk dato, versjoner og koblet kommando/reversering. Ingen passord/nøkler/dokumentinnhold. Historikk autoriseres mot både nåværende objekt og relevante før/etter-koblinger; en eldre tillatelse gir ikke lesetilgang i dag. Fullstendig snapshot ved nye slettinger; eldre audit er merket begrenset og har ingen falsk gjenopprett-knapp.

## Regnskapsinvarianter

Én aktiv betaling per forekomst; avbrutt forekomst har null reserve og null aktiv betaling. Ordinær reserve erstattes av utgift; gjeld/fond følger dagens spesifikke regler og fondsavstemming, aldri ordinær utgift i tillegg. Angre/retting beregner alle berørte måneder og senere mål-/fondshendelser, med opprinnelige effektive datoer. Ingen negativ målbeholdning skapes av tilbakeført innskudd. Reelle refusjoner følger eksisterende maks originalbeløp og dato etter originalen. Arkivering/tilgang/skjuling endrer aldri økonomiske summer. Innføring av dette laget må kartlegge alle Entry-lesere før bygging slik at reverserte rader ikke telles i andre moduler.

## CSV og moduloppdagelse

Eksport åpnes fra regninger/poster med valgt fra–til, kategori og status. Regningsperiode betyr forfall; postperiode betyr økonomisk dato. Vis basis i eksportdialog og fil. Eksporter hele tillatte filterutvalg, ikke bare synlig pagineringsside; ingen skjulte rader, snapshots, dokumentstier eller familieinterne data uten rettighet. Serveren bygger utvalg med samme policy som skjermen, kontrollerer tillatelser på nytt og unngår offentlig cache. Kolonner: type, dato, beskrivelse, kategori, beløp NOK, status og tillatt koblings-ID. Norsk UTF-8 CSV med korrekt quoting; tekst som begynner med =,+,-,@, tab/retur nøytraliseres mot regnearkformler. Eksport endrer ingen data.

Modulsynlighet er bekreftet løst etter lagrede familievalg; bevar oppsettet og ikke bygg modulene på nytt. Videre kandidat: Mer/Tilpass viser eksisterende moduler med aktiv/skjult-status og kort funksjonsforklaring. Bare administrator aktiverer familievisning; egen medlemsadgang administreres separat. Begrenset medlem får forklaring om å kontakte administrator, uten skjulte økonomiske eksempler/tall. Aktivering lager ikke nye poster, planer eller importdata.
