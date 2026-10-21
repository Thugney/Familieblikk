
- source_spec: `_bmad-output/implementation-artifacts/spec-familieblikk-budget-ux.md`
  summary: Vurder å beholde relevante postfiltre ved bytte av måned.
  evidence: Eksisterende månedsvelger sendte allerede bare month før rettelsen. Paginering og nullstilling bevarer valgt måned; månedsbytte med filtre er separat, tidligere atferd.


- source_spec: `spec-calendar-web-push.md`
  summary: Undersøk automatisk abonnementserstatning og langtidsutløp på fysiske nettlesere/enheter.
  evidence: Uverifisert medium risiko fra BH5; dagens utløps-/410- og nyaktiveringsflyt er testet, men reelt pushsubscriptionchange og leverandørbytte er ikke observert. En fysisk langtids-/abonnementsbyttetest må vise om en aktiv binding endres uten synlig veiledning.
