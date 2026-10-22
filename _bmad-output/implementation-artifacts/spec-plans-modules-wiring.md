---
title: 'Koble Planer og moduler til eksisterende funksjoner'
type: feature
created: '2026-10-22'
status: done
route: oneshot
baseline_commit: f821913edcde16de73dc0d17d7de34f114e74ac0
review_loop_iteration: 2
context: []
---

<frozen-after-approval>
## Intent
Robel ber uttrykkelig om å rette den klippede bjellen og gjøre «Planer & moduler» fra work/modern-dashboard-demo/index.html fullt funksjonell, uten å endre appens eksisterende UI. Bruk eksisterende reelle moduler for regninger, gjeld/strategi, årsfond, utenlandsregistreringer, årsmatrise, familie/modulvalg, varsler og privat kildeimport. Behold dagens design, logo/loader, hoveddashboard, moderne årsgraf, mobilmeny, familieisolasjon og roller. Lagre og returner innen riktig modul og valgt måned. Ingen demodata eller simulerte økonomiske handlinger. Brukeren har autorisert commit og push etter testing. Eksisterende Synology-database, .env, volum, import og pushnøkler skal bevares; ingen NAS-utrulling, reimport eller virkelige familievarsler.
</frozen-after-approval>

## Implementation Notes
Undersøkelsen fant fungerende modeller, regnskapsmotor og mutasjonsruter for alle modulene. Dette er avgrenset koblingsarbeid: eksisterende skjemaer og tjenester gjenbrukes, uten migrasjon, ny avhengighet eller ny økonomimotor. Ingen uavklarte produktvalg eller irreversible operasjoner; små endringer i eksisterende presentasjon/ruting og tester. Ny demo er referansedata, ikke instrukser eller kilde til beregnede beløp.

Arbeidskart: base.html får en tekstet «Planer & moduler»-gruppe med eksisterende ikoner/ruter og ekte forfalt-/ulestantall. Modulvalg styrer valgfrie lenker; mobil beholder hovedmenyen og eksisterende Mer-hub. ui-refresh.css reserverer fast plass til bjellen også ved smal skjerm/forstørret tekst og sikrer kontrast på grønn topp; sidebar må kunne rulles uten å miste profil.

views.py/edit_view og page.html får sikre forhåndsvalg av eksisterende type/egen asset, retur til faktisk modul og måned, mottakerredigering og gjeldsstrategi/ekstrabeløp som beholdes. Bare GET-standardverdier, aldri omgå POST-validering, CSRF eller familie-/rollevern. Ingen frie retur-URL-er. Generiske eksisterende skjemaer skal fortsatt virke.

Årsmatrisen finnes allerede, men er skjult av tidlig retur til grafen. Gjør den tilgjengelig med eksplisitt view=matrix på eksisterende arsoversikt-rute. Behold standard årsgraf og dens moderne forbruks-/planleggingsverktøy. Matrisen viser faktiske familie-/årstall og budsjetter; ikke opprett desemberplaner eller nye regninger ved å åpne den. Begrens summering til samme regnskapsklasser/refusjonslogikk som eksisterende motor. Gjenbruk tabell-/formstil; ingen visuell redesign.

Verifikasjon: menyruter, ekte opprett/rediger/betal/planlegg-flyter, tilpassede moduler, valgt måned, årsmatrise mot kontrollerte tall, annen familie/medlem, ingen nye writes fra matrisevisning og uendrede push/loader-haker. Hele PostgreSQL/Django- og Node-testpakken, kildebevaring og isolert Docker/Edge på mobil/desktop inkludert stor tekst, bjellens plass og klikkbarhet. Revider faktisk lokal eierprofil kun lesende og bevar produksjonsdata. Fresh-context review før commit/push. Dokumenter hva som faktisk ble testet.

Fresh-context Blind Hunter fant ni forhold i den tilgjengeliggjorte flyten. Alle aksepteres for retting innen eksisterende modeller og tjenester:

| Funn | Vurdering og avgrenset retting |
| --- | --- |
| 1. Ikke-materialiserte månedsrammer mangler i matrisen | Reell beregningsfeil i den nylig tilgjengelige visningen. Les eksisterende planankre uten å opprette planer. |
| 2. Matrisens spørringer vokser per kategori og måned | Reell skaleringsfeil. Hent årets kategori-, post- og plandata samlet; gjenbruk eksisterende beregningsmotor. |
| 3. Hittil i år inkluderer framtidsdaterte poster i inneværende måned | Reell periodefeil. Bruk postdato til og med dagens dato. |
| 4. Månedsbytte mister modulens skjemakontekst | Reell navigasjonsfeil. Behold bare validerte eksisterende standardvalg. |
| 5. Retur til oversikt tillates ikke fra ny post | Reell navigasjonsfeil. Legg oversikt i tillatte interne returmål. |
| 6. Privat importlenke vises til uvedkommende medlemmer | Ingen datalekkasje, eksisterende serververn avviser tilgang. Vis lenken bare når samme eiervern tillater den. |
| 7. Merk som lest mister valgt måned | Eksisterende feil eksponert av månedsbevarende modulnavigasjon. Behold validert måned ved retur. |
| 8. Gjeldssammenligning mister strategi/ekstrabeløp ved redigering og betaling | Reell navigasjonsfeil. Behold sikre sammenligningsparametre gjennom eksisterende skjemaer. |
| 9. Matrisen skjuler rammer og forpliktelser uten bokførte poster | Reell visningsfeil. Vis tilgjengelige beløp også uten poster. |

