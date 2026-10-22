---
title: 'Kameraskanning og felles handleturer'
type: 'feature'
created: '2026-10-22'
status: 'done'
route: 'dispatch'
baseline_commit: '9f55b9832fcdd9e37c4fb2eeccfc404e04edf667'
review_loop_iteration: 2
context:
  - '.project-init/camera-scan-amendment.json'
  - '.project-init/documents-shopping-approval.json'
  - '_bmad-output/specs/spec-familieblikk-family-workflows/phased-scope.md'
  - 'rules.md'
---

<scope-amendment reason="brukerens kamerakorrigering erstatter tidligere arkivkontrakt">

## Intent

Familien tar bilde av kvittering/faktura og skanner sum, dato og betalingsmottaker. Bildet behandles midlertidig på egen server med allerede godkjent OCR, deretter forkastes det. Brukeren gjennomgår feltene og bekrefter før økonomipost opprettes eller kobles. Delte handlelister og én eksplisitt bekreftet utgift per tur består. Valg av egen server er implementasjonsvalget etter brukerens ønske om anbefaling; ikke påstå en separat, ordrett godkjenning som ikke finnes.

## Camera amendment — governing implementation contract

This section supersedes every retained-original, PDF-upload, original-download and document-backup requirement in the historical implementation/review notes below. Those notes remain evidence of earlier work, not acceptance of the revised scan flow.

- Entry point: «Skann kvittering eller faktura», camera first on supported phones, with an image-picker fallback for desktop or unavailable camera. Accept JPEG/PNG photos only in the new scan endpoint; do not offer PDF import. Explain temporary transfer to the family's own server before scanning. Keep manual entry available.
- Show a local photo preview with retake and simple guidance: all edges visible, readable text, even light. Never post automatically on capture. Release the local preview/object URL on replacement, cancellation or successful extraction; do not put photos in localStorage, IndexedDB or service-worker caches.
- Store new scan photos only in a dedicated private transient spool, separate from legacy originals and excluded from backups. Bound reception to 10 MiB and decoded images to 25 megapixels. Keep the existing local-engine resource/time limits and one concurrent OCR task; push remains independent.
- Apply the same lifetime boundary to multipart reception and decoder/OCR scratch files: use bounded private temporary directories, clear them on normal exit, and cover abandoned files at startup. Never log image bytes, OCR text or extracted financial values. No scan artifacts enter backup archives.
- Delete each new transient photo immediately after successful extraction or terminal processing failure, and on explicit cancellation. A worker/startup sweeper expires queued/interrupted scans after 15 minutes and removes orphaned spool files after the same limit. Cleanup is limited to the dedicated spool and must never traverse links or touch historical document storage. If the worker is down, cleanup resumes on startup; the UI must not promise an exact deletion time during downtime.
- Persist only structured candidate fields needed by this flow, reviewed fields, status, ownership and financial links. Do not persist full OCR text, thumbnails, EXIF, source filenames or photo bytes for new scans. Candidate fields are amount, document date and payee; optional due date remains available for bill creation, and category is selected by the user. Do not infer that an invoice has been paid.
- Commit extracted candidates and a cleanup-pending state atomically before unlinking the photo. Mark cleanup complete only after confirmed deletion; retry cleanup after interruption without rerunning recognition or losing candidates. A failed result commit leaves the image subject to the expiry bound. Job lease/generation checks must prevent a stale worker from publishing results after cancellation, expiry or retake; retake starts a new scan identity. Cancellation clears unconfirmed candidates and schedules cleanup, while preserving any already confirmed financial record. Serialize these state transitions with confirmation so cancellation cannot race a posting into an inconsistent state.
- Uncertain or conflicting totals/dates/payees remain visibly unconfirmed, with no silent choice between equal candidates. Prefer explicit payable-total labels over subtotal/VAT/tender/change. Validate whole money tokens and real calendar dates; distinguish document date from due date. Unlabelled merchant headings may be suggestions, never facts. No fabricated confidence percentage.
- Camera recognition uses one bounded TSV pass with an internal engine-quality cutoff. Withhold doubtful whole lines rather than guessing digits; uncertain financial labels cannot silently enable weaker totals. Reject malformed or oversized recognition output instead of treating a truncated prefix as complete. These safeguards do not establish a real-world accuracy percentage; manual correction remains part of the accepted workflow.
- Review: editable amount/date/payee and required category; explicit choice of expense, unpaid bill or link to an existing permitted record. Confirmed scan details survive photo deletion. Missing recognition uses manual entry or retake. Retry after photo removal requires a new photo; never claim the original is still available.
- Preserve current idempotency, stale-version recovery, financial module permissions, duplicate warnings and links through correction/reversal/restore. Duplicate detection uses reviewed structured fields and existing targets; do not retain a photo hash solely to recreate an archive feature. A late scan attached to a shopping trip creates no second expense and cannot silently change its total.
- Existing historical records/files remain untouched by migration and cleanup. Distinguish legacy retained documents from new transient scans explicitly. No destructive migration, actual-family mutation, dependency installation, commit, push or deployment follows from this amendment.

