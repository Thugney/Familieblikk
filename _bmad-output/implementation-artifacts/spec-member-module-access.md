---
title: 'Modultilgang per familiemedlem'
type: feature
created: '2026-10-22'
status: done
route: dispatch
baseline_commit: e00b367b9cbc9ac938a7d4d296a03c6eae5b8e6b
review_loop_iteration: 2
context: []
---

<frozen-after-approval>
## Intent
Administrator velger hvilke moduler hvert vanlig medlem i egen familie kan bruke. Valgene lagres på medlemmet og håndheves på serveren, i menyene og på andre sider som ellers ville vist moduldata. Brukeren har bestilt implementasjon, test, commit og push. Dagens UI, logo, loader, kalender og fungerende push bevares.

## Boundaries & Constraints
All eksisterende tilgang beholdes ved oppdatering. Administratorer har alltid full familietilgang; rolleendring inngår ikke. Vanlige medlemmer beholder egne-poster-regelen innen tillatte moduler. Familieisolasjon og eksplisitt eiervern for privat import kan aldri overstyres av modulvalg. Valg per medlem er adskilt fra familiens eksisterende visningspreferanser.

Moduler: budsjett/poster, regninger, sparing, gjeld/strategi, årsfond, utenlandsregistreringer, årsoversikt og kalender. Konto/passord, utlogging og en trygg startside er alltid tilgjengelige. Varslingsinnhold og push følger kalendertilgang; avregistrering av egen enhet er fortsatt mulig. Nye medlemmer starter med dagens tilgang til administrator endrer den.

Robel godkjente 2026-10-22: «Godkjenn og bygg med skjulte opplysninger og summer (anbefalt)». Sperrede moduler skjuler også opplysninger og summer som røper dem. Full disponering, komplett planlegging og årsmatrise krever alle nødvendige økonomimoduler. Tillatte utgiftsvisninger filtreres og merkes som utvalg; trygg startside viser tillatte funksjoner. Familienes autoritative regnskap endres ikke av visningstilgang.

Bevar autoritative regnskapsberegninger, forpliktelser, import, poster og historikk. Ingen nye avhengigheter, datagjenoppretting, import/seed eller NAS-utrulling. Bare additive, kompatible medlemsfelt. Eksisterende .env, DB-navn, Compose-prosjekt, volum, privat importmontering og nøkler skal bestå vanlig pull/build.

## I/O & Edge-Case Matrix
| Tilstand/handling | Forventet resultat | Feil |
| --- | --- | --- |
| Egen admin lagrer medlemsvalg | Persistens og tydelig bekreftelse; ny forespørsel bruker nye valg | Versjonskonflikt viser nyeste valg uten overskriving |
| Vanlig medlem eller fremmed families ID endrer valg | Ingen endring | 403/404 uten fremmede opplysninger |
| Skjult modul via gammel fane, URL, JSON, skjema eller refusjon | Ingen lesing eller mutasjon av sperret modul | 403 og forståelig begrunnelse |
| Kalender trekkes tilbake med ventende push | Nye svar/oppslag/varsler og kølevering sperres | Historiske avtaler, svar og abonnement bevares |
| Administrator eller urørt gammelt medlem | Dagens moduler og redigeringsregler virker | Ingen ny innlogging kreves |
</frozen-after-approval>

## Code Map
- `budget/models.py:Membership`, `budget/migrations/`: additive JSON-rettigheter og versjon, tomt standardvalg betyr dagens tilgang. Eksisterende økonomiske tabeller urørt.
- Ny `budget/access.py`: én policy for medlemskap, moduler, sider, rader, relasjoner og sikre spørringsutvalg. Ukjente nøkler avvises. Les ferskt medlemskap ved mutasjoner.
- `budget/views.py`, `forms.py`, `services.py`: tidlige sidevakter, lagre/angre/betale, skjemavalg og både gammel/ny radtype. Refusjon arver originalens modul; bill/plan bruker regnskapsklasse/asset. Eksisterende eier-/rollevern består.
- `budget/spending_views.py`, `spending_services.py`: sikre utvalg i søk, kategori/år, inntekt, dekning og postlenker. Full plan kan ikke delvis lagres eller lekke skjulte data.
- `budget/calendar_*`, `push_*`: listing, API, personvalg, deltakerkontroll, varsler, idempotens og faktisk kølevering kontrollerer gjeldende tilgang. Historiske payloads beholdes.
- `budget/templates/budget/`, `templatetags/`: eksisterende nav-/panelstil; medlemsrad får «Modultilgang», native avkryssinger og lagring. Meny/badges/hurtiglenker følger samme policy.

