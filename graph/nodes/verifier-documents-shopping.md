# Uavhengig verifikasjon — dokumenter og handleturer

## Oppgave
Undersøk implementasjon og faktisk runtime-bevis med fersk kontekst. Finn feil eller manglende dekning, særlig private dokumenter, duplikater og samtidige handleturer.

## Input
- `.project-init/documents-shopping-approval.json`
- `_bmad-output/implementation-artifacts/spec-documents-shopping.md`
- `_bmad-output/specs/spec-familieblikk-family-workflows/phased-scope.md`
- `.project-init/documents-shopping-build-evidence.json`
- Gjeldende kildekode/diff, testresultater og syntetiske runtime-bevis referert derfra.
- `work/documents-shopping-verification-plan.md`

## Output
`work/documents-shopping-verdict.json`: verdict, funn med fil/linje/bevis, kravdekning, begrensninger og utførte kontroller. Ingen private råverdier.

## Grenser
Lesende gjennomgang; ikke endre kode eller privat familie. Be om retting gjennom hovedagenten. Verifiser full native kravdekning, ikke bare grønne tester. Ubekreftet OCR, omstart, browserflyt eller tenantpolicy må merkes som manglende bevis.
