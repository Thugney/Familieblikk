"""Deterministic review projection; native BMAD files remain authoritative."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent.parent
P=ROOT/'.project-init'
def write(path,obj):
    path=ROOT/path;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
html=P/'familieblikk-mockup.html'
s=html.read_text(encoding='utf-8')
s=s.replace("['oversikt','poster','budsjett','regninger','sparing','familie'].map", "['oversikt','poster','budsjett','regninger','sparing','familie','mer'].map")
s=s.replace('}[screen]();let content=body;',',...(window.optionalScreens||{})}[screen]();let content=body;')
s=s.replace('Veiledende dagsbeløp','Veiledende dagsbeløp').replace('Trygt dagsbeløp','Veiledende dagsbeløp')
# Keep controls accessible without adding dependencies.
s=s.replace('min-height:38px;padding:5px 0','min-height:44px;padding:5px 0')
css='''
/* Review refinements: readable labels and card-formatted narrow tables. */
small,.bill-text small,.bill-amount small,.mini small,.mini .label,.subtle,.footer-note,.chart-col,.chart-labels{font-size:12px}
.eyebrow,.daily .eyebrow,.date-box span,th{font-size:12px}
input,select{border-color:#70877A}
.pagehead>button{white-space:nowrap;flex-shrink:0}
.bottom-nav button{font-size:12px}
@media(max-width:600px){.preview{display:grid;grid-template-columns:auto minmax(0,1fr) auto minmax(0,1fr);gap:6px}.preview strong{grid-column:1/-1}.preview select{min-width:0;width:100%;max-width:none}.preview .spacer{display:none}}
@media(max-width:600px){.mini .value{font-size:17px}.mini .label,.mini small,.daily>small{font-size:12px}.mini{padding:12px 8px}.mini-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.table-wrap{overflow:visible;margin:0}table{white-space:normal}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}tbody,tr,td{display:block}tr{border-bottom:1px solid var(--line);padding:12px 0}td{border:0;padding:4px 0;display:flex;justify-content:space-between;gap:16px;text-align:right}td::before{content:attr(data-label);font-size:12px;font-weight:500;color:var(--muted);text-align:left}td:last-child{text-align:right}.bill-text p{overflow-wrap:anywhere}.bill button{max-width:84px}.preview label{font-size:12px}}
'''
if '/* Review refinements:' in s:
    a=s.index('/* Review refinements:');b=s.index('</style>',a);s=s[:a]+s[b:]
s=s.replace('</style>',css+'</style>')
start='<!-- OPTIONAL_PREVIEW_START -->';end='<!-- OPTIONAL_PREVIEW_END -->'
if start in s:s=s[:s.index(start)]+s[s.index(end)+len(end):]
extra=(P/'optional-preview.js').read_text(encoding='utf-8')
extra=extra.replace('Object.values(enabled).some(Boolean)','Object.values(used).some(Boolean)').replace('enabled.gjeld?', 'used.gjeld?').replace('enabled.arsutgifter?', 'used.arsutgifter?').replace('enabled.utland', 'used.utland')
extra=extra.replace('Aktive moduler er med i beløpet øverst.','Aktive eller skjulte eksempelforpliktelser er med i beløpet øverst.')
extra=extra.replace('Fondssaldoen er en beregnet avsetning,', 'Ved forsikringens forfall i november ventes 8 800 kr avsatt mot 9 600 kr: 800 kr mangler da. Dette er et fremtidig finansieringsgap, ikke en ny oktoberutgift. Fondssaldoen er en beregnet avsetning,')
extra=extra.replace('${plan.months??\'360+\'} måneder i planen.', '${plan.months??\'360+\'} måneder i planen. Anslåtte renter: ${money(plan.interest)} med ekstra, ${money(minimum.interest)} uten ekstra.')
s=s.replace('</body>',start+'<script>\n'+extra+'\n</script>'+end+'</body>')
connected_start='<!-- CONNECTED_DESIGN_START -->';connected_end='<!-- CONNECTED_DESIGN_END -->'
if connected_start in s:s=s[:s.index(connected_start)]+s[s.index(connected_end)+len(connected_end):]
s=s.replace('</body>',connected_start+'<style>'+ (P/'connected-design.css').read_text(encoding='utf-8')+'</style><script>'+ (P/'connected-design.js').read_text(encoding='utf-8')+'</script>'+connected_end+'</body>')
html.write_text(s,encoding='utf-8')
base='_bmad-output/planning-artifacts/'
specs=[base+'prds/prd-familieblikk-2026-10-20/prd.md',base+'prds/prd-familieblikk-2026-10-20/addendum.md',base+'ux-designs/ux-familieblikk-2026-10-20/DESIGN.md',base+'ux-designs/ux-familieblikk-2026-10-20/EXPERIENCE.md',base+'architecture/architecture-familieblikk-2026-10-20/ARCHITECTURE-SPINE.md']
nav=['Oversikt','Poster','Budsjett','Regninger','Sparing','Mer']
screen_data=[
('oversikt','Oversikt','Igjen å bruke, veiledende dagsbeløp, mottatt/forventet inntekt, kategorier, kommende regninger, sparemål og sammenlignbar historikk.','Ny post'),
('poster','Poster','Inntekter og utgifter med eier, dato, kategori, mottatt/forventet status og refusjon.','Ny post'),
('budsjett','Budsjett','Felles kategorigrenser, faktisk forbruk, reservasjoner, overforbruk og admin-/medlemstilgang.','Endre grenser'),
('regninger','Regninger','Forfalte og kommende forekomster; betaling erstatter reservasjon med én post.','Marker betalt'),
('sparing','Sparing','Mål, åpningssaldo, innskudd, uttak, plan og anslått måldato.','Registrer innskudd'),
('familie','Familie og innstillinger','Medlemmer, roller, familieinvitasjon, språk, valuta og utlogging.','Inviter medlem'),
('mer','Mer','Mobilinngang til ekstra oversikter, familie og valgfritt oppsett.','Åpne oversikt'),
('innlogging','Innlogging','E-post og engangskode. Prototype sender ingen e-post.','Send engangskode'),
('opprett','Opprett familie','Navn på ny privat familie og forklaring av administratorrollen.','Opprett familie'),
('invitasjon','Godta invitasjon','Inviterende familie, mottaker, rolle og adressebekreftelse.','Bekreft adresse og bli med'),
('gjeld','Gjeld','Valgfri gjeldsoversikt med rente/minimum, Avalanche/Snowball, 360 måneders anslag og renter sammenlignet med uten ekstra.','Registrer gjeldsbetaling'),
('arsutgifter','Årsutgifter','Valgfrie års-/uregelmessige regninger med månedlig øremerking, fondssaldo og udekket beløp.','Registrer betaling fra fond'),
('utland','Utland','Valgfrie mottakere, opprinnelig valuta, bekreftet NOK-konvertering, måned og YTD. Ingen penger sendes.','Registrer overføring'),
('arsoversikt','Årsoversikt','Måneder, kategori, budsjett/faktisk, YTD og akkumulert historikk uten å videreføre fritt overskudd. Deler av tabelloppsettet er spine-only.','Se foreslåtte kolonner'),
('tilpass','Tilpass appen','Administrator velger gjeld, årsutgifter og utland. Skjuling må bevare forpliktelser og historikk.','Endre modulvalg')]
screens=[]
for key,title,desc,action in screen_data:
    states=['Empty','Loading','Offline','Error','Member']
    if key=='oversikt':states.append('Negative')
    screens.append({'id':key,'title':title,'navigation':nav,'sections':[{'title':title,'description':desc}],'actions':[{'label':action}],'states':states})
screens[0]['metrics']=[{'label':'Igjen å bruke','value':'18 400 kr'},{'label':'Dagsbeløp','value':'1 533 kr'},{'label':'Mottatt inntekt','value':'62 000 kr'},{'label':'Utgifter','value':'28 450 kr'}]
write(Path('.project-init/ui-design.json'),{'schemaVersion':1,'project':'Familieblikk','status':'draft','theme':{'primary':'#17644B','sidebar':'#FCFDFB','font':'system-ui'},'referenceMockup':'.project-init/familieblikk-mockup.html','screens':screens})
components=[('ui','Responsiv PWA','Visning, skjema og tilgjengelig navigasjon'),('identity','Innlogging og familiepolicy','E-postkode, sesjon, medlemskap og rettigheter'),('domain','Domeneoperasjoner','Én postmodell og beregningsmotor for kjerne og valgfrie moduler'),('db','PostgreSQL','Familieavgrensede data, transaksjoner og unike koblinger'),('mail','E-postadapter','Kode/invitasjon; produksjonsleverandør avklares')]
write(Path('.project-init/review-context.json'),{'schemaVersion':1,'specPaths':specs,'journeys':[{'label':'Inn i familiens budsjett','nodes':[{'label':x} for x in ['E-postkode','Opprett eller godta invitasjon','Riktig familie','Oversikt']],'failurePaths':['Utløpt kode','Annen familie','Ugyldig invitasjon']},{'label':'Regning og sparing teller én gang','nodes':[{'label':x} for x in ['Se reservasjon','Registrer betaling eller innskudd','Autoritativ post','Ny beregning']],'failurePaths':['Dobbeltklikk','Samtidig endring','Uten nett']},{'label':'Familien velger verktøy','nodes':[{'label':x} for x in ['Tilpass appen','Gjeld / årsutgifter / utland','Registrer med kobling','Årsoversikt']],'failurePaths':['Ukjent valutakurs','Underfinansiert fond','Skjult modul med åpne forpliktelser']}],'components':[{'id':i,'label':l,'responsibility':r,'evidenceStatus':'Forslag; ikke implementert'} for i,l,r in components],'edges':[{'from':'ui','to':'identity','label':'Autentisert forespørsel'},{'from':'identity','to':'domain','label':'Serverutledet familie og rolle'},{'from':'domain','to':'db','label':'Én transaksjon / autoritativ post'},{'from':'domain','to':'mail','label':'Kode eller invitasjon'}],'permissions':[{'role':'Medlem','scope':'Les familiens data; opprett og endre egne poster','enforcedAt':'Planlagt serverpolicy og relasjonsvalidering'},{'role':'Administrator','scope':'Alle familieposter, invitasjoner, kategorier, grenser og moduloppsett','enforcedAt':'Planlagt serverpolicy; ikke bare skjulte knapper'},{'role':'Annen familie','scope':'Ingen tilgang','enforcedAt':'Planlagt familieavgrensning på alle oppslag og koblinger'}],'questions':[{'question':'Godkjenn visuell kandidat og foreslåtte beregningsregler, inkludert valgfrie moduler.','status':'Avventer Robel'},{'question':'Django/PostgreSQL er anbefalt startpunkt, ikke installert appstakk. Hosting/e-post og personvern-/gjenopprettingsregler må avklares før ekte familiedata.','status':'Åpent før implementasjon/lansering'},{'question':'Mørkt tema er ikke bestilt. Project Init visual plan krever likevel mørke sammenligningscaser; denne verktøybegrensningen skal ikke tolkes som godkjent produktomfang.','status':'Verktøygap dokumentert'}]})
cases=[]
for key,_,_,_ in screen_data:
    for vp,w,h in [('desktop',1440,1100),('mobile',390,844)]:
        for st in ['Default']:
            cid=f'{key}-{vp}-light-{st.lower()}'
            cases.append({'id':cid,'screen':key,'viewport':vp,'theme':'light','state':st,'width':w,'height':h,'maxDiffRatio':.01,'pixelThreshold':10,'reference':f'.project-init/visual/baselines/{cid}.png','actual':f'.project-init/visual/actual/{cid}.png'})
for st in ['Empty','Loading','Offline','Error','Member','Negative']:
    cid=f'oversikt-mobile-light-{st.lower()}'
    cases.append({'id':cid,'screen':'oversikt','viewport':'mobile','theme':'light','state':st,'width':390,'height':844,'maxDiffRatio':.01,'pixelThreshold':10,'reference':f'.project-init/visual/baselines/{cid}.png','actual':f'.project-init/visual/actual/{cid}.png'})
write(Path('.project-init/visual-cases.json'),{'schemaVersion':1,'cases':cases})
# File-hash receipts contain provenance only, not source-workbook balances.
write(Path('work/source-receipt.json'),{'schemaVersion':1,'sources':[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in ['context.md','_bmad/_config/manifest.yaml']],'framework':'BMAD','version':'6.12.4','scopeAmendment':'Optional workbook capabilities authorized 2026-10-20'})
contracts={
'gatherer-source':(['context.md','_bmad/_config/manifest.yaml'],'work/source-receipt.json','Collect source hashes using prepare-design.py; receipt schema: schemaVersion, sources[{path,sha256}],framework,version,scopeAmendment.'),
'producer-prd':(['context.md'],specs[0],'BMAD PRD; product requirements only, stable FR IDs and explicit assumptions.'),
'producer-design':(['context.md',specs[0]],specs[2],'BMAD DESIGN.md visual token spine. Reference mock is a review projection.'),
'producer-experience':(['context.md',specs[0],specs[2]],specs[3],'BMAD EXPERIENCE.md journeys, permissions, states and interaction spine.'),
'producer-architecture':(['context.md']+specs[:4],specs[4],'BMAD architecture spine; proposed invariants, current primary technology sources and deferred choices.'),
'verifier':(['context.md','rules.md']+specs+['.project-init/familieblikk-mockup.html','.project-init/evidence/design-checks.json'],'work/design-verdict.json','Fresh context; schema: schemaVersion,verdict,findings[{severity,file,issue}],checks,limitations. This is review evidence, never human approval.')}
for name,(inputs,output,rule) in contracts.items():
    f=ROOT/'graph/nodes'/f'{name}.md';f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(f'# {name}\n\n## Input\n'+''.join(f'- {x}\n' for x in inputs)+f'\n## Output\n{output}\n\n## Contract\n{rule}\n\nOne artifact per node. Framework memlog updates use the unchanged BMAD helper as a deterministic side-effect. Preserve others\' work. No approval, commit, push or app implementation.\n',encoding='utf-8')
print(json.dumps({'screens':len(screens),'visualCasesPlanned':len(cases),'nativeSpecs':specs,'humanApproved':False},ensure_ascii=False))