## Tasks & Acceptance
**Execution:**
- [x] Modell/migrasjon/access-policy og testet klassifisering.
- [x] Admin-endepunkt/skjema på familiesiden, familieavgrenset og atomisk med versjonskontroll/audit.
- [x] Alle HTML/JSON/skriveoperasjoner og relasjonsvalg bruker policy før lesing, lagring eller idempotent svar.
- [x] Kalender/push og navigasjon følger tilbakekalling uten å endre historiske familiedata.
- [x] Regresjon, migreringsbevaring, Docker/nettleser og uavhengig sikkerhetsgjennomgang. Autorisert publisering følger feature → develop → main; faktisk resultat bekreftes fra eksterne refs.

**Acceptance Criteria:**
- Gitt egen administrator, når et medlems modul velges bort og siden lastes på nytt, så er valget lagret og modulen utilgjengelig i gammel medlemsøkt.
- Gitt sperret modul, når et medlem manipulerer URL, type, originalpost, asset eller betalings-ID, så leses/endres ingen sperrede data, og ingen annen familie berøres.
- Gitt kalender nektet, når ny avtale/svar eller ventende kø behandles, så mottar medlemmet ikke kalenderinnhold eller push; øvrige medlemmer fungerer som før.
- Gitt eksisterende database, når kompatibel migrering og containerbytte skjer, så er familiedata, innlogging, import, nøkler og kø bevart, med dagens tilgang som standard.
- Gitt mobil/PC, når admin redigerer tilgang, så virker tastatur/berøring og dagens layout/typografi uten horisontal overflow.

## Implementation Notes
Utførelsesansvar: én implementasjonsagent eier alle nødvendige app-, migrasjons- og regresjonstestfiler i Code Map samt produsentbevis i work/member-access-producer.json. Orkestrator eier runtimeharnesser, uavhengig verifikasjon og publisering. Du er ikke alene i kodebasen; bevar andres endringer og tilpass deg dem. Den native BMAD-workflowen er allerede rendret og håndteres av orkestrator; implementer denne spesifikasjonen uten å starte workflowen på nytt. Ingen commit/push fra implementasjonsagenten.

Kjør app/testkode bare i .venv eller Docker. Isolert PostgreSQL-testmiljø finnes via work/run-test-python.ps1 og work/test-runtime.env (skriv aldri miljøverdier i output). Målrettede tester kan kjøres av produsent; rapporter når runner er ledig slik at orkestrators fulle suite ikke kolliderer. Ikke endre .env, private-data, faktisk eierapp på 4180 eller NAS. Ingen testvarsler til ekte familiemedlemmer. Eksisterende syntetisk Docker-oppsett under work/compose-plans-verify.yml og work/background-browser-fixture.json eies av orkestrator. Produsent skal ikke endre disse.

Undersøkelse: ingen eksisterende medlemsrettigheter; Household.modules er kun visningspreferanser. Generiske poster, refusjoner, dashboard, planlegging og push krever felles håndheving. Omfanget krysser sikkerhetsgrenser og krever additiv migrasjon, derfor dispatch. Eksisterende UI beholdes; bare nødvendige avkryssinger og begrenset-tilgangstilstander legges til. Ingen ny økonomimotor.

Uavhengig plankontroll avklarte tre tekniske krav: Regninger/tilknyttede betalinger krever regningstilgang samt gjeld/fond når relevant; frittstående poster/planer følger egen regnskapsmodul og refusjoner arver originalens krav. Test blandede tillatelser. Tilgangslagring og mutasjoner må bruke felles låserekkefølge med fersk kontroll under lås. Push må serialisere siste tilgangskontroll/utsending mot tilbakekalling; leverandøraksepterte varsler kan ikke tilbakekalles. Test samtidighet og idempotens. Audit bruker eksisterende household-UUID som objekt og lagrer heltalls medlems-ID samt før/etter-rettigheter i changes; eksisterende UUID-felt endres ikke.


