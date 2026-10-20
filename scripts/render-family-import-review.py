"""Produce a local-only, escaped review of actual imported source data."""
from pathlib import Path
from html import escape
import json

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'private-data/family-budget'
def text(v):
    return escape(str(v)) if v is not None else '—'
def money(v):
    if v is None:
        return 'Ikke oppgitt'
    return f'{v/100:,.2f}'.replace(',', '\u00a0').replace('.', ',')+' kr'
def render():
    p=json.loads((PRIVATE/'import/import-package.json').read_text(encoding='utf-8'))
    validation=json.loads((PRIVATE/'import/validation.json').read_text(encoding='utf-8'))
    target=json.loads((PRIVATE/'profile-target.json').read_text(encoding='utf-8'))
    names={'income':'Inntekt','expense':'Utgift','debt_payment':'Gjeldsbetaling','savings_deposit':'Sparing',
           'annual_fund_payment':'Årsutgift','remittance':'Utland'}
    labels={'missing_amount':'Beløp eller grense er ikke oppgitt',
            'opening_balance_date_not_in_source':'Dato for startsaldo på sparemål må avklares',
            'source_fx_rate_not_confirmed':'Kildekurs er en ubekreftet plassholder',
            'expense_has_module_link_classification_review':'Utgiftskategori med modulkobling: unngå dobbel belastning',
            'missing_or_ambiguous_date':'Dato mangler eller er uklar'}
    rows=[]
    for r in p['transactions']:
        raw=r['raw']; status='Trenger avklaring' if r['review_state']=='needs_review' else 'Bevart fra kilden'
        rows.append('<tr>'+''.join('<td>'+text(v)+'</td>' for v in [r['source']['row'],r['effective_date'] or 'Udatert',raw['category'],raw['description'],names.get(r['source_accounting_class'],'Ukjent')])+f'<td class="num">{text(money(r["amount_nok_ore"]))}</td><td>{text(raw["linked_to"])}</td><td>{status}</td></tr>')
    categories=''.join(f'<tr><td>{text(c["source"]["row"])}</td><td>{text(c["raw"]["name"])}</td><td>{text(c["raw"]["kind"])}</td><td class="num">{text(money(c["monthly_budget_ore"])) if c["budget_mode"]=="source_monthly_limit" else "Beregnes fra modulplan"}</td></tr>' for c in p['categories'])
    debts=''.join(f'<tr><td>{text(d["raw"]["name"])}</td><td>{text(d["reference_date"])}</td><td class="num">{text(money(d["reference_balance_ore"]))}</td><td>{text(d["annual_rate_decimal"])}</td><td class="num">{text(money(d["monthly_minimum_ore"]))}</td></tr>' for d in p['debts'])
    goals=''.join(f'<tr><td>{text(g["raw"]["name"])}</td><td class="num">{text(money(g["opening_balance_ore"]))}</td><td class="num">{text(money(g["target_ore"]))}</td><td class="num">{text(money(g["monthly_plan_ore"]))}</td><td>{text(g["target_date"])}</td><td>Startdato for tidligere oppsparing er uavklart</td></tr>' for g in p['savings_goals'])
    issues=''.join(f'<li><strong>{text(labels.get(code,code))}</strong>: {count}</li>' for code,count in validation['issue_counts'].items())
    doc=f'''<!doctype html><html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Familieblikk · privat importgjennomgang</title><style>
    *{{box-sizing:border-box}}body{{font:15px/1.55 system-ui;background:#F5F7F4;color:#172B25;margin:0;padding:28px}}main{{max-width:1300px;margin:auto}}h1{{font-size:30px}}h2{{font-size:21px;margin-top:0}}section{{background:white;border:1px solid #DDE5DE;border-radius:16px;padding:24px;margin:22px 0}}.notice{{background:#E8F2EC;padding:18px;border-radius:12px}}.warning{{background:#FFF2D9}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}.metric{{background:white;border:1px solid #DDE5DE;border-radius:12px;padding:18px}}.metric strong{{display:block;font-size:30px}}small{{color:#53675D}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #E4EAE4;vertical-align:top}}th{{font-size:13px;color:#53675D}}.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}.table{{overflow:auto}}a{{color:#17644B}}.pill{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#17644B}}@media(max-width:650px){{body{{padding:16px}}.grid{{grid-template-columns:repeat(2,1fr)}}section{{padding:16px}}}}@media print{{body{{background:white}}section{{break-inside:avoid}}}}</style></head><body><main>
    <p class="pill">Privat kildegjennomgang · ikke en innlogget app</p><h1>Ditt faktiske familiebudsjett</h1>
    <div class="notice">Kildedataene er bevart for familieprofilen til <strong>{text(target.get('owner_email') or 'eier som må angis')}</strong>. Adressen er oppgitt av brukeren, men ikke bekreftet ved innlogging. Dette dokumentet er privat og skal ikke publiseres eller brukes som demo for andre familier.</div>
    <p>Kildens valgte måned: <strong>{text(p['source_selected_month'])}</strong>. Originale datoer og beløp beholdes. Arbeidsboken er ikke endret, og formelcacher er ikke en ny beregning.</p>
    <div class="grid">{''.join(f'<div class="metric"><small>{label}</small><strong>{len(p[key])}</strong></div>' for key,label in [('transactions','Transaksjoner'),('categories','Kategorier'),('debts','Gjeldsposter'),('savings_goals','Sparemål')])}</div>
    <section><h2>Dette må være sant før importen er ferdig</h2><p>Dataene skal faktisk være lagret i riktig verifisert familieprofil og fortsatt finnes etter ny innlogging og omstart. Andre familier får ikke dataene. Gjenkjøring gir ikke dubletter. Det er ikke bygget app eller database ennå, så dette er ikke utført profilimport.</p><div class="notice warning">Alle kilderader er bevart, inkludert dem som trenger avklaring. Manglende datoer eller usikker regnskapsklasse er ikke gjettet og inngår ikke som bekreftede, nye appdata.</div></section>
    <section><h2>Avklaringer i kilden</h2><ul>{issues}</ul><p>Transaksjonsrader med avklaringsbehov: {text(', '.join(map(str,validation['transaction_rows_needing_review'])))}. De to udaterte radene er {text(', '.join(map(str,validation['undated_transaction_rows'])))}. Du kan bevare dem som utkast til de får riktig dato og behandling.</p></section>
    <section><h2>Alle {len(p['transactions'])} faktiske transaksjoner</h2><div class="table"><table><thead><tr><th>Excel-rad</th><th>Dato</th><th>Kategori</th><th>Beskrivelse</th><th>Kildetype</th><th>NOK</th><th>Kobling</th><th>Status</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
    <section><h2>Kategorier og kildebudsjetter</h2><p>Dette er kildens månedlige oppsett; historisk gyldighetsdato er ikke oppdiktet.</p><div class="table"><table><thead><tr><th>Excel-rad</th><th>Navn</th><th>Kildetype</th><th>Månedsbeløp</th></tr></thead><tbody>{categories}</tbody></table></div></section>
    <section><h2>Gjeldens oppgitte referansesaldoer</h2><p>Saldoene gjelder datoen i arket; de er ikke presentert som en ny verifisert banksaldo i dag.</p><div class="table"><table><thead><tr><th>Gjeld</th><th>Saldodato</th><th>Kildesaldo</th><th>Årlig rente, desimaltall</th><th>Minst per måned</th></tr></thead><tbody>{debts}</tbody></table></div></section>
    <section><h2>Sparemål</h2><div class="table"><table><thead><tr><th>Mål</th><th>Startsaldo</th><th>Målbeløp</th><th>Månedsplan</th><th>Måldato</th><th>Avklaring</th></tr></thead><tbody>{goals}</tbody></table></div></section>
    <section><h2>Kildebevis</h2><p>SHA-256: <code>{text(p['source']['sha256'])}</code></p><p>Arbeidsboken, rå celler, typed importpakke og kontrollrapport ligger under private-data/family-budget/. Originalkopi og uttrekk beholdes separat fra offentlig design.</p></section>
    </main></body></html>'''
    path=PRIVATE/'import/import-review.html';path.write_text(doc,encoding='utf-8')
    print('Private import review rendered; no financial values written to terminal.')
    return path

if __name__=='__main__':
    render()
