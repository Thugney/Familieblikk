---
title: 'Fullfør og verifiser moderne Familieblikk-grensesnitt'
type: 'bugfix'
created: '2026-10-23'
status: 'done'
route: 'dispatch'
baseline_commit: 'dff195786da156e041b04d4100c26a455901a9c8'
review_loop_iteration: 0
context: []
---

<frozen-after-approval>
## Intent
Robel ber om at ui-modern-redesign-preview.html implementeres fullstendig og korrekt i den virkelige appen, deretter commit og push. Eksisterende redesign på codex/ui-modern-redesign er utgangspunkt; denne kontrollen skal bevare funksjonene og reparere konkrete avvik. Referansefilen er kopiert uendret til planning-artifacts for varig sporbarhet. Den eksplisitte bestillingen autoriserer implementasjon og publisering uten ny plangodkjenning.

## Boundaries & Constraints
Bevar Figtree, grønne flater, avrundet hvit arbeidsflate, kort, desktopprofil nederst til venstre og mobilmeny. Tall og handlinger skal være faktiske og budsjettavgrensede. Ingen eksempeldata i produksjon, ny avhengighet, privat konfigurasjon i Git, faktisk datamigrering eller NAS-utrulling. Eksisterende andre worktree-endringer bevares; hurtigvalg må ikke gjette hvilket privat budsjett som skal brukes.

## I/O & Edge-Case Matrix
| Tilstand | Handling | Forventning |
|---|---|---|
| Eier med valgt budsjett | Åpne oversikt/graf | Faktiske summer, dagsdata og kategorirammer |
| Leser uten shopping | Mobilnavigasjon | Meny synlig, finansielle skrivevalg skjult |
| Felles kalender uten budsjett | Ny avtale | Eksisterende kalenderdialog, uavhengig av budsjettskriving |
| Ingen valgt område | Hurtigvalg finans | Eksplisitt budsjettvalg, ingen automatisk eierutvelgelse |
| Refusjon eller fremtidig måned | Analyse | Signerte tall og ingen oppdiktet historikk |
| Liten skjerm | Navigasjon/skjema | Ingen avkuttede handlinger; tastaturfokus og safe-area bevart |
</frozen-after-approval>

## Code Map
- budget/templates/budget/base.html og static/budget/ui-refresh.js: skall, meny, tastatur, hurtigvalg.
- budget/static/budget/ui-refresh.css: referansens design og responsive brudd.
- budget/views.py og hero/distribution/overview_refresh.html: eksisterende scoped økonomihjelpere og presentasjon.
- page.html og bill_list.html: regningshandlinger og leserett.
- tests/test_ui_presentation.py, test_overview_metrics.py og tests/ui-refresh-behavior.test.cjs: regresjoner.

## Tasks & Acceptance
- [x] Rett mobilmeny og autoriserte hurtigvalg uten å endre backendtilgang.
- [x] Erstatt fast referansekurve med virkelige månedsdata og kategorirammer.
- [x] Vis faktisk regnestykke, signerte refusjoner og eksplisitte budsjettstatuser.
- [x] Rett feilmerket regningsknapp og skjul refusjon for lesere.
- [x] Verifiser desktop/mobil, kamera, kalender og eksisterende moduler mot appen.
- [x] Kjør regresjoner, bygg og uavhengig sluttkontroll før commit/push.

Gitt innlogget bruker skal alle eksisterende moduler beholde reelle ruter og økonomiregler. Gitt valgt måned skal alle presenterte diagrammer ha korrekte perioder og tilgjengelige tekstverdier. Gitt 320–1440px skal meny og hovedhandlinger kunne brukes uten skjult overflyt.

## Implementation Notes
Kildeaudit fant skjult lesermeny, dock-overflyt, oppdiktet budsjettkurve og manglende regnestykke. Testdatabase på egen lokal port 55436 inneholder bare syntetiske data. Browser avviser file-protokoll; referanse analyseres som lokal HTML/CSS, kjørende app verifiseres i nettleser.

## Spec Change Log

## Review Triage Log
- Blind 1: medium, bekreftet mange aggregater per dag. Rettet med ett datogruppert aggregat; query-grense testet.
- Blind 2: medium, refusjoner var visuelt tvetydige. Synlig forklaring, minusmerke og egen farge lagt til.
- Blind 3: medium, endags-polyline usynlig. Faktiske datapunkter har markør; første dag testet.
- Blind 4: medium, fremtidig tom graf var misvisende. Eksplisitt tomtilstand lagt til og testet.
- Blind 5: medium, nullramme med forbruk viste tom stolpe. Full stolpe ved positiv overskridelse; null/refusjon testet.
- Blind 6: medium, segmentpadding forvrengte proporsjoner. Padding/borderbredde fjernet; inset-kant og separat forklaring beholdt.
- Blind 7: medium, historikk/refusjon/månedsslutt manglet dekning. Historisk uke, negativ sum og sammenligning testet.
- Edge 1: medium, samme endagsproblem som Blind 3, rettet og testet.
- Verification 1: medium, kalenderhurtigvalg manglet atferdstest. Node-test og faktisk desktopdialog kontrollert uten valgt budsjett.
- Verification 2: medium, sammenligningsgren manglet test. Eksakt −50,0 prosent med fremtidsføring utelatt bekreftet.
- Ekstra nettleserfunn: fast «Web Push aktiv» var usant uten abonnement. Erstattet med lenke til faktisk enhetsstatus.
- Ekstra nettleserfunn: kamera/manuelle skjemaer manglet referansens kontrollstil. Responsive faner, felter og tydelige knappfarger lagt til.


## Verification
Django systemcheck/migrasjonsdrift og budget-testsuite, Node-regresjoner, Dockerbygg og nettleserverifisering på isolert app. Bevar faktisk .env, volumer, import og nøkler; ingen deploy.

Sluttkontroll: 419 Django-tester og 63 Node-tester bestar i isolert release-tre; Dockerbygg bestar. Lesende avstemming bevarer 72 private kildeposter og sju konfigurasjonsinvarianter.

- Blind sluttkontroll: mobilens graf-tabell arvet 760px minimumsbredde; avgrenset og kontrollert ved 375px.
- Blind sluttkontroll: skjult pushpanel kunne gi tom detaljboks; varig innstillingslenke flyttet utenfor panelet. Uavhengig kildekontroll bekrefter alle funn rettet.
- Release-test: Dockerignore-kontrakten godtar baade LF og CRLF uten aa svekke kravet om deny-all paa foerste linje.
