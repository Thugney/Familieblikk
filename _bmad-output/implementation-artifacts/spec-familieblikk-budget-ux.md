---
title: 'Tydelig kategorioversikt, postfiltre og felles merkevare'
type: bugfix
created: '2026-10-20'
status: done
route: dispatch
baseline_commit: 9560f9a0a885cd437c0697f1a6eaac8d64d2365f
review_loop_iteration: 0
context:
  - context.md
  - rules.md
  - _bmad-output/planning-artifacts/ux-designs/ux-familieblikk-2026-10-20/DESIGN.md
---

<frozen-after-approval reason="Brukeren har uttrykkelig godkjent alle disse apprettelsene i samme bestilling.">

## Intent

**Problem:** Kategorier uten månedsramme gir tomme søyler selv ved faktisk forbruk. Oversikten viser alle kategorier uten avgrensning, Poster mangler nyttige søk/filtre og paginering, og logo/ordmerke varierer mellom app, mobil og innlogging.

**Approach:** Vis ærlige kategorimål med faktisk kategorifarge og eksplisitt alternativ fordelingsgraf når rammen mangler/er null. Gi kompakt oversikt med søk og utvidelse, serverbaserte postfiltre og stabil paginering, og én delt merkevarekomponent.

## Boundaries & Constraints

**Always:** Behold godkjent fireflislogo, hvit sammenhengende arbeidsflate, norsk tekst og desktopprofil bare nederst til venstre. Post- og kategorifiltre gjelder bare sine lister, aldri familiens beregningsmotor. Behold valgt måned og filterverdier mellom sider. All filtrering og alle valglister avgrenses til serverens familie. Private importdata forblir urørt.

**Never:** Oppdiktede rammer eller datamigrering, nye avhengigheter, kalenderimplementasjon/-previewendringer, commit, push eller faktisk eierdatabaseendring fra implementeringsagenten.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Kategoriramme | Positiv ramme, overforbruk eller refusjon | Eksakte beløp; kategorifarget fremdrift avgrenset 0–100; negativt nettoforbruk beholdes i tekst | Ingen ugyldig progressverdi |
| Uten ramme | Manglende/null ramme med positivt forbruk | Tydelig relativ andel av månedens positive kategoriforbruk, aldri kalt budsjettbruk | Nullsum gir 0 og forklaring |
| Kategoriliste | Over seks kategorier, søk/utvidelse | Seks mest relevante i oversikten; antall, søk og se-alle/utvid; Budsjett beholder komplett tilgang | Ingen treff har nullstill-lenke |
| Postfiltre | Tekst, type, kategori, oppretter, dato, inntektsstatus | Kun treff innen valgt måned; bekreftede filtervalg beholdes; maks 10 rader per side og stabil rekkefølge | Ugyldige/fremmede filtervalg gir feltfeil og ingen fremmede resultater |
| Isolasjon | Filtre og sidetall endres | KPI-er, kategorisummer, regninger og sparing er uendret | Ingen skjult endring av regnskapsgrunnlaget |
| Merkevare | Innlogging, mobil skjemaside, desktop | Samme ordmerke, font, vekt, avstand og fireflismerke; ingen duplisert desktopprofil | Logo krever ingen ekstern ressurs |

</frozen-after-approval>

## Code Map

- `budget/views.py` bygger nå kategorisummer fra en allerede filtrert postliste; skill komplett månedsgrunnlag fra listefiltre. Gjenbruk `services.calculate` uendret.
- `budget/forms.py` kan eie familieavgrensede filterfelt. `Entry.sequence` gir stabil siste sorteringsnøkkel.
- `budget/templates/budget/category_list.html`, `entry_list.html`, `page.html` og ny filter-/merkevareinclude viser tall og navigasjon.
- `budget/templates/budget/base.html`, `auth.html` og `static/budget/app.css` samler eksisterende merkevare; `icon.svg` endres ikke.
- `budget/tests/` bruker isolert PostgreSQL via eksisterende `work/run-test-python.ps1`. Koordinator eier ekte nettleser-/Docker-/eierkontroll og uavhengig sluttgjennomgang.

## Tasks & Acceptance

**Execution:**
- [x] Views/filterformer: separat månedsgrunnlag, familieavgrensede filtre, 10-raders paginering.
- [x] Maler/CSS: ærlige fargede kategorisøyler, kompakt kategorioversikt og vedvarende filtre/sidenavigasjon.
- [x] Delt merkevare på innlogging, desktop og mobilskjemaer.
- [x] Målrettede tester for matrisen; overlever diff og resultater til uavhengig gjennomgang.

