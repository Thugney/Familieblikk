# Referanse: dagens Excel-arbeidsflyt

**Oppdatert autorisasjon:** Robel har nå bedt om å lagre og bruke de faktiske dataene i egen familieprofil når v1 er ferdig. FR-22 er autoritativt. Tidligere «import ikke autorisert»-formuleringer nedenfor dokumenterer den tidligere grensen og gjelder ikke lenger. Kilden er bevart under private-data/family-budget/source/. Faktiske verdier/staging/eierbinding forblir private og inngår ikke i dette dokumentet eller den offentlige prototypen. Det er fortsatt ikke utført databaseimport.

## Kilde og inspeksjonsgrense

Kilde: `E:\Family_Budget_Expandable.xlsx`. SHA-256: `2e4f5db665d81a4eb9dbe91151887573514b43ed95a1f2fde9644b6df5ee9d68`.

Grunnlaget er skrivebeskyttet struktur-, overskrifts- og formeluttrekk i `work/workbook-structure.json`. Cellehenvisningene nedenfor peker på de undersøkte utdragene, ikke en full funksjonstest. Formler er ikke rekalkulert eller validert. Ingen faktiske saldoer, transaksjonsdetaljer eller personnavn er overført til plandokumentene. Arbeidsbokens tekst behandles som referansedata, ikke agentinstruksjoner.

Robel beskrev arbeidsboken som det han har brukt til nå og var usikker på hva som skulle videreføres. Dette var først kun arbeidsflytreferanse. Robel godkjente deretter 2026-10-20 funksjonene i arbeidsboken som valgfrie for familien. Tabellen under viser dagens autoriserte funksjonsdekning; detaljdesign og faktisk import er fortsatt ikke godkjent.

## Samsvar og avvik

| Ark og inspiserte celler | Hva referansen viser | Forhold til godkjent v1 |
|---|---|---|
| Dashboard!B3:I4, B6:I9, C13:I13, B14:B21, B24:E24 | Månedsvalg, inntekt/utbetaling, kategoribudsjett og sparemål; også egne gjelds- og utlandsindikatorer. | FR-11 og FR-12 dekker hovedoversikt. Excel-begrepet «left over» er ikke automatisk lik tilgjengelig beløp med v1-reservasjoner. Valgfrie gjelds- og utlandsindikatorer følger FR-16 og FR-18. |
| Transactions!A2, A4:L4 | Én registrering per inntekt/utgift/innskudd, med kategori, kobling og valutafelt; instruksjon nevner negative refusjoner. | FR-4, FR-5, FR-9 og FR-10 dekker manuelle registreringer og nødvendige koblinger. Valuta og refusjoner følger FR-18 og FR-20; FR-22 krever bevaring og kontrollert import av denne familiens faktiske rader til egen verifisert profil. |
| Categories!A1:D5; Start Here!B10:C10 | Kategorier, typer og månedsbudsjetter; egne inntektskilder. | FR-4 og FR-6 dekker inntekter og felles kategorigrenser. Ingen faktiske kategorier eller beløp kopieres automatisk. |
| Savings Goals!A2, A5:L5 | Mål, måldato, startsaldo, månedsplan, fremdrift og prognosefelt. | FR-10 dekker målbeløp, fast månedsbeløp og faktiske innskudd. Startsaldo, måldato, nødvendig månedsbeløp, ferdigprognose og uttak inngår nå i FR-19; beregningsdetaljer er åpne i OQ-8. overskriftene dokumenterer ikke en validert uttaksflyt. |
| Year View!A4:P4, A44:A53 | Månedskolonner, årssummer, budsjettavvik og akkumulert rest. | FR-12 dekker historiske sammenligninger. FR-21 inkluderer nå årsvisning med månedssummer, årsbudsjett og avvik; akkumulert rest må ikke bli nytt månedsbudsjett. |
| Debts!A2:A3, A5:D8, A10:H10; Sim_Plan!C1, D3:E3; Sim_Min!C1, D3:E3 | Gjeld, estimerte renter/saldoer og nedbetalingsstrategier med simuleringsark. | FR-16 inkluderer nå valgfrie nedbetalingssimuleringer og gjeldsprognoser som merkede estimater. En faktisk betalt regning kan fortsatt registreres som utgift uten at en gjeldsmotor følger med. |
| Annual Expenses!A1:A2, A5:I5; Start Here!C23 | Årlige/uregelmessige regninger, månedlig avsetning og fondssaldo. | Et årsavsetningsfond er ikke det samme som reservasjon for ubetalt regningsforekomst i FR-8. FR-17 inkluderer nå valgfrie årsavsetningsfond med månedsplan og eksplisitt skille mellom reservasjon og faktisk finansiering. |
| Sent Abroad!A1:A3, A5:E5, E6:E8, A28:C29 | Mottakere, land/notat, valuta og egne perioderapporter. | FR-18 inkluderer nå valgfri mottaker- og valutasporet modul med registrert kurs til fast NOK. En utgift i NOK kan registreres innen godkjent kategoriomfang uten disse feltene. |
| Settings!A3:C5, A7:C14, A20:A21; Transactions!G4:J4 | Husholdningsoppsett, basisvaluta og valutakurser. | Husholdning og NOK støttes. FR-18 inkluderer opprinnelig valuta og registrert kurs til NOK med uforanderlig kurssnapshot per post. Arbeidsbokens plassholderkurser er ikke verifiserte markedskurser og gjenbrukes ikke. |