### Reviewstyrt presisering for ny utledning (iterasjon 1)
- Autoriserte leseutvalg må være sikre også når en rad omklassifiseres mellom opprettelse og evaluering av queryset. Bruk databasepredikater som følger gjeldende rad og relasjoner i selve spørringen; ingen PK-liste godkjent av en tidligere Python-enumerering. Dette fjerner også N+1/ubegrenset enumerering ved skjema/paginering. Bevar klassifiseringen for frittstående/koblet regning/refusjon og tenant-grensene; ingen endring i regnskapsmotoren.
- save_entry/save_row skal kontrollere oppdaterte asset/original/occurrence/category-relasjoner under household-låsen. Kast ikke låste ferske relasjoner til fordel for tidligere skjemacache. Demonstrer omklassifisert original mellom formvalidering og lagring samt queryset opprettet før omklassifisering, evaluert etter.
- Skjemakategorier uten budsjettinnsyn må begrenses til kategorier på tillatte poster/regninger; medlem med bare sparing får ingen uvedkommende kategorinavn. Bruk samme filtrering på utenlandsfilter. Legg til eksplisitte regresjoner.
- Redigering av eksisterende valgt kalenderavtale skal bevare allerede tilknyttede, nå sperrede deltakere og historiske svar selv om de ikke lenger er valgbare. Nye sperrede deltakere avvises fortsatt, og de får aldri nye varsler/innhold. Test server og reell skjemaredigering; behold synlige deltakerendringers eksisterende svarregler.
- Merk begrenset regningsliste som utvalg. Forklar kort på adminskjemaet at årsoversikt krever budsjett, og gjelds-/fondsregninger krever begge moduler. Bevar UI.
- Suppler Node-harness med tillatelsesflagg, fokus og keydown; verifiser End/Home/Arrow bare gjennom synlige faner. Test to samtidige administratorlagringer av samme versjon: én suksess, én konflikt, ett audit.

KEEP: Bevar alle åtte moduler, tom legacy-default, admin-bypass, eksisterende eierskap/tenantvern, additive migrasjon 0013, audit-UUID, versjonskonflikt, HH-låsrekkefølge, køstopp ved kalendernekt, tillatt avregistrering av egen enhet, trygg startside, merkede og filtrerte utvalg, undertrykte fonds-/gjeldssummer uten regninger, bills-only lagre/angre/refusjon og tilgjengelig retur, godkjent UI/logo/loader, privat DB/Compose/nøkler. Hele forrige apputledning er bevart som en lokal gjenopprettbar diff: den private gjenopprettingspakken dokumentert i work/member-access-recovery-proof.json. Les denne for positiv bevaring og utled korrigert kode fra denne spesifikasjonen. Ingen installasjon, commit/push eller annen testkjøring enn målrettede tester. Orkestrator kjører full verifikasjon etter retur. Lever work/member-access-producer.json med endrede filhash og testresultater.

## Spec Change Log
- Iterasjon 2: FB1/FE1 viste saldo-orakel i fundoskriving; FB2 gammel aksept ved ny dato; FB3 manglende navigerbar tillatt historikk; FB4 ignorerte familiepreferanser. Presisert skriveavhengighet, historikk i eksisterende liste, korrekte kalenderreset-regler og hjemmesidens synlighet. KEEP over bevarer vellykket 245-testers basis, SQL/ferske relasjoner og verifiserte data-/UI-kontrakter.
- Iterasjon 1: E2/B4 viste at materialisert PK-tillatelse ikke var atomisk ved senere evaluering; E1 viste foreldet originalcache. Presiserte SQL-utvalg og ferske relasjoner. B1/B3 presiserte kategorivalg og historiske kalenderdeltakere. Kjent dårlig tilstand: omklassifisert rad/refusjon kunne røpe sperret modul, gammel valgt avtale kunne ikke redigeres uendret. KEEP over bevarer alle fungerende flater og datakontrakter.

