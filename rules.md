# Project rules

- Norwegian Bokmål UI; NOK; Europe/Oslo month boundaries.
- Follow the approved scope in context.md; unresolved details remain labeled proposals.
- Ask before new dependencies, commits or pushes. BMAD 6.12.4 installation was explicitly authorized on 2026-10-20; project-local uv 0.13.3 installation was separately authorized and verified. Django 5.2.18, psycopg 3.3.6, Gunicorn 26.2.0 and required locked transitive dependencies were explicitly approved for .venv/Docker on 2026-10-20. Other new dependency installations still require approval.
- Conventional commits; never commit to main. Intended Git workflow: main, develop, codex/ feature branches. The private repository is Thugney/Familieblikk. Initial commit and push are explicitly authorized by Robel on 2026-10-20; verify actual remote refs and CI before declaring publication complete. Future commits/pushes still require authorization.
- No secrets committed. No credentials, provisioning, deployment, payment or bank integration implied.
- Mockups use fictional data and must visibly identify themselves as a design preview.
- Independent review and human acceptance precede app implementation. Keep Project Init gates honest.
- Actual workbook preservation and eventual own-household import are now explicitly authorized. All private sources, extracted records, owner email binding, reconciliation and runtime import receipts belong under gitignored private-data/. Do not publish/serve them, use them as a global seed, or claim completion before the actual authenticated family profile persists the data.


## Godkjent endring 2026-10-20 — forhåndsregistrert eier

Robel svarte på SMTP-/kodeavklaringen: «nei ikke kode bare pre-registered hvis det er greit for forst omgang». Dette endrer innloggingskravet for første eier: en eksplisitt lokalt forhåndsregistrert konto med passord kan eie familien og bekrefte kildeimport uten SMTP. E-postadressen er eierbinding fra brukerens instruksjon; den skal ikke feilaktig merkes e-postverifisert. Bevar separat opphavsmetode for kontoen/medlemskapet og autentisert passordøkt. Passord hasjes med Django, behandles privat, aldri i Git/image/logg. Ingen anonym tilgang, automatisk konto-overtakelse eller globale startdata. Eksisterende engangskodeflyt bevares for senere bruk. Privat kilde kan importeres bare til denne eksplisitt bundne eierens egen familie; idempotens, avklaring, avstemming, isolasjon og persistenskrav gjelder fortsatt. Ingen nye avhengigheter eller ekstern utrulling følger av endringen.


### Utvidelse av forhåndsregistrering — godkjent av Robel

«ikke bare meg men som admin jeg kan også registrere familien og andre familie». Familieadministratorer kan opprette egne familiemedlemmer med passord uten e-postkode. Den eksplisitt klargjorte eieren får en separat registreringsrett til å opprette andre private familier med egen administrator. Registreringsrett gir ikke budsjettinnsyn eller medlemskap i de andre familiene. Vanlige medlemmer kan ikke registrere brukere; andre familieadministratorer kan bare administrere egen familie med mindre separat registreringsrett gis eksplisitt. Eksisterende kontoer overtas ikke, og én familie per bruker gjelder. Nye familier starter tomme; Robels kilde er fortsatt bare hans egen familie. Gjeldende passordregler, CSRF, økter, feilforsøksgrenser og hemmelighetsgrenser gjelder alle forhåndsregistrerte kontoer.
