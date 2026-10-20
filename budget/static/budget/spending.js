/* Familiens data lever bare i denne siden. Ingen lagringskø eller privat nettleserlagring. */
(function () {
  'use strict';
  const money = value => value === null || value === undefined ? 'Ukjent' : new Intl.NumberFormat('nb-NO', {style: 'currency', currency: 'NOK', maximumFractionDigits: 2}).format(value / 100);
  function parseOre(value) {
    const text = String(value).trim().replace(',', '.');
    if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return null;
    const [whole, fraction = ''] = text.split('.');
    const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    return Number.isSafeInteger(result) ? result : null;
  }
  function equation(plan, draft) {
    const groups = {ordinary_fixed_ore: plan.totals.ordinary_fixed_ore, other_categories_ore: 0, savings_ore: 0, debt_ore: 0, funds_ore: 0};
    let valid = Number.isSafeInteger(draft.expected_income_ore) && draft.expected_income_ore >= 0 && Number.isSafeInteger(groups.ordinary_fixed_ore);
    for (const row of draft.categories) { valid = valid && Number.isSafeInteger(row.other_ore) && row.other_ore >= 0; groups.other_categories_ore = row.other_ore === null || groups.other_categories_ore === null ? null : groups.other_categories_ore + row.other_ore; }
    for (const row of draft.assets) {
      const source = plan.assets.find(asset => asset.id === row.id);
      valid = valid && !!source && Number.isSafeInteger(row.amount_ore) && row.amount_ore >= 0;
      if (source) {
        const key = {savings: 'savings_ore', debt: 'debt_ore', fund: 'funds_ore'}[source.kind];
        groups[key] = row.amount_ore === null || groups[key] === null ? null : groups[key] + assetContribution(source, row.amount_ore);
      }
    }
    return {...groups, planned_remainder_ore: valid ? draft.expected_income_ore - Object.values(groups).reduce((sum, value) => sum + value, 0) : null};
  }
  function assetContribution(asset, amount) {
    if (amount === null) return null;
    if (asset.kind === 'debt') return Math.max(amount, asset.obligation_ore || 0);
    if (asset.kind === 'fund') return amount + Math.max((asset.obligation_ore || 0) - (asset.available_balance_ore || 0) - amount, 0);
    return amount;
  }
  function entryUrl(value, origin) {
    try { const url=new URL(value,origin); return url.origin===origin && /^\/endre\/entry\/[\da-f-]{36}\/$/i.test(url.pathname) ? url.href : null; }
    catch (_) { return null; }
  }
  // Invalidating at input time prevents a previous response winning during debounce.
  function requestGate() {
    let version = 0, controller;
    return {invalidate() { ++version; if (controller) controller.abort(); }, begin() { if (controller) controller.abort(); controller = new AbortController(); const current = ++version; return {signal: controller.signal, current: () => current === version}; }};
  }
  const helpers = {money, parseOre, equation, requestGate, assetContribution, entryUrl};
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (typeof document === 'undefined') return;
  const root = document.querySelector('[data-spending-workspace]');
  if (!root || root.dataset.enhanced) return;
  root.dataset.enhanced = 'true';
  const $ = selector => root.querySelector(selector);
  const $$ = selector => [...root.querySelectorAll(selector)];
  const boot = JSON.parse($('#spending-boot').textContent);
  const form = $('#sp-plan-form');
  let tab = boot.initial_tab || 'spending', data, annualData, plan, draft, preview, saveKey, saving = false, searchTimer, activeDetail, historySelection=[];
  let confirmAction, retryAction;
  const selected = new Set();
  const spendingGate = requestGate(), annualGate = requestGate(), planningGate = requestGate(), detailGate = requestGate();
  const monthName = value => new Intl.DateTimeFormat('nb-NO', {month:'long',year:'numeric',timeZone:'Europe/Oslo'}).format(new Date(value + '-15T12:00:00Z'));
  const dateName = value => new Intl.DateTimeFormat('nb-NO', {day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Oslo'}).format(new Date(value + 'T12:00:00Z'));
  const sourceNames = {missing: 'Ukjent – fyll inn beløp', existing_plan: 'Eksisterende målplan', history: 'Valgt historikk', confirmed_commitment: 'Bekreftet forpliktelse', manual: 'Manuelt beløp'};
  const kindNames = {expense:'Utgift',refund:'Refusjon',remittance:'Overføring til utlandet'};
  function el(tag, attributes = {}, children = []) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) {
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'onClick') node.addEventListener('click', value);
      else if (key === 'checked') node.checked = value;
      else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const p = (text, cls = 'sp-note') => el('p', {class:cls, text});
  const button = (text, handler, cls = 'secondary') => el('button', {type:'button', class:cls, onClick:handler, text});
  const row = (name, value, note) => el('div', {class:'sp-plan-row'}, [el('span', {}, [name, note ? el('small', {text:note}) : null]), el('strong', {text:value})]);
  function status(text) { $('#sp-status').textContent = text; }
  function error(message, retry = true, action) { $('#sp-error').textContent = message; $('#sp-error').hidden = false; $('#sp-retry').hidden = !retry; if(action!==undefined)retryAction=action; }
  function clearError() { $('#sp-error').hidden = true; $('#sp-retry').hidden = true; retryAction=null; }
  function markDirty() { form.dataset.dirty = 'true'; preview = null; saveKey = null; }
  function csrf() { return form.querySelector('[name=csrfmiddlewaretoken]').value; }
  async function api(url, params = {}, options = {}) {
    if (!navigator.onLine) throw Object.assign(new Error('Du er frakoblet. Utkastet beholdes. Koble til og prøv igjen.'), {status:0});
    const target = new URL(url, location.origin);
    for (const [name, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== '') target.searchParams.set(name, value);
    const response = await fetch(target, {credentials:'same-origin',cache:'no-store',...options,headers:{'Accept':'application/json',...(options.body ? {'Content-Type':'application/json','X-CSRFToken':csrf()} : {}),...options.headers}});
    let body;
    try { body = await response.json(); } catch (_) { throw new Error('Økten kan ha utløpt. Last inn siden på nytt når utkastet er gjennomgått.'); }
    if (!response.ok || response.redirected) throw Object.assign(new Error(body.error || 'Kunne ikke hente familiens data. Prøv igjen.'), {status:response.status});
    return body;
  }
  function currentFilters() { return {month:boot.month,period:$('#sp-period').value,q:$('#sp-search').value.trim(),categories:[...selected].join(','),start:$('#sp-start').value,end:$('#sp-end').value}; }
  function validDates() { return $('#sp-period').value !== 'custom' || ($('#sp-start').value && $('#sp-end').value && $('#sp-start').value <= $('#sp-end').value); }
  function categoryOptions(options) {
    const container = $('#sp-category-options');
    if (container.dataset.ready) return;
    container.dataset.ready = 'true';
    container.append(button('Vis alle kategorier', () => { selected.clear(); $$('[data-sp-category-filter]').forEach(input => input.checked = false); updateCategorySummary(); loadSpending(); }));
    for (const category of options) {
      const input = el('input', {type:'checkbox',value:category.id,'data-sp-category-filter':category.id});
      input.addEventListener('change', () => { input.checked ? selected.add(input.value) : selected.delete(input.value); updateCategorySummary(); loadSpending(); });
      container.append(el('label', {}, [input, category.name]));
      $('#sp-annual-category').append(el('option', {value:category.id,text:category.name}));
    }
  }
  function updateCategorySummary() { $('#sp-category-summary').textContent = selected.size ? selected.size + ' valgt' : 'Alle kategorier'; }
  function metric(label, amount, note) { return el('div', {class:'sp-metric'}, [p(label,'sp-eyebrow'), el('strong', {class:'sp-amount',text:amount}), el('small', {text:note})]); }
  function coverage(info, extra = '') {
    const count = info.unresolved_import_count || 0;
    return el('div', {class:'sp-coverage'}, [el('strong', {text:'Om tallgrunnlaget'}), extra, info.warning ? ' ' + info.warning : count ? ` ${count} uavklarte importposter er utelatt fra beløpene.` : ' Bare bekreftede poster inngår.']);
  }
  function chart(rows, label) {
    const holder = el('div');
    if (!rows.length) { holder.append(p('Ingen historikk i valgt periode. Manglende måneder vises ikke som 0 kr.')); return holder; }
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 620 260'); svg.setAttribute('class','sp-chart'); svg.setAttribute('role','img');
    svg.setAttribute('aria-label', label + '. ' + rows.map(r => monthName(r.month) + ': ' + (r.amount_ore === null ? 'mangler grunnlag' : money(r.amount_ore)) + (r.status === 'partial' ? ', ufullstendig' : '')).join('. '));
    const values = rows.map(r => r.amount_ore).filter(v => v !== null), high = Math.max(...values,0), low = Math.min(...values,0), span = Math.max(high-low,1), y = v => 205 - (v-low)/span*155;
    const baseline = y(0), step = 570/rows.length, barWidth = Math.min(95,step*.65);
    const shape = (tag, attrs, text) => { const n = document.createElementNS(ns,tag); for (const [k,v] of Object.entries(attrs)) n.setAttribute(k,v); if (text !== undefined) n.textContent = text; svg.append(n); return n; };
    shape('line',{x1:25,y1:baseline,x2:605,y2:baseline,stroke:'#dfe6df'});
    rows.forEach((r,i) => {
      const x = 25 + i*step + (step-barWidth)/2, center = x+barWidth/2;
      let mark;
      if (r.amount_ore === null) { mark=shape('rect',{x,y:baseline-2,width:barWidth,height:4,fill:'#e3e8e1'}); shape('text',{x:center,y:224,'text-anchor':'middle'},'–'); }
      else { const negative = r.amount_ore < 0; mark=shape('rect',{x,y:Math.min(y(r.amount_ore),baseline),width:barWidth,height:Math.max(Math.abs(y(r.amount_ore)-baseline),2),rx:4,fill:negative?'#ad3f38':r.status==='partial'?'#7f9f88':'#17644b'}); if (rows.length <= 4) shape('text',{x:center,y:negative?y(r.amount_ore)+17:y(r.amount_ore)-10,'text-anchor':'middle',class:'sp-value'},money(r.amount_ore)); }
      const title=document.createElementNS(ns,'title');title.textContent=monthName(r.month)+': '+(r.amount_ore===null?'Mangler grunnlag':money(r.amount_ore))+(r.status==='partial'?' · ufullstendig måned':'');mark.append(title);
      shape('text',{x:center,y:247,'text-anchor':'middle'},new Intl.DateTimeFormat('nb-NO',{month:'short',timeZone:'Europe/Oslo'}).format(new Date(r.month+'-15T12:00:00Z')));
    });
    holder.append(p('Beløpsskala: '+money(low)+' til '+money(high)+'.','sp-note'),svg,p('Rødt og minustegn viser netto tilbakebetaling. En strek betyr manglende grunnlag; den betyr ikke 0 kr. Pågående måneder er ufullstendige.'));
    const details = el('details',{},[el('summary',{text:'Vis månedstall som tekst'})]), list = el('ul',{class:'sp-entries'});
    for (const r of rows) list.append(el('li',{class:'sp-entry'},[el('span',{},[monthName(r.month),el('small',{text:r.status==='partial'?'Ufullstendig måned':r.status==='missing'?'Mangler registrert grunnlag':'Registrerte poster'})]),el('strong',{text:money(r.amount_ore)})]));
    details.append(list); holder.append(details); return holder;
  }
  function breakdown(rows, detailHandler, id = 'sp-breakdown') {
    const holder = el('div',{id}), max = Math.max(...rows.map(c => Math.abs(c.amount_ore)),1);
    for (const category of rows) {
      const negative = category.amount_ore < 0, bar = el('span',{class:'sp-bar'+(negative?' sp-negative':'')});
      bar.style.width = Math.abs(category.amount_ore)/max*100+'%';
      const b = button('',() => detailHandler(category),'sp-category');
      b.setAttribute('data-sp-detail',category.id); b.style.setProperty('--sp-color', /^#[\da-f]{6}$/i.test(category.color) ? category.color : '#7f9f88');
      b.append(el('span',{class:'sp-cat-name'},[el('i',{class:'sp-dot','aria-hidden':'true'}),category.name]),el('span',{class:'sp-cat-value'+(negative?' sp-negative':'')},[money(category.amount_ore),negative?el('small',{text:'Netto tilbakebetaling'}):null,' ›']),el('span',{class:'sp-bar-track','aria-hidden':'true'},[bar]));
      holder.append(b);
    }
    if (!rows.length) holder.append(p('Ingen utgiftsposter passer filtrene. Velg en annen periode eller nullstill filtrene.','sp-empty'));
    return holder;
  }
  function renderSpending(result) {
    categoryOptions(result.category_options);
    const target = $('#sp-results'), metrics = el('div',{class:'sp-metrics'},[
      metric('Utgifter i valgt utvalg',money(result.total_ore),`${result.pagination.count} poster · ${dateName(result.period.start)} – ${dateName(result.period.end)}`),
      metric('Alle utgifter i perioden',money(result.period_total_ore ?? result.total_ore),'Før kategori- og søkefilter'),
      metric('Kategorier med treff',String(result.categories.filter(c=>c.entry_count>0).length),result.period.to_today?'Perioden er avgrenset til i dag':'Hele det valgte tidsrommet')]);
    const left = el('section',{class:'sp-section'},[el('h2',{text:'Hvor gikk pengene?'}),p('Hele utvalget, kategori for kategori. Trykk for detaljer.'),breakdown(result.categories,c=>openDetail(c,currentFilters())),p('Søylene sammenligner registrerte beløp. Refusjoner reduserer forbruk på refusjonsdatoen. 0 kr betyr registrert null eller ingen treff i dette utvalget.')]);
    const income = el('div',{class:'sp-income'},[el('h3',{text:'Inntekt i perioden'}),p(result.income.label),row('Faktisk mottatt',money(result.income.received_ore)),row('Forventet / ikke mottatt',money(result.income.expected_entries_ore))]);
    if (result.income.forecast_ore !== null) income.append(row('Forventet inntekt i månedsplan',money(result.income.forecast_ore),result.income.forecast_scope||'Planbeløpet gjelder hele budsjettmåneder, separat fra mottatte penger.'));
    const right = el('section',{class:'sp-section'},[el('h2',{text:'Utvikling måned for måned'}),p('Samme periode, kategorier og søketekst'),chart(result.trend,'Utgifter i valgt utvalg'),income]);
    target.replaceChildren(metrics,el('div',{class:'sp-grid'},[left,right]),coverage(result.coverage));
    if (!result.pagination.count) target.append(button('Nullstill filtre',resetFilters));
  }
  async function loadSpending() {
    clearTimeout(searchTimer); spendingGate.invalidate();
    if (!validDates()) { $('#sp-results').replaceChildren(); error('Velg både fra- og til-dato. Fra-dato må være før eller lik til-dato.',false); return; }
    const token = spendingGate.begin(); clearError(); status('Oppdaterer forbruket…'); $('#sp-results').setAttribute('aria-busy','true');
    try { const result = await api(boot.urls.spending,currentFilters(),{signal:token.signal}); if (!token.current()) return; data=result; renderSpending(result); status('Forbruket er oppdatert.'); }
    catch(e) { if(token.current() && e.name!=='AbortError') error(e.message+' Tidligere resultat kan være fra forrige filtervalg.'); }
    finally { if(token.current()) $('#sp-results').setAttribute('aria-busy','false'); }
  }
  async function loadAnnual() {
    const token = annualGate.begin(); clearError(); status('Henter årsoversikten…'); const params={period:'year',month:boot.month,year:$('#sp-year').value,categories:$('#sp-annual-category').value};
    try { const result=await api(boot.urls.spending,params,{signal:token.signal}); if(!token.current())return; annualData=result; categoryOptions(result.category_options);
      $('#sp-annual-results').replaceChildren(coverage(result.coverage,'Måneder uten registrert grunnlag er ukjente. Dette er registrert forbruk, ikke en bekreftet helårssum.'),el('div',{class:'sp-metrics'},[metric('Registrerte utgifter i valgt år',money(result.total_ore),'Alle måneder med registrert grunnlag'),metric('Måneder med registrerte poster',String(result.trend.filter(r=>r.has_entries).length),'Pågående måned kan være ufullstendig')]),chart(result.trend,'Registrerte utgifter i valgt år'),el('h3',{text:'Fordeling på kategorier'}),breakdown(result.categories,c=>openDetail(c,params),'sp-annual-breakdown')); status('Årsoversikten er oppdatert.');
    } catch(e) { if(token.current()&&e.name!=='AbortError')error(e.message); }
  }
  function entryList(result, pageHandler) {
    const list=el('ul',{class:'sp-entries'});
    for(const entry of result.entries) {
      const content=el('span',{},[el('strong',{text:entry.description}),el('small',{text:dateName(entry.date)+' · '+(kindNames[entry.kind]||entry.kind)+' · '+entry.category_name})]);
      if(entry.detail_url) { const url=entryUrl(entry.detail_url,location.origin); if(url)content.append(el('a',{href:url,text:'Åpne post'})); }
      list.append(el('li',{class:'sp-entry'},[content,el('strong',{class:entry.amount_ore<0?'sp-negative':'',text:money(entry.amount_ore)})]));
    }
    if(!result.entries.length)list.append(el('li',{class:'sp-empty',text:'Ingen poster passer gjeldende filtre.'}));
    const pagination=el('div',{class:'sp-pagination'},[p(`Side ${result.pagination.page} av ${result.pagination.pages} · ${result.pagination.count} poster`)]);
    if(result.pagination.page>1)pagination.append(button('Forrige',()=>pageHandler(result.pagination.page-1)));
    if(result.pagination.page<result.pagination.pages)pagination.append(button('Neste',()=>pageHandler(result.pagination.page+1)));
    return el('div',{},[list,pagination]);
  }
  async function openDetail(category, filters, page=1) {
    activeDetail={category,filters,page}; $('#sp-detail-title').textContent=category.name;
    if(!$('#sp-detail').open)$('#sp-detail').showModal();
    $('#sp-detail-content').replaceChildren(p('Henter kategorien…')); const token=detailGate.begin();
    try { const result=await api(boot.urls.spending,{...filters,categories:category.id,page},{signal:token.signal}); if(!token.current())return;
      $('#sp-detail-content').replaceChildren(p(`Valgt utvalg · ${money(result.total_ore)} · ${result.pagination.count} poster`),chart(result.trend,'Kategoriens utvikling i valgt utvalg'),el('h3',{text:'Poster i det valgte utvalget'}),entryList(result,next=>openDetail(category,filters,next)));
    } catch(e) { if(token.current()&&e.name!=='AbortError')$('#sp-detail-content').replaceChildren(p(e.message,'sp-warning'),button('Prøv igjen',()=>openDetail(category,filters,page))); }
  }
  function amountInput(name, value, source, kind, id, note='') {
    const inputId='sp-amount-'+kind+'-'+id;
    const input=el('input',{id:inputId,type:'number',min:'0',step:'0.01',inputmode:'decimal',required:true,value:value===null?'':String(value/100),'data-plan-kind':kind,'data-plan-id':id});
    input.addEventListener('input',()=> { const amount=parseOre(input.value); if(kind==='income')draft.expected_income_ore=amount; else if(kind==='category')draft.categories.find(r=>r.id===id).other_ore=amount; else draft.assets.find(r=>r.id===id).amount_ore=amount; markDirty(); const label=input.closest('.sp-plan-row').querySelector('[data-sp-source]'); label.textContent='Manuelt beløp'+(note?' · '+note:''); updateEquation(); });
    return el('div',{class:'sp-plan-row'},[el('label',{for:inputId},[name,el('small',{'data-sp-source':'',text:(sourceNames[source]||source)+(note?' · '+note:'')}),kind==='asset'?el('small',{'data-sp-contribution':id}):null]),input]);
  }
  function renderPlan() {
    historySelection=[...draft.history_months];
    $('#sp-target').value=plan.target_month; $('#sp-plan-heading').textContent='Plan for '+monthName(plan.target_month);
    const cover=coverage(plan.coverage,'Utkastet gjelder bare målmåneden. Ukjente beløp må fylles inn; 0 kr er et eksplisitt valg.');
    const history=el('fieldset',{class:'sp-history'},[el('legend',{text:'Kildemåneder for forslag'})]), options=el('div',{class:'sp-history-options'});
    for(const item of plan.history_options) {
      const checkbox=el('input',{type:'checkbox',value:item.month,checked:draft.history_months.includes(item.month),'data-sp-history':item.month,disabled:item.status==='missing'});
      checkbox.addEventListener('change',()=> { historySelection=$$('[data-sp-history]:checked').map(i=>i.value); planningGate.invalidate(); updateHistoryLabel(); });
      options.append(el('label',{},[checkbox,monthName(item.month)+' · '+(item.status==='completed'?`${item.entry_count} poster`:item.status==='partial'?`${item.entry_count} poster · ufullstendig grunnlag`:'mangler grunnlag')]));
    }
    history.append(options,p('', 'sp-note'),button('Bruk forslag',applyHistory)); history.querySelector('p').id='sp-history-label';
    if(!plan.history_options.length) history.append(p('Ingen avsluttede kildemåneder er tilgjengelige. Legg inn familiens planbeløp manuelt.'));
    const income=el('section',{class:'sp-plan-section'},[el('h3',{text:'1. Forventet inntekt'}),p('Planlagt inntekt er ikke mottatte penger. Beløpet endrer ikke dagens «igjen å bruke».'),amountInput('Forventet samlet inntekt',draft.expected_income_ore,plan.income_source,'income','income')]);
    const fixed=el('section',{class:'sp-plan-section'},[el('h3',{text:'2. Faste regninger og planer'}),p('Hver forpliktelse trekkes én gang i riktig del av regnestykket. Øvrige kategoribeløp nedenfor kommer i tillegg til ordinære faste regninger.')]);
    const ordinary=plan.commitments.filter(c=>c.accounting_class==='ordinary');
    for(const item of ordinary)fixed.append(row(item.name,money(item.amount_ore),'Fast regning · '+dateName(item.due_date)+(item.overdue?' · ubetalt fra tidligere måned':'')));
    if(!ordinary.length)fixed.append(p('Ingen ordinære faste regninger er registrert.'));
    for(const asset of plan.assets) {
      const value=draft.assets.find(r=>r.id===asset.id).amount_ore;
      let note={savings:'Sparing',debt:'Gjeldsplan',fund:'Fondsavsetning / påfyll'}[asset.kind];
      if(asset.obligation_ore)note+=' · kjent forpliktelse '+money(asset.obligation_ore);
      if(asset.available_balance_ore!==null)note+=' · eksisterende saldo '+money(asset.available_balance_ore)+' er ikke inntekt';
      fixed.append(amountInput(asset.name,value,asset.source,'asset',asset.id,note));
    }
    if(!plan.assets.length)fixed.append(p('Ingen sparemål, gjeldsplaner eller fondsavsetninger er konfigurert. Opprett dem via «Sparemål og planer».'));
    const variable=el('section',{class:'sp-plan-section'},[el('h3',{text:'3. Plan for øvrig forbruk'}),p('Beløpene er den variable delen. Faste regninger ovenfor legges ikke til en gang til.')]);
    for(const category of plan.categories) {
      const note=`${category.observations} historiske observasjoner`+(category.historical_average_ore!==null?' · netto snitt '+money(category.historical_average_ore):'')+(category.fixed_ore?' · faste regninger '+money(category.fixed_ore)+' vises separat':'');
      variable.append(amountInput(category.name,draft.categories.find(r=>r.id===category.id).other_ore,category.source,'category',category.id,note));
    }
    if(!plan.categories.length)variable.append(p('Familien har ingen forbrukskategorier ennå. Opprett kategorier før dere fordeler forbruk.'));
    const unknown=el('section',{class:'sp-plan-section'},[el('h3',{text:'Hva vet vi ikke ennå?'}),p('Ferier, prisendringer og engangsutgifter kan mangle. Uavklarte importutkast inngår ikke. Gå gjennom grunnlaget og egne planer før dere lagrer. Tidligere overskudd overføres ikke som inntekt.')]);
    const ack=el('input',{type:'checkbox',id:'sp-ack',checked:draft.acknowledge_incomplete}); ack.addEventListener('change',()=> { draft.acknowledge_incomplete=ack.checked; markDirty(); updateEquation(); });
    if(plan.coverage.requires_acknowledgement)unknown.append(el('label',{class:'sp-ack',for:'sp-ack'},[ack,'Jeg har gjennomgått det begrensede grunnlaget.']));
    const summary=el('aside',{class:'sp-plan-summary'},[el('h3',{text:'Slik henger planen sammen'}),el('div',{id:'sp-equation','aria-live':'polite'}),el('div',{class:'sp-actions'},[el('button',{type:'submit',id:'sp-review',text:'Gjennomgå og lagre',hidden:!plan.can_save}),button('Forkast utkast',discardDraft)]),p(plan.can_save?'Ingenting lagres før du bekrefter målmåned og endringsoversikt.':'Alle familiemedlemmer kan lage og drøfte utkast. Bare administrator kan lagre felles plan.')]);
    $('#sp-plan-content').replaceChildren(cover,history,el('div',{class:'sp-plan-grid'},[el('div',{},[income,fixed,variable,unknown]),summary]));
    updateHistoryLabel(); updateEquation();
  }
  function updateHistoryLabel() { const n=historySelection.length; $('#sp-history-label').textContent=n?`Valgt: ${historySelection.map(monthName).join(', ')}. ${n<3?'Sparsomt grunnlag. ':''}Endret kildevalg erstatter ikke utkastbeløp eller lagret grunnlag; bruk forslag og bekreft først.`:'Ingen kildemåneder valgt. Forslag er ukjente; legg inn beløp eller velg avsluttede måneder.'; }
  function equationContent(totals, income) {
    const content=el('div',{class:'sp-equation'});
    content.append(row('Forventet inntekt',money(income)));
    for(const [key,label] of [['ordinary_fixed_ore','− Faste regninger'],['other_categories_ore','− Øvrig forbruk'],['savings_ore','− Sparing'],['debt_ore','− Gjeldsplan'],['funds_ore','− Fondsavsetning / påfyll']])content.append(row(label,money(totals[key])));
    if(totals.planned_remainder_ore===null)content.append(p('Fyll ut grunnlaget. Et tomt felt betyr ukjent, ikke 0 kr.','sp-warning'));
    else content.append(el('div',{class:'sp-residual'+(totals.planned_remainder_ore<0?' sp-negative':'')},[p(totals.planned_remainder_ore<0?'Planlagt underskudd':'Ufordelt i månedsplanen','sp-eyebrow'),el('strong',{class:'sp-amount','data-sp-remainder':'',text:money(totals.planned_remainder_ore)}),p(totals.planned_remainder_ore<0?'Planen bruker mer enn forventet inntekt. Juster beløpene eller avklar inntekten.':'Dette er forventet handlingsrom, ikke penger tilgjengelig nå.')]));
    return content;
  }
  function updateEquation() { const totals=equation(plan,draft); $('#sp-equation').replaceChildren(equationContent(totals,draft.expected_income_ore)); $('#sp-review').disabled=saving||!navigator.onLine||totals.planned_remainder_ore===null||(plan.coverage.requires_acknowledgement&&!draft.acknowledge_incomplete); for(const label of $$('[data-sp-contribution]')){const asset=plan.assets.find(a=>a.id===label.dataset.spContribution),amount=draft.assets.find(a=>a.id===asset.id).amount_ore; label.textContent='Trekk i prognosen: '+money(assetContribution(asset,amount))+(asset.kind==='debt'?' · minst kjent gjeldsforpliktelse':asset.kind==='fund'?' · avsetning og nødvendig påfyll, eksisterende saldo medregnet':' · sparing én gang');} }
  async function loadPlan(target, force=false) {
    if(draft && !force)return;
    const token=planningGate.begin(); clearError(); status('Henter planleggingsgrunnlaget…');
    try { const result=await api(boot.urls.planning,target?{target_month:target}:{},{signal:token.signal}); if(!token.current())return; plan=result; draft=structuredClone(result.draft); preview=null;saveKey=null;renderPlan();delete form.dataset.dirty;status('Utkastet er klart. Ingenting er lagret.'); }
    catch(e) { if(token.current()&&e.name!=='AbortError'){error(e.message,true,()=>loadPlan(target,true));if(draft)$('#sp-target').value=draft.target_month;} }
  }
  function confirmDialog(title, content, text, action) { $('#sp-confirm-title').textContent=title;$('#sp-confirm-content').replaceChildren(...content);$('#sp-confirm-action').textContent=text;$('#sp-confirm-action').disabled=false;$('#sp-confirm-error').hidden=true;confirmAction=action;if(!$('#sp-confirm').open)$('#sp-confirm').showModal(); }
  function discardDraft() { confirmDialog('Forkaste utkastet?', [p('Dine ulagrede beløp forkastes. Ingen bokførte poster endres.')], 'Forkast og hent lagret grunnlag',async()=> { $('#sp-confirm').close();await loadPlan($('#sp-target').value,true); }); }
  async function applyHistory() {
    if(!historySelection.length){error('Velg minst én avsluttet kildemåned før du bruker forslag.',false);return;}
    const token=planningGate.begin(); const fingerprint=JSON.stringify(draft);clearError();status('Beregner forslag fra valgte måneder…');
    try { const result=await api(boot.urls.planning,{target_month:draft.target_month,history:historySelection.join(',')},{signal:token.signal});if(!token.current()||JSON.stringify(draft)!==fingerprint)return;
      if(result.source_revision!==plan.source_revision){error('Grunnlaget er endret siden du startet utkastet. Hent nytt grunnlag og avstem før du bruker forslag.',false);offerReconcile();return;}
      const suggestedCategories=result.categories.map(c=>({...c,other_ore:c.historical_other_ore===undefined?c.other_ore:c.historical_other_ore}));
      const content=[p('Forslag fra '+result.history_months.map(monthName).join(', ')+'. Disse erstatter bare øvrige kategoribeløp i utkastet. Ingen lagring.'),coverage(result.coverage)];
      for(const c of suggestedCategories)content.push(row(c.name,money(c.other_ore),`${c.observations} observasjoner · netto snitt ${money(c.historical_average_ore)}`));
      confirmDialog('Bruke historiske forslag?',content,'Bruk forslag i utkastet',()=> { draft.categories=suggestedCategories.map(c=>({id:c.id,other_ore:c.other_ore})); draft.history_months=result.history_months; draft.snapshot=result.snapshot; plan.categories=suggestedCategories; plan.coverage=result.coverage; draft.acknowledge_incomplete=false;markDirty();$('#sp-confirm').close();renderPlan();status('Forslag er lagt i utkastet. Ingenting er lagret.'); });
    }catch(e){if(token.current()&&e.name!=='AbortError')error(e.message,true,applyHistory);}
  }
  async function reviewPlan(event) {
    event.preventDefault(); if(saving||!plan||!plan.can_save)return;
    if(equation(plan,draft).planned_remainder_ore===null){error('Fyll inn alle beløp. Et tomt felt betyr ukjent.',false);return;}
    saving=true;updateEquation();clearError();status('Kontrollerer utkastet mot lagret målplan…');
    try { const fingerprint=JSON.stringify(draft), result=await api(boot.urls.preview,{}, {method:'POST',body:JSON.stringify(draft)}); if(fingerprint!==JSON.stringify(draft)){status('Utkastet er endret. Gjennomgå det på nytt.');return;} preview=result;saveKey=saveKey||crypto.randomUUID();
      const content=[p('Målmåned: '+monthName(result.target_month),'sp-coverage'),p('Eksisterende målplan for denne måneden blir erstattet med endringene nedenfor. Historiske rammer og bokførte poster beholdes.'),p('Planen lagres for målmåneden. Eksisterende regler kan videreføre beløp til senere måneder som ikke har en egen plan.')];
      if(!result.changes.length)content.push(p('Ingen endrede beløp.'));
      for(const change of result.changes)content.push(el('div',{class:'sp-change'},[el('span',{text:change.name}),el('strong',{text:money(change.before_ore)+' → '+money(change.after_ore)})]));
      content.push(equationContent(result.totals,result.draft.expected_income_ore));
      confirmDialog('Bekreft plan for '+monthName(result.target_month),content,'Bekreft og lagre månedsplan',savePlan);status('Kontrollert. Bekreft for å lagre.');
    }catch(e){error(e.status===409?'Målplanen er endret av noen andre. Utkastet beholdes. Bruk «Hent nytt grunnlag og avstem» for å sammenligne før du prøver igjen.':e.message,true,()=>reviewPlan({preventDefault(){}}));if(e.status===409)offerReconcile();}
    finally{saving=false;updateEquation();}
  }
  async function savePlan() {
    if(saving||!preview)return;
    saving=true;$('#sp-confirm-action').disabled=true;$('#sp-confirm-error').hidden=true;updateEquation();
    try { const result=await api(boot.urls.save,{}, {method:'POST',body:JSON.stringify({draft:preview.draft,confirmation_digest:preview.confirmation_digest,confirm:true,key:saveKey})});if(!result.saved)throw new Error('Lagring er ikke bekreftet. Utkastet beholdes.');
      const target=result.target_month;$('#sp-confirm').close();delete form.dataset.dirty;draft=structuredClone(preview.draft);preview=null;saveKey=null;await loadPlan(target,true);status('Månedsplanen for '+monthName(target)+' er lagret. Ingen inntekt eller utgift er bokført.');
    }catch(e){$('#sp-confirm-error').hidden=false;$('#sp-confirm-error').textContent=e.status===409?'Målplanen har endret seg. Lukk og hent nytt grunnlag for å avstemme. Utkastet beholdes.':e.message+' Utkastet beholdes; prøv igjen for samme lagringsforsøk.';if(e.status===409){preview=null;offerReconcile();}}
    finally{saving=false;$('#sp-confirm-action').disabled=!preview;updateEquation();}
  }
  function offerReconcile() {
    if($('#sp-reconcile'))return;
    const b=button('Hent nytt grunnlag og avstem',async()=> {const token=planningGate.begin();try{const fresh=await api(boot.urls.planning,{target_month:draft.target_month,history:draft.history_months.join(',')},{signal:token.signal});if(!token.current())return;
      const saved=draft.history_months.length?await api(boot.urls.planning,{target_month:draft.target_month},{signal:token.signal}):fresh;if(!token.current())return;
      if(saved.source_revision!==fresh.source_revision){error('Grunnlaget ble endret under avstemmingen. Hent det på nytt før du fortsetter.',false);return;}
      const merged=structuredClone(fresh.draft);merged.expected_income_ore=draft.expected_income_ore;
      for(const c of merged.categories){const match=draft.categories.find(r=>r.id===c.id);if(match)c.other_ore=match.other_ore;}
      for(const a of merged.assets){const match=draft.assets.find(r=>r.id===a.id);if(match)a.amount_ore=match.amount_ore;}
      const content=[p('Målmåned: '+monthName(fresh.target_month)),p('Behold egne beløp bare etter at du har sammenlignet med siste lagrede målplan. Nye forpliktelser inngår fra det nye grunnlaget.')];
      content.push(row('Sist lagret forventet inntekt',money(saved.expected_income_ore)),row('Ditt utkast',money(draft.expected_income_ore)));
      for(const c of saved.categories)content.push(row(c.name,money(c.other_ore)+' → '+money(draft.categories.find(r=>r.id===c.id)?.other_ore??null),'Sist lagret → ditt utkast'));
      for(const a of saved.assets)content.push(row(a.name,money(a.amount_ore)+' → '+money(draft.assets.find(r=>r.id===a.id)?.amount_ore??null),'Sist lagret → ditt utkast'));
      content.push(el('h3',{text:'Faste forpliktelser i nytt grunnlag'}));
      for(const item of fresh.commitments){const before=plan.commitments.find(old=>old.id===item.id);content.push(row(item.name,money(before?.amount_ore??null)+' → '+money(item.amount_ore),dateName(item.due_date)+' · '+({ordinary:'Ordinær regning',debt:'Gjeld',fund:'Fond'}[item.accounting_class]||item.accounting_class)));}
      for(const item of plan.commitments.filter(old=>!fresh.commitments.some(current=>current.id===old.id)))content.push(row(item.name,money(item.amount_ore)+' → Fjernet fra grunnlaget'));
      content.push(el('h3',{text:'Sist lagret plan'}),equationContent(saved.totals,saved.expected_income_ore),el('h3',{text:'Ditt utkast med nye forpliktelser'}),equationContent(equation(fresh,merged),merged.expected_income_ore));
      confirmDialog('Avstem endret målplan',content,'Behold mine beløp med nytt grunnlag',()=> { const old=draft;plan=fresh;draft=structuredClone(fresh.draft);draft.expected_income_ore=old.expected_income_ore;draft.history_months=old.history_months;for(const c of draft.categories){const match=old.categories.find(r=>r.id===c.id);if(match)c.other_ore=match.other_ore;}for(const a of draft.assets){const match=old.assets.find(r=>r.id===a.id);if(match)a.amount_ore=match.amount_ore;}draft.acknowledge_incomplete=false;markDirty();$('#sp-confirm').close();b.remove();clearError();renderPlan();status('Nytt grunnlag er hentet. Gjennomgå og bekreft planen på nytt før lagring.'); });
    }catch(e){if(token.current()&&e.name!=='AbortError')error(e.message,true,()=>b.click());}});b.id='sp-reconcile';$('#sp-plan-content').prepend(b);
  }
  function resetFilters() { selected.clear();$('#sp-search').value='';$('#sp-period').value='month';$('#sp-dates').hidden=true;$$('[data-sp-category-filter]').forEach(c=>c.checked=false);updateCategorySummary();loadSpending(); }
  function switchTab(next) {
    tab=next;clearError();
    for(const b of $$('[data-sp-tab]')) { const active=b.dataset.spTab===tab;b.setAttribute('aria-selected',active);b.tabIndex=active?0:-1;$('#sp-panel-'+b.dataset.spTab).hidden=!active; }
    if(tab==='spending')loadSpending();else if(tab==='annual')loadAnnual();else loadPlan();
  }
  for(const b of $$('[data-sp-tab]'))b.addEventListener('click',()=>switchTab(b.dataset.spTab));
  $('.sp-tabs').addEventListener('keydown',e=> {const buttons=$$('[data-sp-tab]'),i=buttons.indexOf(document.activeElement);if(i<0||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowRight'?1:buttons.length-1))%buttons.length;switchTab(buttons[next].dataset.spTab);buttons[next].focus();});
  $('#sp-search').addEventListener('input',()=> {spendingGate.invalidate();clearTimeout(searchTimer);status('Oppdaterer søket…');searchTimer=setTimeout(loadSpending,300);});
  $('#sp-filters').addEventListener('submit',e=>{e.preventDefault();loadSpending();});
  $('#sp-period').addEventListener('change',()=>{$('#sp-dates').hidden=$('#sp-period').value!=='custom';loadSpending();});
  for(const id of ['#sp-start','#sp-end'])$(id).addEventListener('change',loadSpending);
  for(const id of ['#sp-year','#sp-annual-category'])$(id).addEventListener('change',loadAnnual);
  $('#sp-reset').addEventListener('click',resetFilters);$('#sp-retry').addEventListener('click',()=> {if(retryAction){retryAction();return;}if(tab==='spending')loadSpending();else if(tab==='annual')loadAnnual();else loadPlan(undefined,true);});
  $('#sp-target').addEventListener('change',()=> {const target=$('#sp-target').value;if(!target||target===draft?.target_month)return; if(form.dataset.dirty==='true'&&draft){confirmDialog('Bytte målmåned?', [p('Ulagrede beløp for '+monthName(draft.target_month)+' forkastes når du bytter til '+monthName(target)+'.')],'Forkast og bytt måned',async()=> {$('#sp-confirm').close();await loadPlan(target,true);});$('#sp-target').value=draft.target_month;}else{loadPlan(target,true);}});
  form.addEventListener('submit',reviewPlan);
  $('#sp-confirm-action').addEventListener('click',()=>confirmAction&&confirmAction());
  for(const b of $$('[data-sp-close]'))b.addEventListener('click',()=> {const dialog=b.closest('dialog');if(dialog.id==='sp-confirm'&&saving)return;dialog.close();});
  $('#sp-confirm').addEventListener('cancel',e=>{if(saving)e.preventDefault();});
  $('#sp-detail').addEventListener('close',()=>detailGate.invalidate());
  window.addEventListener('offline',()=> {spendingGate.invalidate();annualGate.invalidate();planningGate.invalidate();detailGate.invalidate();error('Du er frakoblet. Ulagrede felt beholdes på denne siden. Koble til for å hente eller lagre.',false);if(plan)updateEquation();$('#sp-confirm-action').disabled=true;});
  window.addEventListener('online',()=> {if(retryAction)error('Du er tilkoblet igjen. Prøv den mislykkede handlingen på nytt.',true,retryAction);else clearError();status('Du er tilkoblet igjen. Utkastet er beholdt; ingenting er sendt automatisk.');if(plan)updateEquation();$('#sp-confirm-action').disabled=saving||(confirmAction===savePlan&&!preview);});
  $('#sp-year').value=boot.month.slice(0,4);$('#sp-start').value=boot.month+'-01';$('#sp-end').value=new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Oslo'});
  switchTab(tab);
})();