## Review Triage Log

| RB1 kategorier uten utvalgsmerking | medium | patch | page.html kategorier inkluderer filtrerte beløp uten varsel. Gjenbruk eksisterende restricted_selection-notice. |
| RB2 bills-only typefilter | low | patch | Vanlig koblet betaling er synlig, men kind=expense filtreres bort av budget-regelen. Tillat typen kun innen allerede avgrenset regningshistorikk. |
| RB3 remittance-only uten kategorier | medium | patch | category_choices gir tomt sett før første tillatte post. Eksisterende privacy-policy beholdes; forklar faktisk admin-klargjøring/tilgang i dagens skjema, uten oppdiktede poster. |
| RB4 skjulte gamle kalenderdeltakere | low | patch | Redigering beholder sperret tidligere deltaker uten synlig avkryssing. Direkte hjelpetekst skal forklare dette og fortsatt varslingssperre. |
| RB5 lås ved treg pushtjeneste | false | avvist | Dette er den godkjente serialiseringen mot tilbakekalling, ikke en utilsiktet manglende lås. transport har timeout=10; test_transport_holds_household_lock_until_provider_acceptance bruker styrt treg sender og demonstrerer ventende admin med 0,2s kontroll og 8s testgrense. Det beviser ikke høy trafikk, men omfanget er familier og nødvendig garanti prioriteres. |
| RB6 motsatt leveringsrekkefølge | low | patch | Testgap i motsatt kontendert rekkefølge: tidligere tester dekket claimed→revoke sekvensielt og send-først samtidig. Avgrenset worker-venter/revoke-først-regresjon legges til. |
| RB7 betaling/refusjon i konkurranse | low | patch | Generisk inntektsmutasjon og sekvensiell idempotens dekker grunnpolicy, men egen kontendert betalingsvei gir målrettet vern mot framtidig avvik fra fersk HH-kontroll. |
| RB8 metadata/future med exception | low | patch | Ny materiell future-test og eksisterende unrestricted metadata/exception-tester dekker deler, men kombinasjon med nektet deltaker mangler. Avgrenset sammensatt regresjon. |
| RB9 åpen pushside mister tilgang | low | patch | requestJson/catch bevarer deaktivér og gir reload-feil, men eksplisitt 403/ikke-JSON etter aktiv start mangler i Node-harness. Test eksisterende atferd, ingen ny pushflyt. |
| RB10 foreldet/ugyldig historikkfilter | low | patch | entry_filters viser field.errors og resetlenke allerede; et eksplisitt modultilbakekallingsfilterforløp legges til sammen med RB2 for å bevare dette. |
| RG1 tilbakekalt avtaleoppretter ved svar | medium | patch | Preverifisert testgap: creator legges eksplisitt til før siste access-guard. Selve guard er korrekt, men bookings-only test ville ikke oppdaget at den ble fjernet. Ny test sjekker både varsler og leveringskø for yes/no. |
| RE — edge-case-review | — | ingen | Fersk edge-case-linse returnerte tom funnliste etter kilde- og kravsporing. |