Required evidence before completion: actual camera/image review on mobile and desktop; successful and failed recognition leaves no new photo; cancellation, queued expiry, crash recovery, orphan cleanup and backup exclusion; ambiguous totals/dates and ordinary merchant headings; no financial writes before confirmation; exact and concurrent retry; two-member shopping refresh/conflict; cross-family and revoked-module denial; existing configuration and actual 72-source-row read-only preservation. Earlier archive tests do not prove these revised requirements.

## Historical archive baseline — superseded where camera contract differs

Alltid: norsk UI, eksisterende visuell stil, privat familietilhørighet, gjeldende modulrettigheter, eksplisitt økonomisk bekreftelse, optimistisk versjonskontroll og idempotens. Originaldokument og historikk bevares. Lokal OCR; ingen ekstern behandling. Én hovedkategori og separat tur per butikk.

Aldri: automatisk bokføring fra opplasting/avkryssing, doble utgifter, datatap, endring av eksisterende .env/nøkler/databasevolum/importkilde, NAS-utrulling, commit/push eller installasjon av nye avhengigheter uten uttrykkelig godkjenning. Test bare syntetiske familier; faktisk familie leses bare for bevaringskontroll.

## Historical archive matrix — not revised acceptance

| Tilstand | Handling | Resultat | Feil |
|---|---|---|---|
| PDF/JPEG/PNG | Last opp/fotografer | Privat original, vedvarende OCR-jobb, redigerbart utkast; null poster | Størrelse/innhold/ressurser avvises tydelig |
| OCR klar/feilet | Gjennomgå | Original og forslag til leverandør, NOK-beløp, dato/forfall, nummer/KID, kategori | Manuell retting; aldri gjett/bokfør |
| Godkjent utkast | Bekreft faktura/utgift eller koble til eksisterende | Én ubetalt engangsregning eller én utgift; kobling gir null nye poster | Duplikatvarsel og konflikt uten overskriving |
| Samme/nytt bilde | Gjenta | Filhash og bekreftede kjennetegn viser eksisterende dokument-/regning-/betalingskjede | Ingen automatisk sammenslåing |
| Delt liste | Legg til/rediger/kryss av vare, antall, valgfri pris/kategori | Andre medlemmer ser gjeldende liste; null økonomiske poster | Versjonskonflikt beholder utkast |
| Handletur | Bekreft dato, faktisk total, kategori, valgfri kvittering | Én lenket utgift, beggeveis lenke | Samtidig retry gir samme utgift |
| Fullført tur | Sen kvittering, retting/angre/gjenopprett | Samme utgift/historikk/kobling | Beløpsendring krever eksplisitt postretting |
| Annen familie eller tilbakekalt tilgang | Les/skriv/retry/last ned | Ingen private felt eller økonomilenker eksponeres | Avslag også ved tidligere gyldig nøkkel |
| Omstart/arbeiderfeil | Start igjen | Originaler, koblinger, kø og utkast består | OCR blokkerer ikke push; begrenset retry |

</scope-amendment>

## Code Map

