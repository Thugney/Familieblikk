"""Read-only workbook structure extraction; no execution or recalculation."""
from pathlib import Path
import zipfile, xml.etree.ElementTree as ET, json, hashlib
p=Path('E:/Family_Budget_Expandable.xlsx')
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(p) as z:
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        strings=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets={r.attrib['Id']:r.attrib['Target'] for r in rels}
    sheets=[]
    for s in wb.find('m:sheets',ns):
        rel=s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target=targets[rel]
        name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        root=ET.fromstring(z.read(name))
        selected=[]; formulas=[]
        for cell in root.findall('.//m:sheetData/m:row/m:c',ns):
            a=cell.attrib.get('r',''); t=cell.attrib.get('t'); v=cell.find('m:v',ns); f=cell.find('m:f',ns)
            text=''
            if t=='s' and v is not None: text=strings[int(v.text)]
            elif t=='inlineStr': text=''.join(cell.find('m:is',ns).itertext())
            if text and len(selected)<32 and s.attrib['name'] not in ['Sim_Plan','Sim_Min']:
                selected.append({'cell':a,'text':text[:200]})
            if f is not None and len(formulas)<3: formulas.append({'cell':a,'formula':f.text})
        dim=root.find('m:dimension',ns)
        sheets.append({'sheet':s.attrib['name'],'dimension':dim.attrib.get('ref') if dim is not None else None,'text_sample':selected,'formula_sample':formulas})
out={'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'read_only':True,'recalculated':False,'sheets':sheets}
Path('work').mkdir(exist_ok=True)
Path('work/workbook-structure.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
