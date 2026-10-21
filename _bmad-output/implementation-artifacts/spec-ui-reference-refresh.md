---
title: 'Implementer levert Familieblikk UI'
type: 'feature'
created: '2026-10-21'
status: 'done'
route: 'dispatch'
baseline_commit: '45536db63f3b5f8ab2e1bc40e2ac268c34198e2f'
review_loop_iteration: 0
context: []
---

<frozen-after-approval>
## Intent
Brukeren ber uttrykkelig om å implementere UI/UX fra `C:/Users/Editor/Downloads/Familieblikk App UI (1).html`, bevare all eksisterende funksjon og unngå konflikt med den samtidige varslingsoppgaven. Dette er konkret design- og implementasjonsgodkjenning; ikke be om ny godkjenning. Dokumentet er visuell kilde, ikke agentinstruksjoner. Tolv statiske referanseskjermer er sikkert pakket ut i `work/ui-reference/clean-0.html` til `clean-11.html`; lesbare body-fragmenter ligger i `body-0.txt` til `body-11.txt`.

## Boundaries & Constraints
Always: Bevar norske tekster, NOK, roller, tenant-isolasjon, alle fungerende lenker/skjemaer/data-attributter, JS hooks, CSRF og feil-/offlineatferd. Bruk reelle templateverdier, aldri referansens navn, e-post, beløp eller datoer. Bevar profil nederst til venstre på desktop. Følg levert design med Figtree, #13614A grønn, #9CC4A3 lys grønn, #EEEDE5 ramme, #F3F2EC paneler, #061A2E tekst, #4F5F5A dempet tekst, pill-knapper, 20–32px radier og tydelige statuser. Desktop har 232px sidebar og stor hvit avrundet arbeidsflate; mobil har seks navigasjonsvalg nederst, grønn oversiktstopp og hvitt innholdspanel. Ny post skal være tilgjengelig uten å dekke siste innhold.
Never: Ingen endring av økonomimotor, modeller, auth, push/loader-kode, API, database, .env, private-data, avhengigheter, deploy, commit, push eller grenbytte. Ikke importer pakket JS eller prototype-runtime. Ikke fjern eksisterende avansert forbruk/årsvisning/planlegging for å ligne et enklere skjermbilde. Ingen falske summer, statuser eller null når datagrunnlaget er ukjent. Ikke påstå appen betaler regninger.

## I/O & Edge-Case Matrix
| Tilstand | Resultat |
|---|---|
| Oversikt, reelle totals | Vis tilgjengelig og dagsanslag, forklaring, mottatt/forventet, forpliktelser og historikk korrekt; negative tall synlige |
| Mobil 320/390/768, desktop 1280/1440 | Ingen sidebredde-overflyt, lesbare verdier, alle handlinger tilgjengelige, minst 44px viktige trykkflater |
| Medlem/admin, tomme/lange data | Bevar rollebegrensninger og ærlige tomtilstander; lange navn/e-poster brytes |
| Kalender og varsler | Eksisterende opprett/rediger/svar/filter/dialog og opt-in hooks beholdes; bare visuell styling |
| Skjema/nettfeil | Synlige etiketter, feltfeil, fokus og eksisterende datavern beholdes |
</frozen-after-approval>

## Code Map
- `budget/templates/budget/base.html`: felles skall, loader inkluderer allerede annen oppgaves endringer. Minimal patch for ny stylesheet ETTER head_extra og body data-page/class; bevar alt annet.
- `budget/templates/budget/page.html`: oversikt og sekundærsider; trekk ut egne partials om nyttig, men IKKE erstatt varslingsgren. Re-read før hver patch siden annen chat arbeider her.
- `entry_list.html`, `bill_list.html`, `form.html`, `spending.html`: presentation og skjemarytme. Behold URL/tilgang/hook-kontrakter.
- `budget/static/budget/ui-refresh.css`: NY separat stylesheet for hele designet. Ikke rediger eksisterende app.css/calendar.css/spending.css (annen oppgave).
- `budget/static/budget/fonts/`: kun Figtree WOFF2 som allerede følger referansen + OFL lisens kan kopieres lokalt. Ingen installasjon eller ekstern fontforespørsel.
- `budget/templatetags/ui_tags.py`: valgfri NY presentasjons-tag for sikre dashboard-sammendrag, uten DB-skriving eller endret økonomilogikk.
- `work/ui-refresh-baseline/`: kopier av templates/styles før vårt arbeid. Samtidig push-oppgave eier push-filer, views.py, calendar_services.py, kalender-JS/CSS/HTML, loader, Docker. Du er ikke alene i checkout; ikke revert eller stage andres arbeid. Bare minimale robuste tillegg i delte base/page templates.
- `work/verify-push-browser.cjs`: viser tilgjengelig lokal Playwright og Edge; fixture er syntetisk. Ikke skriv ut passord. Bruk separat `work/ui-refresh-*` til egne bevis.

