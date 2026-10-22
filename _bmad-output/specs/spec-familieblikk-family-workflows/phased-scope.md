# Senere trinn og bevaring av inntaket

Trinn 2 og 3 er bevart forslag etter trinn 1, med egen konkret designkandidat/aksept før bygging. Lokal behandling og eksplisitt bekreftet utgift per handletur er allerede avklart.

## Trinn 2 – faktura og kvittering

Ta bilde eller last opp PDF/JPEG/PNG. Lagre original privat på Synology og kjør lokal tekstgjenkjenning. Vis original sammen med redigerbart forslag: leverandør, beløp, dato/forfall, fakturanummer/KID når lesbart og kategori. Usikker/mislykket gjenkjenning går til manuell retting; aldri gjett eller bokfør automatisk. Faktura oppretter ubetalt regning først ved eksplisitt bekreftelse. Kvittering kan kobles til eksisterende post eller betalt regning fremfor å lage ny.

Dokument, utkast og jobb tilhører familie og følger dokumentmodul samt den koblede postens gjeldende modultilgang. Privat nedlasting krever autorisasjon; aldri offentlige statiske URL-er. Valider filtype/innhold/størrelse og begrens bilde/PDF-ressurser; konkrete grenser og oppbevaring må vedtas i trinnets design. Eget persistent dokumentlager inngår i backup og vanlig oppdateringskontroll. Lokal OCR-jobb må ha separat kapasitet fra pushkø slik at fungerende varsler ikke blokkeres.

Duplikatvern omfatter hele faktura → regning → betaling → kvittering → handletur. Eksakt filhash alene er utilstrekkelig: nytt bilde kan være samme dokument. Kombiner eksisterende koblinger og dokumentets bekreftede kjennetegn; vis kandidatduplikat til mennesket før ny opprettelse. Idempotens hindrer dobbeltklikk; usikker likhet må aldri automatisk slå sammen eller slette data.

**P2 aksept:** upload/OCR alene lager null økonomiske poster; bekreftet faktura gir én ubetalt regning; kvittering koblet til allerede betalt original gir null ekstra utgift. Retry og nytt bilde viser eksisterende kjede/duplikatvarsel. Annen familie/revokert tilgang får ingen original, OCR-tekst eller dokumentmetadata. Omstart bevarer dokument og lenke; OCR-feil hindrer ikke push.

**Åpent:** OCR-motor, fast versjon og ressurser verifiseres mot faktisk Synology-modell før konkret installasjonsgodkjenning. Ingen ny dependency er valgt/godkjent. Handoffens Tesseract-kilde er begrunnelse for prøving av bildekvalitet, ikke motorvalg; Django-kilden begrunner privat og validert brukeropplasting.

## Trinn 3 – felles lister og handleturer

Flere delte lister har vare, antall, valgfri pris/kategori og kjøptstatus, synkronisert mellom tillatte familiemedlemmer med konfliktkontroll. Avkryssing betyr kjøpt; liste/kvitteringsutkast påvirker ingen utgift. «Fullfør handletur» krever faktisk dato, beløp, én hovedkategori og valgfri kvittering før én utgift opprettes. Estimerte varepriser erstatter ikke bekreftet total.

Vis tur↔utgift begge veier. Gjentatt bekreftelse returnerer samme utgift; retting/angre følger den felles posthistorikken. Kvittering lagt til senere kobles til eksisterende utgift; avvikende beløp krever uttrykkelig retting og kan ikke skape ny bokføring. Flere butikker er separate turer i første kandidat. Kvitteringslinjer og kategorisplitting er senere forslag uten godkjent omfang.

Egen administrert handlelistetilgang gir ikke budsjett- eller dokumenttilgang. Separat budsjettadgang kreves for å opprette/se utgiften; separat dokumentadgang og lenket postpolicy kreves for kvitteringen. Vis ingen skjulte beløp, dokumentmetadata eller økonomisk lenkeinnhold via listen. Rettigheter revurderes ved fullføring og replay, ikke bare når listen åpnes.

**P3 aksept:** to medlemmer ser kjøptstatus; avkryssing og utkast gir null poster. Samtidig fullføring/retry gir én utgift og entydig turkobling. Sen kvittering gir null ekstra utgift; beløpsendring krever bekreftet retting med historikk. Listetilgang alene gir verken utgiftsoppretting eller finans-/dokumentinnsyn. Angre/gjenopprett og omstart bevarer koblingene uten duplikater.

## Godkjenningsgrense og kildedekning

Handoffens trinn 1 dekkes av CAP-1–4, bill-corrections.md og AT-01–15. Trinn 2 dekkes av CAP-5/P2; trinn 3 av CAP-6/P3. Alle avgrensninger er tatt inn i SPEC/companions: ingen bank, ekstern OCR, automatisk bokføring, dependency, commit/push eller NAS-utrulling; private data og eksisterende UI bevares. Kildeaudit er lokal kodekontroll, ikke faktisk runtime. Historisk sletting kan ikke rekonstrueres uten data.

Wrapper-only content: handoffens chatbytte og tidligere verifikasjonskvittering er prosessmetadata; de gir verken ny produktfunksjon eller godkjenning av denne kandidatens detaljer. Ingen åpne produktpåstander er droppet.
