# Produsent — separate budsjetter

## Input
- `context.md`, `rules.md`, `AGENTS.md`
- `_bmad-output/implementation-artifacts/spec-financial-areas.md`
- `.project-init/financial-areas-approval.json`
- Gjeldende appkode og tester.

## Oppgave
Fullfør separate budsjetter på tvers av alle finansflater. Bruk allerede akseptert visuell stil og godkjente regler. Eier styrer eget budsjett; eksplisitte lesere er skrivebeskyttet; administrator har ikke automatisk innsyn. Felles foreldreområde kan ha to redigerere. Felles handleliste har private betalingsdetaljer. Senere deling krever to ulike personer (eier og familieadmin). Kalender er fortsatt felles.

Eksisterende data skal ikke automatisk tildeles noen. Lag en eksplisitt, autentisert oppsettflyt med forhåndsvisning og bekreftelse for eksisterende familie. Før oppsett er nye medlems-/delingsendringer og finansaktivering blokkert; ingen implisitt innsynsutvidelse. Selvstendig ny familie og nye personlige budsjetter kan opprettes tomme med eksplisitte valg. Ingen mutasjon av faktisk lokal familie eller NAS under utvikling.

## Output og eierskap
Eier all nødvendig appkode, migrasjoner og tester for økonomiområder, inkludert maler. Skriv `.project-init/financial-areas-build-evidence.json` med konkrete kontroller, mangler og filkart. Ikke endre OCR-gjenkjenningsalgoritmen; den har separat ansvar. Du er ikke alene i checkout: bevar andres endringer.

## Grenser
Ingen nye avhengigheter, reelle datamigreringer, restore/import/seed, commit/push eller deployment fra produsenten. Hovedagenten håndterer autorisert publisering etter uavhengig verifikasjon. Bruk avgrensede syntetiske PostgreSQL-tester; ingen påstander om ferdig personvern uten dekning av alle innganger.