| FB1 nøyaktig fondsgap | high | bad_spec | save_entry regner fund_balance med sperrede regningsdata og røper eksakt gap. Også binært suksess-/feilorakel krever skriverelatert bills-forutsetning. |
| FB2 gammel aksept ved ny dato | medium | bad_spec | one-reset ekskluderer sperret medlem; etter gjenåpning viser listing gammelt ja på ny tid. Bevar metadata/splittet historikk, følg eksisterende vesentlig-endring-reset. |
| FB3 navigerbar posthistorikk | medium | bad_spec | Poster krever budget, mens sparing/gjeld/fond/regninger tilbyr registrering uten egen tillatt historikkliste. Direkte URL virker, men egen redigering/angre er utilgjengelig gjennom UI. |
| FB4 familiens visningsvalg | low | patch | available_pages bruker alle PAGES uten Household.modules. Skjulte gjeld/fond/utland/årsoversikt dukker opp på ny startside. Samme eksisterende synlighetsfilter skal brukes. |
| FB5 avregistrering når OS avslår | medium | defer | Notification.permission==denied avbryter før subscription-oppdagelse også i baseline e00b367, altså eksisterende UI-begrensning. Utlogging kaller disable_session og er fortsatt tilgjengelig; kalendernekt stopper i tillegg all kølevering. Eget forbedringsarbeid for serverbinding uten endpoint. |
| FB6 avhengige avkryssinger | false | avvist | Skjemaet forklarer konkret budsjett+årsoversikt og regninger+gjeld/fond. Lagret årsvalg blir effektivt når budsjett gis; ingen feiltilgang gis. Dynamisk ekstra UI er valgfri utvidelse. |
| FB7 tilgangen oppsummert på medlemsrad | low | avvist | Ekstra oversikt ville spare et klikk, men ingen funksjonsfeil. Krever nye sammendragstilstander/visning utover direkte tekstretting; dagens UI skal bevares. |
| FB8 standard 403 uten hjemlenke | false | avvist | familieblikk.urls handler403 peker til forbidden_view; budget/error.html har eksisterende Til oversikten-lenke til /, som ruter trygg startside. |
| FB9 uavhengige klassifiseringstilfeller | false | avvist | Matrisen er en ekstra samsvarstest. Eksisterende test_budget_denial_does_not_block_savings_or_ordinary_bill, mixed grants og refund/URL/mutasjonstester har uavhengige bokstavelige 200/403- og radforventninger. |
| FB10 varig migrasjonstest | low | avvist | Faktisk migrasjon er verifisert på 28 befolkede tabeller/114 rader, identiske eksisterende kolonner, og containerbevaring. Forslaget er ekstra framtidig testinfrastruktur, ikke påvist migrasjonsfeil; kompleks ny runner for en eksisterende immutable migrasjon utsettes ikke som produktkrav. |
| FE1 fundoskriving røper sperret saldo | high | bad_spec | Samme konkrete årsak som FB1: åpning 100000, skjult regningsbetaling 21300, forsøkt 100000 gir eksakt gap 213,00 NOK. |
| FG1 future-serie og sperret svar | medium | patch | Preverifisert testgap: ny test traff bare none/one, ikke recurring/future. Iterasjon 2 tester gammel historikk og nytt/berørt svar eksplisitt. |


| ID | Dom | Rute | Verifisert grunnlag |
| --- | --- | --- | --- |
| B1 kategorivalg | high | bad_spec | restrict_form utelater Category; EntryForm gir alle husets kategorier også ved bare sparing. Kategorinavn er opplysninger fra nektet budsjett. |
| B2 egendefinert årsperiode | false | avvist | Annual er egen rapport/modul. Tillatt budsjett beholder periodefilter og tillatte postdata; egendefinert intervall røper ikke nektede økonomimoduler og gir ikke tilgang til årsmatrise/planlegging. |
| B3 tidligere kalenderdeltaker | medium | bad_spec | validate_payload avviser bevart sperret ID ved redigering; editor har ikke lenger avkryssing for vedkommende. Eksisterende avtale/svar skal bevares ved vanlig redigering. |
| B4 Python-enumerering | medium | bad_spec | safe_rows går over hele originalhistorikken og henter relasjoner før ny queryset. Samme utvalgsdesign som E2 gir ekstra skanning og N+1. SQL-utvalg løser kjent årsak. |
| B5 fast-path tenantrelasjoner | false | avvist | Reell app lagrer alle økonomiske relasjoner gjennom FamilyRow.clean/full_clean med tenantkontroll; det finnes ingen appvei for å produsere den beskrevne korrupte fremmedrelasjonen. Fast-path filtrerer selve radens household. |
| B6 occurrence.template tenant | false | avvist | FamilyRow.clean itererer alle ForeignKey, også template, og save_row full_clean kontrollerer dette. Ingen normal brukerhandling kan opprette den beskrevne fremmede templatekoblingen. |
| B7 regningsutvalg umerket | low | patch | page.html sin regningsgren mangler utvalgsforklaring når gjeld/fond er nektet. Direkte tekstkorrigering. Inngår i ny utledning. |
| B8 modulavhengigheter | low | patch | Årsoversikt krever budget og annual; gjelds-/fondsregninger er snitt. Skjemaet forklarer ikke dette. Direkte hjelpetekst, inngår i ny utledning. |
| B9 fjernet/flyttet medlemskap | false | avvist | Endepunktets tenantavgrensede get_object_or_404 avviser fremmede ID-er før service. Appen har ingen flytte-/sletteoperasjon for eksisterende medlemskap; den beskrevne konkurrerende fjerningen kan ikke demonstreres via støttet bruk. |
| B10 to administratorer | low | patch | Eksisterende sekvensiell konflikttest og HH-lås er riktige; en eksplisitt konkurransetest mangler. Tillegg av avgrenset test inngår i ny utledning. |
| E1 cachet original | high | bad_spec | save_entry låser fersk Entry/Asset men forkaster objektet; require_row/validate_entry bruker gammel relasjonscache. Original kan lovlig omklassifiseres før lås hvis den ennå ikke har refusjon. |
| E2 queryset-omklassifisering | high | bad_spec | safe_rows godkjenner gamle radobjekter og returnerer PK-filter; senere SQL kan hente samme ID etter omklassifisering til sperret modul. |
| G1 tastaturnavigasjon | medium | patch | Preverifisert regression gap: DOM-harness mangler flags/focus/keydown og eksisterende tester oppdager ikke fjerning av hidden-filter. Legg til rettet atferdstest i ny utledning. |


