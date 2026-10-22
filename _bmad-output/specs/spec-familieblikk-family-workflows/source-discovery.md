# Kildeoppdagelse – 2026-10-22

Dette er lesende lokal kildekontroll, ikke runtime- eller NAS-verifikasjon. Brukeren har etterpå bekreftet at modulene er synlige etter at familievalgene ble lagret: synlighetsproblemet er løst. Bevar disse innstillingene og eksisterende funksjoner. Faktisk NAS-versjon er ikke undersøkt.

| Kilde | Faktisk situasjon | Gap til kandidaten |
|---|---|---|
| budget/models.py | FamilyRow har versjon/oppretter/familie. BillOccurrence er unik på template + due_date. Entry har én-til-én occurrence, unik familienøkkel/sekvens. Audit har object_id/operation/changes. | Dato er ikke stabil serieidentitet; ingen avbruddstilstand eller komplett gjenopprettingssnapshot. |
| budget/services.py:save_row/materialize_template | Serieendring bevarer i dag/tidligere og betalte forekomster; fremtidige ubetalte kan endres/slettes, også denne måneden. Materialisering sjekker forekomstens forfallsmåned. | Flyttet forfall kan gjenskape opprinnelig måned; nye regler må bruke stabil slot og bevare tombstones. |
| budget/services.py:delete_entry/pay_bill | Sletting fjerner Entry fysisk med bare kind i sletteaudit. Betaling har atomisk én aktiv kobling. Endring av koblet betaling krever angre først. | Ingen komplett gjenoppretting. Nye slettinger må bevares; historisk slettet innhold kan ikke antas rekonstruerbart. |
| budget/access.py | Faktisk policyfil; permissions.py/modules.py finnes ikke. Household låses før medlemskap lastes på nytt. safe_rows og relasjonspolicy finnes. | Gjenbruk og utvid policy for historikk, eksport og slettede objekter. |
| budget/forms.py / views.py | BillForm redigerer BillTemplate; slett gjelder Entry. | Egen forekomsthandling, versjonert arkivering og gjenoppretting mangler. |
| budget/templates/budget/bill_list.html | Merk betalt og Endre fremtidig serie. | Ingen forekomstmeny/historikk. |
| budget/templates/budget/more_refresh.html | Gjeld, Årsfond, Utland og Årsoversikt finnes. | Synlighet er bekreftet løst etter lagring av familievalg; videre oppdagelsesforbedring er kandidat, ikke modulombygging. |
| budget/urls.py | Ingen dokument/OCR/handleliste eller brukerrettet eksport-rute. | Nye trinn må designes og godkjennes. |

Familievalg i Household.modules styrer navigasjon. Membership.module_access styrer faktisk rettighet; administrator har moduladgang, manglende eldre nøkler betyr tillatt. Vanlig regningsbetaling arver bills fra forekomsten og krever ikke generell budget. Gjelds-/fondsregninger krever bills pluss debt/fund. Refusjon arver originalens tilgang. Årsoversikt krever annual + budget; full matrise krever alle finansmoduler. Ingen av disse valgene filtrerer familiens autoritative økonomi. Nye visninger må ikke lekke skjulte totalsummer, audit-snapshots, kategorier eller lenkede objekter.

Adopterte planleggingsdokumenter gir visuell/regnskapsmessig grunnkontrakt. Nyere context.md og aktuell access.py er autoritative for senere konto-, push- og rettighetsendringer; gamle forslag er ikke fornyet krav om e-postkode eller in-app-only varsling.
