# Foreslåtte beregningsregler for forbruk og planutkast

Disse A1–A4-presiseringene er designforslag. Eksisterende `budget/services.py` skiller ordinære utgifter, sparing, gjeld og årsavsetninger; dette forslaget oppretter ingen ny faktisk kontantmotor. `budget/views.py` begrenser i dag oversikten til seks kategorier før utvidelse. Ny kandidat skal gjøre hele grunnlaget forståelig og synlig.

## Forbruk og perioder

Forbruk = bekreftede ordinære utgifter og utenlandsoverføringer i NOK minus tilknyttede ordinære refusjoner på effektive datoer i perioden. Sparing/uttak, gjeldsbetalinger og fondsbetalinger vises separat som disponering, ikke som kategoriens ordinære forbruk. Refusjoner i valgt periode reduserer nettoforbruk selv om originalen er eldre. Negativ nettokategori vises som netto tilbakebetaling, ikke skjult eller klippet til null i totalsummen. Fordelingsgrafen må derfor støtte separat tekstet negativ del; prosenter er aldri eneste forklaring.

Måned/år inkluderer datoer fra første til siste dag i valget; inneværende periode merkes «til i dag» og tar ikke med fremtidige faktiske poster som om de allerede var skjedd. Tre måneder foreslås som valgt måned og de to foregående; egendefinert har inkluderende start/slutt. Samme dato-, kategori- og tekstfilter gjelder treff, detaljer og graf. Overlappende valg må ikke telle én post flere ganger. Oppsummeringen oppgir filter og tidsrom, og «Nullstill filtre» gjenoppretter forståelig standard. Søking reagerer på tekstendring med kort forsinkelse for å unngå unødige kall; eksakt forsinkelse er implementasjonsvalg, ikke et nytt brukerkrav.

Bekreftet null er ikke det samme som manglende/ufullstendig måned. Årsgrafen viser manglende dekning separat og kan nå alle kategorier uten topp-N-dropp. Inntekt har egen visning/etikett; dersom samlet kontantstrøm vises, må klassene skilles og avstemmes med eksisterende kontantresultat, ikke fremstilles som ordinært forbruk.

## Historisk forslag

Brukeren velger én eller flere avsluttede kildemåneder. Per variabel kategori beregnes aritmetisk gjennomsnitt av bekreftet netto ordinært forbruk for disse månedene; vis månedene, antall observasjoner og ufullstendighetsmerke. Uavklarte importutkast gir ingen beløp, men deres eksistens vises som forbehold. Ingen registrering er ikke automatisk en bekreftet nullmåned: dekningsstatus må avklares eller verdien legges inn manuelt. Sparsomt grunnlag gir et redigerbart forslag med advarsel, ikke anbefalt økonomisk fasit. Negativt gjennomsnitt kan vises som historisk netto tilbakebetaling, men gir ikke automatisk en negativ forbruksramme. Valgt historikk erstatter aldri faktiske poster eller gamle rammer.

## Neste måneds plan

Foreslått enkel rest: `forventet inntekt − ordinære faste forpliktelser − øvrige kategoriplaner − fast sparing − gjeldsplan − fondsavsetning/top-up = planlagt rest`. Dette er forventet månedsdisponering, ikke dagens tilgjengelige beløp. Manglende inntekt eller nødvendig planbeløp gir «Fyll ut grunnlaget»; kjent null må bekreftes eksplisitt. Negativ rest beholdes med tekst og redigeringsvei. Intet tidligere fritt overskudd legges til.

Hver planlinje har ett formål og én klasse. En gjentakende ordinær regning inngår som fast forpliktelse; kategoriens øvrige plan må ekskludere den allerede dekkede delen. Vis dette skillet i kategoridetaljen før resten summeres. Gjeld/fond tas som egne planer og ikke også som ordinær regning/kategoriplan. Sparing er planlagt avsetning én gang; faktiske innskudd/uttak er ikke ekstra prognoseposter som legges på samme plan. Eksisterende underfinansiering/gammel forpliktelse vises eksplisitt med kilde og én klassifisert planlinje, uten å bli stille gjettet inn. Et eksisterende fondsbeløp er ikke inntekt og fondsbetaling må ikke også bli fullt ordinært trekk.

Hver foreslått verdi merkes eksisterende plan, bekreftet forpliktelse, valgt historikk eller manuelt beløp. Utkastet kan endres og avbrytes uten dataendring. Familien kan drøfte det, men administrator må eksplisitt bekrefte riktig målmåned og endringsoversikt før eventuell fremtidig lagring. Samtidig endret målplan gir konflikt og ny avstemming, ikke stille overskriving. Lagring oppretter/oppdaterer bare godkjente målplaner og forventninger; ingen bokført inntekt, utgift eller importpost opprettes av planbekreftelsen. Eksisterende målplan-/inntektsmodell må avstemmes før implementering.

Kontrollgrunnlag for senere kandidat: mer enn seks utgiftskategorier, refusjon på tvers av måneder, ufullstendig kildemåned, manglende inntekt, dobbelt regnings-/kategoritrekk, sparemålplan med faktisk innskudd, avbryt og admin-versjonskonflikt. Ingen av disse kontrollene er utført som del av spesifikasjonen.