## Verification
- `work/run-test-python.ps1 manage.py test budget.tests --noinput`: full PostgreSQL-suite pluss tilgangs-/IDOR-/refusjons-/revokasjonstester.
- Node/Compose- og private kildebevaringstester; check og makemigrations --check --dry-run uten avvik.
- Isolert Docker med før/etter migrasjon og containerbytte; lesende faktisk eieravstemming. Ingen normal worker eller virkelige familievarsler i test.
- Edge: admin lagrer, medlem i eksisterende økt mister/får tilgang, direkte HTTP avvises, mobil/desktop og nettleserkonsoll; fersk uavhengig review før push.

### Utført verifikasjon før uavhengig review
- 234 Django/PostgreSQL-tester og 45 Node/Compose-tester bestått; 20 private kildeforberedelsestester bestått.
- Edge: 157 tillatelsessjekker i faktiske nettleserøkter, 390/768/1440 px, ingen JavaScript-feil; åtte moduler, stale-versjon, familieisolasjon, manipulerte URL/POST, tilbakekalling og gjenåpning uten ny innlogging.
- Separat 139-sjekkers pushregresjon bestått. Faktisk worker/kryptering/kø ble brukt med appfaner lukket; leverandør-HTTP og nettleserabonnement simulert. Ingen fysisk OS-visning påstås. Kølagt medlemsjobb ble kansellert ved kalendernekt uten leverandørkall.
- Additiv migrasjon bevart alle eksisterende kolonner/rader: 28 tabeller, 114 rader, identiske før/etter-hasher. Faktisk lokal eierbaseline avstemmer alle 72 kildeposter; endelig etterkontroll/containerbytte gjenstår.
- Bevis: work/access-full-django.log, access-node-tests.log, access-browser-verification.json, access-push-browser-verification.json, access-revoked-worker-verification.json og access-migration-after.json. Syntetiske fixtures er private testartefakter; ingen NAS-endringer.

### Sluttverifikasjon etter iterasjon 1
- 161 faktiske nettlesersjekker bestått uten JavaScript-feil, inkludert serverlagret historisk deltaker/svar etter redigering i kalenderdialogen.
- 46 Node/Compose-tester og 20 private kildebevaringstester bestått. check og makemigrations --check --dry-run uten avvik.
- 139 pushregresjonssjekker bestått med appfaner lukket, faktisk worker/kryptering og simulert leverandør-HTTP. Ingen reelle familievarsler eller NAS-utrulling.
- Faktisk lokal eier etterkontroll: alle 72 kildeposter og verdier bevart, identisk profildigest. .env, Compose, avhengighetslås, private import- og nøkkelkontrakter uendret.
- R1 (low/patch, rettet): feltspesifikk ValidationError for ugyldig fremmed relasjon gjenopprettet etter fulltest; modulavvisning er fortsatt PermissionDenied.
- R2 (low/patch, rettet): regningsdelen skjules helt på Varsler når bills=False; kalendervarsler og lenker virker fortsatt. Egen regresjon bestått.

