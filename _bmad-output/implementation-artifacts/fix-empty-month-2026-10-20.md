---
title: Rett tom måned i oversikt og skjemanavigasjon
type: bug
status: done
created: '2026-10-20'
---

Brukeren rapporterte 404 på `/app/oversikt/?month=`. Manglende, tom eller bare blank månedsverdi skal velge inneværende måned i Europe/Oslo. Gyldig historisk `YYYY-MM` skal bevares; ugyldige ikke-tomme verdier skal fortsatt avvises.

Skjemasider manglet måned i mal-konteksten og genererte tomme menylenker og månedsfelt. Grunnmalen beregner nå en lokal standardmåned for disse sidene. Ingen innlogging, beløp eller kildeklassifisering endres.

Endringer: `budget/views.py`, `budget/templates/budget/base.html`, `budget/tests/test_month_navigation.py`.

Verifisert: alle 57 Django/PostgreSQL-tester består. Faktisk Docker-app er kontrollert med tom, manglende og blank månedsverdi, innsending av tomt månedsfelt, skjemanavigasjon ved 390/1440 px, historisk september og ugyldig måned. Faktiske eierdata er avstemt uendret. Uavhengig gjennomgang har ingen funn. Lokale kvitteringer: `work/empty-month-browser.json` og `work/empty-month-review.json`.