**Acceptance Criteria:** Ingen brukerdata/schemaendring. Eksisterende innlogging, roller, budsjettberegninger og kalenderfiler bevares. Mobil og desktop verifiseres av koordinator før ferdigmelding.

## Implementation Notes

Ingen uavklarte produktvalg. Ingen irreversibel operasjon. Arbeidsfiler på codex/family-calendar tilhører samtidig autorisert kalenderarbeid og bevares. Brukerens eksplisitte gjennomføringsgodkjenning erstatter ny mellomgodkjenning av samme avgrensning.

## Spec Change Log

## Review Triage Log

| Funn | Vurdering | Tiltak og bevis |
|---|---|---|
| B1 | low / defer | Existing base month form already submitted only month before this change, including the previous kind filter. Pagination/reset preservation in current scope passes. No new regression. |
| B2 | low / patch | New shared form introduces income status to remittance-only list. Restrict this form at existing page boundary; no change to base records. |
| B3 | medium / patch | Query searches category__name but refund rows attribute category through original; selector already follows original category. |
| B4 | false / reject | No membership removal/transfer path exists; registration preserves one family per existing user and refuses account takeover. No demonstrated reachable caller produces the hypothetical former member. |
| B5 | low / patch | Form omits category_all, while expand link explicitly changes that GET state. Preserve existing flag with hidden input. |
| B6 | low / patch | Template prints share percentage with positive category denominator zero. Add an explicit no-positive-spending state without inventing a limit. |
| B7 | low / patch | Single empty template branch treats all empty querysets as no-match. Distinguish empty base from filtered no-match with reset/new-entry actions. |
| B8 | low / reject | Base queryset always intersects selected month, verified by dedicated cross-month regression. Browser min/max guides everyday date entry. Direct URL acceptance causes no out-of-month result or leak; adding server bounds would change tested intersection semantics for a negligible uncommon case. |
| V1 | medium / patch | Current fixture has no archived rows. Add both spending and no-spending archived rows to assert actual statuses; trust verification-gap evidence. |

## Verification

Kjør målrettede Django/PostgreSQL-tester for kategori-/postvisning og merkevare, samt relevante eksisterende side-/månedstester. Koordiner fullkjøring med hovedagenten. Ingen ekte eierdata brukes som testfixture.

Implementert separat EntryFilterForm, stabil 10-raders paginering, gruppeaggregerte ufiltrerte kategoritall, topp seks med søk/utvidelse, ærlig forbruk-andel uten ramme og delt brand.html. Avanserte postfiltre ligger i tilgjengelig details som åpner ved aktive filtre/feil. Ingen avvik fra frozen intent.

Målrettet PostgreSQL-verifikasjon: `work/run-test-python.ps1 manage.py test budget.tests.test_budget_ux budget.tests.test_month_navigation --keepdb`. Koordinator overtar uavhengig gjennomgang, fullsuite og faktisk nettleser på desktop/mobil; disse portene er ikke egensertifisert.

Koordinatorens faktiske mobilgjennomgang: sidegrensen strammet til 10 poster for å redusere scrolling; tom familie beholder opprinnelig oppstartstekst, mens tomt filterresultat får nullstillingslenke.

Sluttkontroll: 71 PostgreSQL/Django-tester består (47,999 sekunder), systemkontroll uten feil, 71 faktiske Docker-nettleserkontroller på fem bredder, inkludert frakoblet fallback med merkevare. Service worker-test består. Uendrede importerte kilder/råverdier/målkoblinger kontrollert privat etter containeromstart. Kalender er fortsatt separat fiktiv designkandidat uten menneskelig aksept.

Uavhengig sluttverifikasjon: work/budget-usability-review.json uten blokkere, alle 14 kildehashverdier matcher sluttkontrollen. Tre BMAD-gjennomganger er triagert i work/budget-ux-triage.json; tidligere tap av filtre ved månedsbytte er dokumentert som utsatt. Ingen commit eller push utført.

Godkjent oppfølging: kategorisøk oppdateres etter 300 ms og statusvalg straks gjennom samme GET-rute; kun resultatcontainer erstattes. Fokus/skjemaverdier beholdes, foreldede svar avbrytes/ignoreres, feil beholder tidligere resultater og URL. Vanlig GET er fallback. Ingen privat nettleserlagring.