- `budget/services.py`: `save_entry(actor,row,expected_version=None,command_key=None)` for utgifter; `save_row` for ny `BillTemplate(monthly=False)`; `materialize_template` for forekomst. Aldri `prepare_month` på dokument-/listelesing.
- `budget/access.py`: `lock_member` inne i atomic før replay. MODULES utvides, men documents/shopping utelates fra FINANCE. Nye rader krever egen policy før safe_rows' finanshurtigsti.
- `budget/correction_services.py`: eksisterende entry_state/visible_history og rettingsruter gjenbrukes; Entry beholdes ved reversering.
- `budget/views.py`, `forms.py`, `templates/budget/base.html`: get_member, NAV, TITLES og MoneyField gjenbrukes. Dedikerte ruter før generisk app/page. Ikke redesign.
- `docker-compose.yml`, `Dockerfile`, `familieblikk/settings.py`: separat dokumentvolum og OCR-arbeider med begrensninger; eksisterende DB/push-identitet bevares.

## Historical execution checklist — superseded for scan storage and UI

**Execution:**
- [ ] `budget/document_models.py`, `shopping_models.py`, `models.py`, `migrations/0015_*`: additive modeller, stabile kommando-/koblingsnøkler, ingen omskriving av eksisterende økonomi.
- [ ] `budget/document_services.py`, `document_storage.py`, `document_ocr.py`, `management/commands/document_worker.py`: privat lagring, innholdsvalidering, begrenset lokal kø, forslag og duplikatkontroll. Oppbevar dokumenter til eksplisitt senere slettingspolicy; ingen automatisk sletting.
- [ ] `budget/shopping_services.py`: delte lister, vareendringer, versjoner, atomisk fullføring, koblinger og historikk.
- [ ] `budget/document_views.py`, `shopping_views.py`, egne skjemaer/maler/JS, `urls.py`, `access.py`, meny: tilgjengelig mobil/PC, kilde og gjennomgang, feilmeldinger, beholdte utkast, automatisk listeoppdatering uten å overskrive innskriving.
- [ ] Compose/settings/driftsdokumentasjon: persistent privat dokumentlager, uavhengig kø, oppdaterings-/backupkontrakt. Ingen pakkeinstallasjon før godkjenning; manglende motor er synlig ufullført OCR, aldri simulert suksess.
- [ ] `budget/tests_documents.py`, `tests_shopping.py`: alle matriserader, reelle PostgreSQL-konflikter/retry, tenant-/modulpolicy og restartsikkerhet. Browserkontroll med fiktive dokumenter og to medlemmer.

**Acceptance Criteria:**
- Gitt dokument eller listeutkast, når det lagres, så endres ingen økonomi før bekreftelse.
- Gitt eksisterende betaling/tur, når kvittering kobles eller bekreftelse gjentas, så finnes bare én utgift og lenken består etter reversering/gjenoppretting.
- Gitt listetilgang alene, når medlemmet åpner fullført tur, så finnes ingen skjulte beløp/dokumentmetadata/økonomilenker.
- Gitt faktisk eksisterende familie, når releasen verifiseres, så består lesende 72-kilderaders avstemming og uendrede private konfigurasjonshasher.

## Historical implementation notes

Godkjenningen gjelder begge planer og bygging; ingen ny godkjenningsrunde for samme omfang. Hovedagenten har produsentansvar for denne spesifikasjonen og koordinerer avhengighetsgodkjenning. Implementeringsagenten eier appkode/tester og nødvendige driftsendringer; andre agenter kan arbeide samtidig, ikke reverser deres endringer. Ved usikkerhet velges konkret kompatibel implementasjon innenfor kontrakten, og avvik rapporteres.

OCR-motor/pakkeversjon og fysisk NAS-ressursramme avklares før installasjon. Implementer adapter/kø og øvrige funksjoner uten å installere pakker; full OCR-aksept krever ekte motor etter godkjenning. Anbefalt innledende grense: 10 MiB/fil, 10 PDF-sider, 25 megapiksler/bilde, én OCR-jobb samtidig med tids-/minnegrenser; dokumenter grensene i UI.

Avklart 2026-10-22: Robel godkjente Docker-only tesseract-ocr 5.5.0-1+b1, nor/eng 1:4.1.0-2, poppler-utils 25.03.0-5+deb13u4 med nødvendige biblioteker. Ingen ny venv/global installasjon. Oppgitt vert: DS3622xs+ DSM på tilpasset Xeon D-1531-maskin, rundt 20 GB RAM. Senere Azure/annen hosting er fremtidig mål, ikke utrullingsmandat; bruk portabel lagringsgrense og Docker-volume nå.

## Spec Change Log

