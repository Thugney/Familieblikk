
- source_spec: `_bmad-output/implementation-artifacts/spec-familieblikk-budget-ux.md`
  summary: Vurder å beholde relevante postfiltre ved bytte av måned.
  evidence: Eksisterende månedsvelger sendte allerede bare month før rettelsen. Paginering og nullstilling bevarer valgt måned; månedsbytte med filtre er separat, tidligere atferd.


- source_spec: `spec-calendar-web-push.md`
  summary: Undersøk automatisk abonnementserstatning og langtidsutløp på fysiske nettlesere/enheter.
  evidence: Uverifisert medium risiko fra BH5; dagens utløps-/410- og nyaktiveringsflyt er testet, men reelt pushsubscriptionchange og leverandørbytte er ikke observert. En fysisk langtids-/abonnementsbyttetest må vise om en aktiv binding endres uten synlig veiledning.
- source_spec: `_bmad-output/implementation-artifacts/spec-background-calendar-alerts.md`
  summary: Bekreft fysisk bakgrunnsvarsel på autorisert Windows- og Android-enhet etter NAS-oppdatering.
  evidence: Arbeider/kryptering og faktisk serviceworker er verifisert med simulert leverandørtransport; NAS-worker kjører ifølge brukerens ps-utdata. Faktisk leverandøraksept og OS-visning på brukerens enheter med lukket app er fortsatt uobservert og vil avklare eventuell leveringsfeil.
