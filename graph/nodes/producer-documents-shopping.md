# Produsent — dokumenter og handleturer

## Oppgave
Implementer og verifiser de to brukeraksepterte familiearbeidsflytene i eksisterende app.

## Input
- `.project-init/documents-shopping-approval.json`
- `_bmad-output/implementation-artifacts/spec-documents-shopping.md`
- `_bmad-output/specs/spec-familieblikk-family-workflows/phased-scope.md`
- Eksisterende appkode og `rules.md`, `context.md`.

## Output
`.project-init/documents-shopping-build-evidence.json`: sporbar kvittering med full baseline/revisjon, kildehash, utførte kommandoer/resultater og gjenstående krav. Appkode og tester er implementasjonsarbeidet som kvitteringen dokumenterer. Ikke skriv private data i kvitteringen.

## Grenser
Ingen faktisk eiermutasjon, NAS-utrulling, commit/push eller globale pakker. Godkjente OCR-pakker bare i Docker. Nye tabeller/volumer må bevare eksisterende database- og push-identitet. Ikke erstatt reell OCR-/nettleserverifikasjon med mock-tester.

## Ferdigvilkår
Alle krav i native spesifikasjon har direkte bevis, økonomisk kobling og gjeldende rettigheter testes, privat før/etter-audit består. Produsentens egen rapport er ikke uavhengig godkjenning.
