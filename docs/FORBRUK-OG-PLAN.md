# Forbruk og månedsplan

Åpne **Budsjett** for Forbruk, Årsoversikt og Planlegg neste måned. De samme verktøyene finnes på Oversikt. Kalenderen ligger i menyen Kalender.

Forbruk viser registrerte ordinære utgifter og utenlandsoverføringer minus refusjoner på refusjonsdatoen. Søk oppdateres automatisk; velg én eller flere kategorier og måned, tre måneder, år eller egne datoer. Trykk på en kategori for graf, poster og flere sider med detaljer. Alle kategorier med treff vises. Inntekt vises separat. Sparing, gjeld og årsavsetninger følger sine egne planer.

Årsoversikten viser registrert aktivitet måned for måned og kan filtreres per kategori. Manglende grunnlag vises som ukjent. Appen har ingen bekreftelse på at en hel måned er ferdig registrert; også historiske måneder merkes derfor ufullstendige. Uavklarte importutkast inngår ikke i beløpene.

## Planlegg fremover

Velg en fremtidig målmåned. Legg inn forventet samlet inntekt, se faste forpliktelser og juster kategori-, spare-, gjelds- og fondsbeløp. Forventet inntekt i planen er separat fra mottatt inntekt. Tidligere måneders frie overskudd overføres ikke.

Du kan velge avsluttede kildemåneder og bruke historiske forslag etter gjennomgang. Forslag krever registrerte kategoriobservasjoner i hver valgt måned; manglende observasjoner blir ukjente beløp. Tomt felt betyr ukjent. Skriv 0 når dere bevisst ikke vil sette av penger til en linje. Begrenset datagrunnlag må gjennomgås og bekreftes.

Planlagt rest = forventet inntekt minus ordinære faste regninger, øvrig kategoriforbruk, sparing, gjeldsplan og fondsavsetning/påfyll. Ordinære regninger inngår én gang. Gjeld tar hensyn til kjente forpliktelser. Fondsberegningen tar hensyn til eksisterende saldo og eldre reservasjoner. Et negativt resultat vises som underskudd.

Alle familiemedlemmer kan se og drøfte utkast. Bare administrator kan lagre, etter en egen gjennomgang av målmåned og beløpsendringer. Lagring endrer bare den bekreftede målmånedens planer og forventning. Den oppretter ingen bokført inntekt, utgift eller spareinnskudd. Samtidige endringer krever ny avstemming; gjentatte identiske lagringsforsøk gir samme kvittering.

Når en senere måned åpnes, kan appens eksisterende regel for videreføring bruke disse beløpene som utgangspunkt der måneden ikke har en egen plan. Lagringen skriver ingen andre måneder umiddelbart. Forventet inntekt i månedsplanen må fortsatt settes særskilt for hver måned.

Ulagrede beløp beholdes i den åpne siden ved nettfeil. Lagring krever nett. Utkast lagres ikke i nettleserens lokale lagring; lukking eller oppfrisking kan miste det. Kategoriadministrasjon og eksisterende postskjema finnes via egne lenker.

## Teknisk kontroll

De nye forbruks-/planleggingsendepunktene og planforhåndsvisningen leser grunnlaget uten å opprette regninger eller månedsplaner. Den eksisterende generelle Oversikt-ruten beholder sin tidligere månedsforberedelse; dette er ikke endret til en global garanti om skrivefrie GET-kall.

Målplan lagres atomisk med familielås, administratorrolle, kildeversjon og idempotens. Historikk, faktiske poster, kalender og private importrader endres ikke. Private data og hemmeligheter er fortsatt utenfor Git og Docker-image. Lokal Docker-verifikasjon dokumenteres i `work/spending-runtime-verification.json`; NAS-utrulling og publisering av disse endringene er ikke utført.