2026-10-22 — Reparasjonsreview fant at upload lagret en ny fil før eksakt replay ble kontrollert. Krev autorisert replay-precheck før dekoding/lagring og fortsatt låst sluttkontroll. Bare den aktuelle forespørselens nyopprettede, aldri refererte stagingfil kan ryddes ved tapt race/avslag; ingen eksisterende originaler eller generelle kataloger slettes. Verifiser uendret filantall ved retry og trygt avslag etter endret tilgang/kø. KEEP: kort husholdningslås, dekoding utenfor lås og alle refererte originaler.

2026-10-22 — Uavhengig review avdekket hull i opplastingsgrense før multipart-lagring, låseomfang, HTTP-replay, oppdagbar historikk og beløpsparser. Utvid utførelsen nedenfor uten å endre godkjent brukerintensjon. KEEP: eksisterende filer, data, originaler, regnskapskoblinger, bekreftelseskrav, private konfigurasjoner og andres arbeid bevares; reparer inkrementelt etter prosjektets uttrykkelige bevaringsinstruksjon, ikke slett fungerende implementasjon.

Reparasjonskontrakt: håndhev 10 MiB mens opplastingen mottas; utfør dyr innholdsvalidering før husholdningslås, revalider tilgang/kø/replay i kort transaksjon. Valider PNG/JPEG tilstrekkelig til å avvise tom/trunkert bildestrøm med eksisterende godkjente Docker-motorer, ingen ny pakke. Sikkerhetskopier dokumenter direkte til diskdestinasjon uten komplett arkiv i appens tmpfs. Dokumentoversikt pagineres, bekreftede felter vises uforanderlig. Vis bevarte turvarer og fjernede varer med eksisterende versjonskontrollert gjenoppretting. Duplikatvarsel viser kun autoriserte kandidater. Norske grupperte beløp parses helt eller forkastes; ingen deltreff. HTTP-skjema må tillate tidligere kvittering ved autentisert eksakt replay uten å åpne nye koblinger. Gjenopprettet listeutkast regnes som urørt av polling inntil bruker velger lagring/forkasting. Tester utfører JS refresh og HTTP recovery/retry, ikke bare servicefunksjoner.

## Review Triage Log

| Funn | Dom og bevis | Rute |
|---|---|---|
| Blind 1 backup tmpfs | high: backup.ps1 bygger hele tar i /tmp, app har tmpfs; voksende arkiv kan fylle minne. | bad_spec |
| Blind 2 upload lock | medium: både documents-view og upload tar husholdningslås før pdfinfo opptil 15 sekunder og fil-I/O. | bad_spec |
| Blind 3 100 dokumenter | medium: documents-view bruker [:100] uten paginering; eldre ukoblede filer blir utilgjengelige i oversikten. | bad_spec |
| Blind 4 turvarer | medium: detail fjerner trip-varer fra aktiv liste og mal viser ingen trip.items; bevarte varer kan ikke gjennomgås. | bad_spec |
| Blind 5 duplikater | medium: complete_trip returnerer generisk ValidationError; fullføringssiden gir ingen kandidatlenker å kontrollere. | bad_spec |
| Blind 6 OCR tusenskille | high: regex kan matche 1.25 fra 1.250,00; eksplisitt kopiering gir et feil beløpsforslag. | bad_spec |
| Blind 7 bildestrøm | medium: PNG IHDR/IEND uten IDAT og JPEG dimensjoner uten skann aksepteres. | bad_spec |
| Blind 8 OCR retry | low: feil gir bevarte originaler og manuell utfylling som uttrykkelig avtalt. Ny retry-UI er forbedring for sjeldne motor-/ressursfeil, ikke nødvendig for avtalt fallback; ekstra flate avvises i dette bygget. | reject |
| Blind 9 bekreftede felt | medium: bekreftet gren skjuler korrigert leverandør/KID/fakturanummer/dato; OCR er ikke de gjennomgåtte feltene. | bad_spec |
| Blind 10 fjernede varer | medium: removed=True utelukkes fra listen uten tilgang til eksisterende edit for gjenoppretting. | bad_spec |
| Edge 1 kvittering replay | medium: TripForm/ReceiptForm filtrerer confirmed=False før service-replay og avviser vellykket forespørsels kvittering. | bad_spec |
| Edge 2 recovery polling | high: recovered vises i tekst, men JS initialiserer dirty bare fra errorlist; gyldig bevart utkast kan reloades bort. | bad_spec |
| Edge 3 backup tmpfs | high: samme konkrete arkivproblem som Blind 1, verifisert i Compose og backup.ps1. | bad_spec |
| Edge 4 multipartgrense | high: DATA_UPLOAD_MAX_MEMORY_SIZE begrenser ikke filbytes; hele multipartfilen skrives før upload.read-grensen. | bad_spec |
| Gap 1 shopping JS | medium: reviewer verifiserte ingen atferdstest for refresh/dirty; server- og assettester dekker ikke tapt utkast. | patch |
| Gap 2 recovery HTTP | medium: reviewer verifiserte ingen stale POST/recovery-bekreftelsestest i nye dokument-/turvisninger. | patch |
| Repair review upload staging | medium: upload skriver ny storage_key før replay og returnerer deretter gammel Document; ordinære retries øker permanent fil-/backupvolum uten referanse. Kilde bekreftet. | bad_spec |