- Endelig fulltest: 245 Django/PostgreSQL-tester bestått (129,511 s), ingen skips. Endelig containerbytte: app og database begge erstattet på samme volum; profildigest/passord, VAPID-kryptert/public identitet, abonnementskryptering og én ventende jobb identiske før/etter. 97 app-/konfigfiler samsvarer med sluttimage.
- Matriseaudit: alle fem frosne rader har kjørte, beståtte tester (admin save/regrant/stale-version; tenant/CSRF/manipulert radtype; kalendernekt/queue cancellation; legacy-default/migrasjon/containerbevaring; mobil/PC/fokus/overflow).

### Presisering og ny utledning etter siste review (iterasjon 2)
- Sperret regningsinnsyn må også beskytte mot beløps-/suksess-orakler ved fondsbetalinger, refusjoner og angre/redigering. Når en mutasjon påvirker et årsfond kreves både fund og bills før beregning/validering under HH-låsen, inkludert den gamle persisted typen ved omklassifisering og originalen ved refusjon. Generisk feilmelding alene er utilstrekkelig fordi aksept/avvisning av prøvde beløp også kan røpe skjult saldo. Bevar visning av tillatte frittstående fondsposter/planer; forklar betalingsavhengigheten i eksisterende tekst. Skjul utilgjengelige fondsskrivehandlinger og krev samme policy på serveren før finansberegninger. Administratorer beholder full tilgang.
- Tilgang til sparing/gjeld/fond/regninger uten budsjett må ha navigerbar, filtrert posthistorikk i den respektive tillatte modulen, med eksisterende egen/admin rediger/slett/angre der skrivetilgang faktisk foreligger. Gjenbruk entry_list og eksisterende utforming; ikke opprett ny bred Poster-tilgang eller redesign. Bevar månedsvalg, paginering og tilgjengelig retur ved redigering/angre.
- Trygg startside skal respektere de samme familiemodulenes visningspreferanser som sidebar/Mer, uten at tilgangsreglene blir visningspreferanser.
- En gammel aksept må aldri fremstå som aksept av endret dato/tid etter at kalendertilgang gjenåpnes. Metadataendringer beholder svar. Ved vesentlig endring av én forekomst nullstilles berørte svar etter kalenderens eksisterende regler, også om en deltaker midlertidig er sperret. Ved fremtidig serieendring bevares sperret deltakers gamle svar på det historiske segmentet, mens den nye/endrede forekomsten krever nytt svar. Legg til begge regresjoner, inkludert at tillatt deltakers berørte svar nullstilles.
- KEEP alt fra iterasjon 1: lazy SQL, ferske låste relasjoner, kategoribegrensning, beholdt tidligere valgt sperret deltaker ved metadataredigering, kontrollert ValidationError for ugyldig relasjon, hele regningsdelen skjult på Varsler ved bills=False, all tidligere UI, migrasjon, datakontrakt og testdekning. Gjenopprettbar, byteverifisert forrige utledning: den private gjenopprettingspakken dokumentert i work/access-recovery-iteration2.json. Bruk denne for positiv bevaring og utled korrigert kode fra spesifikasjonen. Bare målrettede tester fra produsent; root tar fullverifikasjon. Eierskap og ingen commit/push fra produsent er uendret.

### Iterasjon 2 — faktisk sluttverifikasjon
- Edge besto 177 funksjons-/sikkerhets-/UI-sjekker, ingen JavaScript-feil. Reell adminlagring/eksisterende medlemsøkt, kalender-metadataredigering med bevart svar, bills-only angrelenke, savings-only faktisk redigering/retur, fund-only lesbar historikk og lik 403 for både lite/stort prøvd fondsbeløp før finansvalidering er kontrollert.
- Produsentens 120 relevante PostgreSQL-tester og 32 Node-atferdstester bestått. Root kjørte alle 46 Node/Compose-tester uten skip; full Django/PostgreSQL-sluttkjøring pågår. Migrasjon og private kontrakter er uendret.