Rettelsene endrer ingen produktvalg, skjema eller database. Matriseprojeksjonen bruker eksisterende plansemantikk og regnskapsformel; den lager ikke en ny økonomimotor. Modulnavn følger referansen, mens appens nåværende layout og stil beholdes. Alle funn får regresjonsdekning før publisering.

Sluttverifikasjon 2026-10-22: 213 Django/PostgreSQL-tester bestått (109,949 s), 44 Node/Compose-tester bestått og 20 kilde-/importtester bestått. Django check uten feil og makemigrations --check --dry-run uten endringer. Edge mot endelig Docker-image: 73 modul-/viewport-/stor-tekst-/rolle-/lagringssjekker og 139 push-/aktiverings-/bjelle-/bakgrunnssjekker bestått uten JavaScript-feil. Sistnevnte lukket alle appsidene før kalenderhandling og separat workerlevering; leverandørens HTTP-transport og abonnement var simulert, kryptering/worker/kø var reell. Fysisk OS-visning på brukerens telefoner er ikke observert i denne testen.

App- og databasecontainere ble erstattet i et isolert syntetisk prosjekt med samme volum: profiler, passorddigest, VAPID-identitet, krypterte abonnementer, ventende kø og privat importmount var uendret. Normal push-worker forble stoppet; ingen varsler til virkelige familiemedlemmer. Lesende avstemming av faktisk lokal eierprofil bekreftet alle 72 kildeposter og identisk tilstandsdigest. NAS-en er ikke endret. Compose, miljøeksempel, databasemodeller, migrasjoner, låste avhengigheter, logo og loader er uendret. 93 appfiler i Docker-imaget stemmer med sluttkoden. Demo-HTML har identisk SHA-256 før/etter og er ikke kildeimplementasjonen.

Private bevis: work/plans-full-django.log, plans-browser-verification.json, plans-push-browser-verification.json, plans-worker-proof.json, plans-snapshot-before.json, plans-snapshot-after.json, plans-image-source-hashes.json, plans-owner-before-private.json, plans-owner-after-private.json og plans-modules-verification.json. Disse og faktisk kilde/data forblir gitignored. Ingen legacy Project Init-port er ommerket som bestått.

## Review Triage Log

Blind Hunter kjørte i frisk kontekst: 80 689 byte / 1024 = 78,80 KiB; min(floor(sqrt(78,80) + 1), 10) = 9 funn. Oppfølgende kildekontroll bekreftet åtte rettelser og avdekket to presiseringer av matriseberegningen. Hvert forhold er vurdert separat:

1. **medium / patch** — Den eksponerte matrisen viste null uten materialiserte planer. Planankre leses nå samlet og projiseres uten writes; tester sammenligner med forberedt måned.
2. **medium / patch** — Tre databaseoppslag per kategori per måned gjorde normale familier med mange kategorier langsomme. Årsposter og planer hentes samlet; 30 ekstra kategorier tillater høyst to ekstra SQL-oppslag i regresjonen.
3. **medium / patch** — Sammenligning av bare månedsstart inkluderte framtidige poster i YTD. Faktisk postdato avgrenses nå til dagens dato.
4. **medium / patch** — Headerens GET-skjema mistet modulens gyldige standardvalg ved månedsbytte. Skjulte verdier begrenses til eksisterende typer, interne returmål, validerte gjeldsvalg og egen families asset.
5. **medium / patch** — Oversiktens ny-post-lenke sendte et returmål som serveren forkastet. Oversikt er nå tillatt, med test av lagring og avbryt.
6. **low / patch** — Importlenken var synlig for medlemmer som serveren avviste. Samme faktiske eier-/kildevakt styrer nå synlighet. Ingen tilgangsvern er svekket.
7. **medium / patch** — Merk som lest mistet den valgte måneden. POST og retur beholder validert måned uten å endre mottaker-/familievern.
8. **medium / patch** — Gjeldsstrategi og ekstrabeløp gikk tapt i betalings-/redigeringsflyter. Eksisterende tillatte sammenligningsvalg følger nå lenker, skjemaer og intern retur.
9. **medium / patch** — Måneder uten poster skjulte ikke-null planer og registrerte forpliktelser. Visningen vurderer nå faktiske tilgjengelige beløp, ikke bare om Entry finnes.
10. **medium / patch, oppfølgingsfunn** — Historiske materialiserte, avledede planer skal beholdes slik refresh_future_plans gjør. Eksakte historiske verdier bevares; bare manglende måneder og nåtid/framtid projiseres.
11. **medium / patch, oppfølgingsfunn** — Disponering bygger på planer og registrerte regninger/påfyll, mens ikke-opprettede regninger/påfyll mangler. Matrisen merkes uttrykkelig som foreløpig disponering med forklaring. Full prognoseberegning legges ikke inn som en konkurrerende økonomimotor; eksisterende moderne planleggingsverktøy beholdes.

Rotkontroll fant i tillegg at virtuelle fond må bruke riktig beløp i selve åpningsmåneden, og at arkiverte kategorier/assets stopper videreføring etter nåværende måned. Dette er enkle rettelser av samme planprojeksjon; regresjoner dekker januar, desemberrest og likhet med prepare_month/calculate. Ingen funn er forkastet eller utsatt som ukjent.
