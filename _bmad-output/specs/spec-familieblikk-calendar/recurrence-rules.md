# Foreslåtte gjentakelses- og tidsregler

Disse reglene presiserer CAP-2–CAP-4 og CAP-6–CAP-7 for preview og senere testplan. A2–A3 er forslag, ikke brukerens godkjente detaljer.

## Dato og tid

Tidsavtale har lokal start og slutt i Europe/Oslo; slutt må være etter start. Heldag har startdato og siste inkluderte dato, minst én dag. Visningen inkluderer en avtale når dens tids-/datospenn overlapper valgt visningsperiode, også over månedsskifte. Sted og notat er valgfri ren tekst; ingen vedlegg eller aktivt HTML-innhold.

Ukentlig gjentakelse følger opprinnelig ukedag, månedlig følger opprinnelig månedsdag. En tidsserie beholder lokalt start-/sluttklokkeslett og relativ sluttdag; ikke et fast UTC-klokkeslett. En vårtid som ikke finnes, eller et høstklokkeslett som forekommer to ganger, må vises som en avklaring før lagring: vårtid korrigeres eksplisitt, høsttid velger eksplisitt tidligere/senere UTC-offset. Ingen stille forskyvning. Heldag påvirkes ikke av sommertid.

## Månedsslutt og serieavslutning

Opprinnelig dag beholdes som anker: 31. januar → 28. februar (29. i skuddår) → 31. mars. Vis teksten «Månedlig den 31.; siste dag i kortere måneder». Ukentlig serie hopper syv lokale kalenderdager. Sluttdato er valgfri og inkluderer forekomster som starter på datoen; den kan ikke være før seriens start. Uten sluttdato beregnes bare det avgrensede synlige datointervallet; ingen uendelig fremtidig materialisering kreves.

## Endre eller slette

Enkeltavtale endres/slettes direkte med bekreftelse. Serie gir eksplisitt valg «Bare denne avtalen» eller «Denne og fremtidige». Enkeltendring er et unntak knyttet til originalforekomstens identitet, og oppretter ikke både original og flyttet avtale. Enkeltsletting skjuler bare den valgte forekomsten, også etter ny innlasting. Fremtidig endring starter ved valgt originalforekomst; tidligere forekomster/unntak bevares. Fremtidig sletting avslutter serien før denne forekomsten. Endret serie beholder samme oppretter- og familierettigheter; en datoendring gir ikke ny eier.

Bekreftelsen oppgir omfang og valgt skjæringsdato. Et flyttet unntak avgjør omfang etter originalforekomst, ikke sin nye dato. Ved fremtidig endring skal eksisterende fremtidige unntak vises før bekreftelse; foreslått regel er å erstatte dem i den berørte delen, mens tidligere unntak bevares. Avbryt er uten effekt. Sletting eller redigering fra et annet medlem avvises også hvis handlingen sendes direkte. Gjenforsøk og samtidige endringer kan ikke duplisere forekomster eller overskrive uten konfliktmelding.

## Kontrolltilfeller etter godkjenning

Demonstrer månedlig 31. i februar/mars, ukentlig klokkeslett over begge sommertidsskifter, heldag over månedsskifte, flyttet enkelthendelse uten dublett og fremtidig redigering/sletting med bevart fortid. Gjenta med administrator, oppretter, annet medlem og fremmed familie. Dette er planlagte kontroller, ikke utførte tester.


## Deltakere og kalendervisninger

Bekreftet funksjon: medlemmenes egne kalendere og felleskalenderen er lesbare for alle i husholdningen. En avtale opprettes enten i fellesomfang eller med valgte husholdningsmedlemmer; samme kanoniske forekomst vises i hver valgt persons kalender og i samlet familieoversikt. Deltakertilordning gir rett til eget deltakelsessvar etter CAP-7, men ingen rett til å redigere avtalen eller svare for andre. Serveren avviser ugyldig deltaker fra annen familie; ingen delvis avtale eller deltakerkobling lagres.

Foreslått A4: «Alle» viser union, «Felles» bare fellesomfang og en person bare sine tilordnede avtaler. Eventuelt flervalg av personer viser unionen én gang per kanonisk forekomst. Skjemaets eksplisitte valg mellom «Felles familieavtale» og «Valgte familiemedlemmer» krever minst én gyldig deltaker i personomfang. Oppretteren velges bare hvis brukeren faktisk inkluderer vedkommende; valget påvirker ikke eierskap. Fellesomfang og deltakeromfang blandes ikke stille. Alle kan fortsatt lese begge typer gjennom relevant kalenderfilter.

Endring av deltakere eller felles-/personomfang bruker samme «Bare denne avtalen» / «Denne og fremtidige» som øvrig serieendring. Et enkelt unntak erstatter forekomstens deltakere uten å kopiere hendelsen; fremtidig endring bevarer tidligere tilordninger. Fjernet deltaker mister bare forekomstens plass i personfilteret, ikke familiens leseadgang til hendelsen. Oppretter-/administratorrett beholdes, også når oppretteren ikke er deltaker. Kontrolltilfellet med to deltakere skal vise én forekomst i Alle og samme identitet i begge personkalendere, og et vanlig deltaker-medlem skal få avslag på direkte redigeringsforsøk.