- Iterasjon-2 siste kompatibilitetspatch: eksisterende Poster-tomtilstand beholder nøyaktig gammel create-URL; nye modulers returparametere og Utland beholdes. 54 berørte PostgreSQL-tester bestått. Full sluttkjøring gjentas. All appkode er nå frosset for root-verifikasjon.

### Endelig kandidat etter tomtilstandsretting
- Alle 253 Django/PostgreSQL-tester bestått (128,616 s), ingen skip; alle 46 Node/Compose-tester og 20 private kildetester bestått.
- Alle 177 nettlesersjekker bestått på eksakt sluttimage, ingen JavaScript-feil. check og makemigrations-kontroll bestått; 97 runtimefiler har identiske kilde-/imagehash.
- Pushregresjon 139 bestått; senere tomtilstandspatch endret bare entry_list-URL, ingen pushkode. Separat worker og lukket app testet med simulert nettleser/leverandør, ingen fysisk OS-visning påstås.
- Databevaring: kompatibel migrasjon bevart 114 tidligere rader i 28 tabeller, containerbytte bevart profil/passord/nøkler/abonnementskryptering/ventende kø og privat mount, faktisk lokal eieravstemming bevart alle 72 råkildeposter og bekreftede beslutninger. Ingen NAS-utrulling og ingen endring av .env, Compose, volum, låser eller nøkler.
- Matriseaudit gjentatt: alle fem frosne rader dekkes av kjørte beståtte tester. Tidligere funn FB1/FE1, FB2, FB3, FB4 og FG1 har egne beståtte regresjoner.

### Bounded patch etter siste review
RB1–4 er direkte tekst-/filterrettelser innen eksisterende UI og privacy-policy; RB6–10/RG1 er målrettede regresjoner uten nytt produktomfang. Ingen bad_spec/intent_gap, ingen ny modell/migrasjon/avhengighet. Produsent re-engasjert; runtime/privatdata fortsatt uendret. Ingen ny publisering før verifisert patch.

### Endelig verifikasjon og reviewlukking 2026-10-22
- RB1–4/RB6–10/RG1 er rettet og verifisert med egne regresjoner. Tre uavhengige reviewrunder er triagert; ingen uavklarte blokkerende funn. RB5 er den nødvendige låserekkefølgen mot tilbakekalling, kontrollert med samtidighetstest og begrenset transporttimeout.
- Alle 260 Django/PostgreSQL-tester bestått (108,252 s), 47 Node/Compose-tester bestått uten skip, 20 private kildebevaringstester bestått. check og makemigrations-kontroll uten avvik.
- Eksakt sluttimage besto 177 faktiske nettlesersjekker og 139 pushregresjoner, ingen JavaScript-feil. Mobil/PC, tilgjengelige kontroller og eksisterende økter er kontrollert. Leverandør-HTTP og nettleserabonnement er simulert; fysisk OS-visning og NAS-utrulling inngår ikke.
- Sluttimage: sha256:fd8a3b5556937ec46be56b85d61ba97285c56311f7e4e3fe7ebdbb9f55925264. Alle 97 runtimefiler samsvarer med kilden.
- Begge syntetiske app-/DB-containere erstattet på samme volum: profil/passord, VAPID-identitet, abonnementskryptering, privat importmontering og ventende kø identiske. Migrasjonen har bevart 114 eksisterende rader i 28 tabeller. Lesende avstemming av faktisk lokal eier bekrefter alle 72 kilderader og uendret profildigest.
- .env, Compose-filer, avhengighetslås og private kontrakter er uendret. Ingen faktisk NAS-database er åpnet eller endret. Vanlig oppdatering bruker eksisterende database og additive migrasjoner; ingen ny import/gjenoppretting.
- Ett tidligere eksisterende OS-denied avregistreringsforbedringspunkt er registrert i deferred-work.md; dette er ikke en ny tilgangsfeil. Avregistrering i støttet flyt og stopp av tilbakekalte kalenderleveringer er verifisert.
- Rotagenten har lest appdiffen og alle avgrensede reviewpatcher; alle fem rader i den godkjente matrisen har bestått verifikasjon. Privat evidens: work/member-access-verification.json.