## Verification

- Sluttverdict: `work/documents-shopping-verdict.json` — godkjent teknisk verifikasjon av gjennomgang/manuell reserveflyt, med vesentlig OCR-begrensning. Ingen åpne implementasjonsblokkere. Eksakt feltgjenkjenning på de fem variantene består ikke; utydelige varelinjer kan skjule ellers tydelig sum/dato, og manuell utfylling kan være vanlig. Dette er ikke en garanti om automatisk pålitelig feltutfylling, fysisk kameratest, publisering eller separate budsjetter.

- Kamerakontrakten har egen beviskjede: `.project-init/documents-shopping-build-evidence.json` → `work/documents-shopping-verdict.json`. Den erstatter ikke eller omskriver historiske feilede OCR-diagnoser. Full regresjon før kvalitetsfilteret: 374 Django/PostgreSQL og 57 Node. Etter kvalitetsfilter og parserreparasjoner: målrettede dokument-/handle-/kameratester i `work/camera-final-regression.txt`.
- Faktisk nettleser kontrollerer bildevalg/forhåndsvisning/forkasting, mobilbredde, gjennomgang, duplikatkobling, manuell retting av feil/manglende beløp, eksplisitt utgift og ubetalt regning, to samtidige medlemmer med bevart utkast, og handleturens samme utgift etter reversering/gjenoppretting. Bilder er slettet før bekreftede felt vises; ingen fysisk telefonlukker er testet.
- Native arbeidertester dekker varige resultater før sletting, feil, avbrudd, utløp, foreldreløse filer, omstart og isolert backup/restore. Fem genererte OCR-varianter brukes som avgrenset diagnose, ikke målt nøyaktighet for ekte kvitteringsbilder. Lesende faktisk kildeavstemming og konfigurasjonskontroll er bevart. Separate budsjetter er fortsatt separat uferdig omfang.

- 2026-10-22: 338 PostgreSQL/Django-tester bestod etter hovedreparasjonene (176.884 s), deretter 24 målrettede dokumenttester etter siste upload-reparasjon. 53 Node-kontroller bestod. Endelig Docker-image bygget. Uavhengig reparasjonsreview bekreftet alle aksepterte funn rettet; siste fil-retry-reparasjon har separat etterkontroll uten gjenværende funn. Bevis: work/documents-shopping-post-review-tests.txt, work/document-upload-replay-tests.txt og work/documents-shopping-verification-checkpoint.json.
- Syntetisk containerutskifting bevarte bekreftet dokument/original/regningskobling og handleturens beløp/varer i faktisk nettleser. Lesende faktisk eieraudit bevarte 72 kilderader og identisk stateDigest. Dette er ikke full NAS-release eller implementasjon av nye separate budsjetter.

- `work/run-test-python.ps1 manage.py test budget.tests_documents budget.tests_shopping --keepdb --noinput`: alle nye kontrakttester består på separat PostgreSQL.
- Full `budget`-suite, eksisterende Node/Compose-kontroller, browserflyter og uavhengig kilde/runtime-review kreves før ferdigmelding.
- Reell OCR med syntetisk faktura/kvittering, feilet fil, omstart, duplikat og push-isolasjon; ingen mock alene beviser OCR.