## Deltakelsessvar

Bekreftet utvidelse: familien ser hvem som har svart «Passer», «Passer ikke» eller «Ikke svart». På fellesavtale er alle nåværende medlemmer svarberettiget; på personavtale er bare de valgte deltakerne det. Alle i familien kan lese svarene. Medlemmet kan endre sitt eget svar eller tilbakeføre det til «Ikke svart». Administrator og oppretter svarer bare for seg selv, selv om de kan endre avtalen. Samme husholdnings- og deltakerkontroll håndheves av serveren ved hver svarhandling; ingen endepunktparameter kan brukes til å utgi seg for et annet medlem. Gjentatt innsending gir én status, ikke en ny kopi av avtalen eller svaret. Ingen «Kanskje»-status, ekstern svarlenke eller varslingslevering inngår.

Foreslått A5: Svaret gjelder kanonisk forekomst + medlem, også for en gjentatt serie. Flytting av forekomsten beholder dens identitet, men dato-/tids-/heldagsendring nullstiller svarene på denne berørte forekomsten. Endring av deltakere eller felles-/personomfang nullstiller også berørte svar. Ved «Denne og fremtidige» gjelder nullstillingen bare de endrede forekomstene fra den valgte originalforekomsten fremover; tidligere forekomster/svar bevares. Bekreftelsen viser at svar nullstilles til «Ikke svart» før lagring; avbryt beholder alt. Tittel-, sted- og notatendring alene beholder svarene. Denne nøyaktige nullstillingspolitikken er designforslag til menneskelig vurdering.

Et nytt valgt medlem starter «Ikke svart». Nytt husholdningsmedlem er svarberettiget på synlige fellesforekomster med «Ikke svart»; det tilskrives aldri et annet medlems svar. Fjernet deltaker kan ikke svare videre på personforekomsten. Eventuell historisk svarlagring ved medlemsfjerning må bevare husholdningsisolasjon; medlemslivssyklus følger eksisterende regler og gir ikke grunnlag for en ny konto-/invitasjonsflyt.

Kontrolltilfeller: Medlem svarer og ombestemmer seg, et annet familiemedlem leser endringen, administrator får avslag på svar på vegne av medlemmet, fremmed familie får avslag, og datoendring viser/bekrefter berørt svarnullstilling uten å endre fortid. Dette er spesifiserte kontroller, ikke utførte backendtester.

## Implementert lokalt – verifikasjon 2026-10-20

Denne statusen erstatter tidligere «venter på vurdering» for kalenderens A1–A5. Historisk menneskelig aksept er `.project-init/calendar-human-acceptance.json` med «Ja, bygg kalenderen inn nå»; kandidatens hashverdier er historiske og er ikke endret til å passe denne senere dokumentrevisjonen. CAP-1–CAP-7 er bevart. Forbruks-/planleggingsdesign ble senere godkjent separat med «ja»; se .project-init/spending-planning-human-acceptance.json og den native implementeringsoppgaven spec-spending-planning-runtime.md.

`work/calendar-runtime-verification.json` rapporterer 106 beståtte Django/PostgreSQL-tester, seks Node-tester, 20 bevaringstester, 45 syntetiske nettleserkontroller og 87 faktiske eierkontroller, konsistent migrasjon 0009 og lokal Docker-oppstart. `work/calendar-docker-browser.json` dokumenterer opprettelse, lesing, svar og sletting i en eksisterende syntetisk familie på port 4180 uten å endre eierens kalender eller budsjett. Dette avsnittet gjengir inspiserte mottak; spesifikasjonsprodusenten kjørte ikke testene på nytt.

`work/calendar-runtime-review.json` har `pass_source_review`, ingen blokkere og beskriver rettede tilgangs-, RSVP-, serie-, frakoblings- og midnattssømmer. Reviewerens egen kildegjennomgang omfatter ikke personlig gjenkjøring av databasetester. Mottaket beskrev 43 syntetiske kontroller før den siste kosmetiske kontrollen, mens samlet runtime-mottak beskriver 45. Endelig kosmetisk mottaksoppfriskning eies av orkestratoren. Dette er ingen påstand om at alle eldre Project Init-visualdekningsgater er grønne.

Implementert datointervall er 1900–2199, lest fra `budget/calendar_services.py`; start/slutt og listeintervall valideres. «Denne og fremtidige» kan ikke flytte seriens nye start før valgt originaldato: handlingen avvises for å bevare fortid og entydig kanonisk identitet. «Bare denne avtalen» kan fortsatt flyttes bakover. UI-hjelpen forklarer forskjellen. Ved fremtidig metadataendring avstemmes tidligere forekomstunntak før RSVP videreføres; materielle forskjeller nullstiller de berørte svarene. Tidsavtale som slutter nøyaktig ved midnatt vises ikke feilaktig som aktivitet neste dag.

Ingen ny avhengighet, commit, push eller NAS-utrulling følger av statusoppdateringen. Ingen appkode, budsjettprototype eller ny forbruks-/planleggingskandidat er endret av denne produsenten.