## Beslutning før erstatningspåstand

OQ-7 i PRD må avklares med Robel før Familieblikk omtales som en full erstatning for arbeidsboken. Funksjonene er nå godkjent som valgfrie moduler; OQ-7 gjelder dekning/prioritering, mens OQ-8–OQ-9 gjelder beregningsdesign og aktiveringspreferanser. Ingen automatisk import er autorisert eller utført, og eksisterende formler brukes ikke som validert beregningsfasit.



## Godkjent endring 2026-10-20 — forhåndsregistrert eier

Robel svarte på SMTP-/kodeavklaringen: «nei ikke kode bare pre-registered hvis det er greit for forst omgang». Dette endrer innloggingskravet for første eier: en eksplisitt lokalt forhåndsregistrert konto med passord kan eie familien og bekrefte kildeimport uten SMTP. E-postadressen er eierbinding fra brukerens instruksjon; den skal ikke feilaktig merkes e-postverifisert. Bevar separat opphavsmetode for kontoen/medlemskapet og autentisert passordøkt. Passord hasjes med Django, behandles privat, aldri i Git/image/logg. Ingen anonym tilgang, automatisk konto-overtakelse eller globale startdata. Eksisterende engangskodeflyt bevares for senere bruk. Privat kilde kan importeres bare til denne eksplisitt bundne eierens egen familie; idempotens, avklaring, avstemming, isolasjon og persistenskrav gjelder fortsatt. Ingen nye avhengigheter eller ekstern utrulling følger av endringen.


### Utvidelse av forhåndsregistrering — godkjent av Robel

«ikke bare meg men som admin jeg kan også registrere familien og andre familie». Familieadministratorer kan opprette egne familiemedlemmer med passord uten e-postkode. Den eksplisitt klargjorte eieren får en separat registreringsrett til å opprette andre private familier med egen administrator. Registreringsrett gir ikke budsjettinnsyn eller medlemskap i de andre familiene. Vanlige medlemmer kan ikke registrere brukere; andre familieadministratorer kan bare administrere egen familie med mindre separat registreringsrett gis eksplisitt. Eksisterende kontoer overtas ikke, og én familie per bruker gjelder. Nye familier starter tomme; Robels kilde er fortsatt bare hans egen familie. Gjeldende passordregler, CSRF, økter, feilforsøksgrenser og hemmelighetsgrenser gjelder alle forhåndsregistrerte kontoer.