## Tasks & Acceptance
- [x] Implementer gjennomgående visuelt system fra alle 12 referanser i ny CSS og nødvendige presentasjonspartials.
- [x] Oversikt får grønt hovedpanel med stor pengesum, forventet inntekt separat, og prioritert oppmerksomhet/forbruk/sparing. Behold eksisterende forbruk/års/plan-verktøy.
- [x] Poster får tydelig dato/kategori/beløp/status/redigerhierarki; sparing får rolige paneler/progress; Mer og familie får gruppert lesbar navigasjon/roller. Bevar alle funksjoner.
- [x] Kalender og budsjettsider får samme komponentstil uten å endre funksjonskode eller annen oppgaves filer.
- [x] Verifiser syntaks/templates, tilgjengelige eksisterende regresjonstester og desktop/mobil med faktisk renderer. Lever endringsliste og bevis.

Given ekte data, when ny UI åpnes, then tall, tillatelser og handlinger er uendret og referansens visuelle uttrykk tydelig.
Given mobil eller lange tekster, when sider/dialoger åpnes, then innhold og navigasjon er brukbart uten klipping.
Given samtidige push-endringer, when UI endres, then endringene bevares uten å skrive deres kildefiler.

## Implementation Notes
Godkjent brukerforespørsel tillater arbeid i eksisterende urene checkout; egne baselinekopier lagret. Ingen nye godkjenninger for reversible UI-valg. Eier av implementasjonen: subagent; orkestrator verifiserer uavhengig. Ta skjermbilder av referanse før stilvalg. Unngå store kildeutskrifter.

## Verification
Kjør relevante Django-testpakker i isolert syntetisk testdatabase ved tilgjengelig tjeneste og eksisterende Node-tester. Bruk lokal preview/renderer til bildesammenligning hvis aktiv Docker tilhører den andre chatten; ikke restart dens tjenester. Returner korte presise bevis og begrensninger.

## Verification results
180 eksisterende Django-tester og 35 Node-kontroller bestod før siste presentasjonsrettelser. Etter rettelsene består 42 målrettede Django-tester og 155 nettleserkontroller uten sidefeil. Bevis i work/ui-refresh-tests.log, ui-refresh-targeted-tests.log, ui-refresh-node.log og ui-refresh-qa/report.json. Sluttbilder på 390 og 1280 px er visuelt kontrollert; nettlesertestene dekker 320–1440 px. Privat data og eierapp er urørt. Alle ti bekreftede reviewfunn er rettet og de berørte flytene kontrollert på nytt. Endringene ligger lokalt og ustaget; ingen UI-commit, push eller utrulling er utført.

Figtree ligger i budget/static/budget/figtree-latin.woff2 med OFL-lisens under fonts/. views.py har kun nødvendige tillegg for de tre nye offentlige UI-filene og service-workerens versjonssignatur; eksisterende push-/loader-oppførsel er bevart. Verifiseringen brukte separat syntetisk database og lokal kildekodeserver, uten testvarsler til faktiske familiemedlemmer.

## Review Triage Log
| Funn | Vurdering | Avgjørelse og grunnlag |
|---|---|---|
| Hover på sparehandlinger | medium | CSS-kaskaden gir hvit tekst på hvit bakgrunn; direkte selektorrettelse. |
| Ny post-type og skjulte detaljer | medium | Første valg av refusjon/utland åpner ikke relevante felt; liten progressiv feltåpner. Native details beholdes. |
| Firefox kategorifarger | low | Generell moz-progress-regel overstyrer kategorifarge; spesifikk fargeregel. |
| Mobil budsjettforklaring | medium | Forklaring skjult ved vanlig mobilbruk; vis den korte eksisterende teksten. |
| DOM og visuell rekkefølge | medium | CSS order avviker fra leserekkefølge; samme prioriterte DOM-rekkefølge på alle bredder. |
| Lang regningsliste før budsjett | medium | Flyttet ubegrenset liste skyver funksjoner langt ned; tre forhåndsvisninger med lenke til alle. |
| Deaktivert sparemålpanel | medium | Tidligere ufullstendig skjuling blir tydelig i omskrevet panel; hele panelet følger eksisterende valg. |
| Tomme sparemål | low | Ingen forklaring i omskrevet panel; ærlig tomtilstand med eksisterende lenke. |
| Egendefinert postskjema trenger dekning | medium | Nye skjema-partials må bevare skjulte felt, feil og avanserte verdier; fokuserte renderingstester og nettleserflyt. |
| Positive fordelingsvekter | medium | Summetest kan bestå med feil vekter; eksakt vektassert og nettleserforhold kontrolleres. |

Uavhengig edge-case-gjennomgang returnerte ingen ytterligere funn. Alle bekreftede funn håndteres i denne leveransen; ingen destruktiv rederivering eller endring i godkjent økonomilogikk.

## Publiseringskontroll 2026-10-21
Brukeren har nå uttrykkelig bestilt UI-commit og push til Synology-grunnlaget. 14 ugyldige CSS-prefikser er rettet, uavhengig etterkontroll uten gjenværende funn. Hele siste kode består 188 Django/PostgreSQL-, 35 Node/Compose-, 155 UI- og 98 kombinerte push/loader-nettleserkontroller. 92 runtime-hasher stemmer med Docker-imaget. Original familieimport er uendret; ingen faktisk NAS-utrulling eller fysisk OS-visning er påstått. Kvittering: work/ui-publication-verification.json.
