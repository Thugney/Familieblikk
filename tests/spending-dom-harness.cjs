// A small in-memory DOM for executing the real module's event handlers in Node.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {randomUUID} = require('node:crypto');

class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.parentElement=null;this.attributes={};this.dataset={};this.listeners={};this.style={setProperty(){}};this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false; }
  set id(value){this.attributes.id=value;} get id(){return this.attributes.id||'';}
  set className(value){this.attributes.class=value;} get className(){return this.attributes.class||'';}
  set textContent(value){this.children=[];this.text=String(value);} get textContent(){return (this.text||'')+this.children.map(c=>c.textContent).join('');}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==='value')this.value=String(value);if(key==='hidden')this.hidden=true;if(key==='disabled')this.disabled=true;if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value);}
  getAttribute(key){if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]??null;return this.attributes[key]??null;}
  append(...nodes){for(const node of nodes){node.parentElement=this;node.ownerDocument=this.ownerDocument;this.children.push(node);}}
  prepend(node){node.parentElement=this;this.children.unshift(node);}
  replaceChildren(...nodes){this.children.forEach(c=>c.parentElement=null);this.children=[];this.text='';this.append(...nodes);}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);this.parentElement=null;}
  addEventListener(type,listener){(this.listeners[type]??=[]).push(listener);}
  async dispatch(type,values={}){const event={type,target:this,key:'',preventDefault(){this.defaultPrevented=true;},...values};for(const listener of this.listeners[type]||[])await listener(event);await settle();return event;}
  async click(){if(!this.disabled)await this.dispatch('click');}
  showModal(){this.open=true;}close(){this.open=false;for(const listener of this.listeners.close||[])listener({target:this});}
  focus(){if(this.ownerDocument)this.ownerDocument.activeElement=this;}
  matches(selector){
    if(selector.endsWith(':checked'))return this.checked&&this.matches(selector.slice(0,-8));
    if(selector.startsWith('#'))return this.id===selector.slice(1);
    if(selector.startsWith('.'))return this.className.split(' ').includes(selector.slice(1));
    const attribute=selector.match(/^\[([^=\]]+)(?:=["']?([^\]"']+)["']?)?\]$/);
    if(attribute){const actual=this.getAttribute(attribute[1]);return actual!==null&&(attribute[2]===undefined||actual===attribute[2]);}
    return this.tagName===selector;
  }
  querySelectorAll(selector){const all=[];const visit=node=>{for(const child of node.children){if(child.matches(selector))all.push(child);visit(child);}};visit(this);return all;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){let node=this;while(node){if(node.matches(selector))return node;node=node.parentElement;}return null;}
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(target='2026-11') {
  return {target_month:target,can_save:true,snapshot:'a'.repeat(64),source_revision:'same',history_months:[],history_options:[{month:'2026-09',entry_count:1,status:'partial'}],coverage:{requires_acknowledgement:false,unresolved_import_count:0,warning:''},expected_income_ore:100000,income_source:'existing_plan',categories:[{id:'food',name:'Mat',other_ore:20000,fixed_ore:0,source:'existing_plan',historical_average_ore:20000,historical_other_ore:20000,observations:1}],assets:[],commitments:[],totals:{ordinary_fixed_ore:0,other_categories_ore:20000,savings_ore:0,debt_ore:0,funds_ore:0,planned_remainder_ore:80000},draft:{target_month:target,history_months:[],snapshot:'a'.repeat(64),expected_income_ore:100000,categories:[{id:'food',other_ore:20000}],assets:[],acknowledge_incomplete:false}};
}
async function harness(options={}) {
  const root=new Element('section');root.setAttribute('data-spending-workspace','');
  const add=(id,parent=root,tag='div')=>{const node=new Element(tag);node.id=id;parent.append(node);return node;};
  const boot=add('spending-boot');boot.textContent=JSON.stringify({initial_tab:options.initial_tab||'planning',plan_month:options.plan_month,can_plan:options.can_plan,can_annual:options.can_annual,month:'2026-10',urls:{spending:'/spending',planning:'/planning',preview:'/preview',save:'/save'}});
  const tabs=new Element();tabs.className='sp-tabs';root.append(tabs);
  for(const name of ['spending','annual','planning']){const b=add('sp-tab-'+name,tabs,'button');b.setAttribute('data-sp-tab',name);add('sp-panel-'+name);}
  for(const id of ['sp-status','sp-error','sp-retry','sp-results','sp-search','sp-period','sp-start','sp-end','sp-year','sp-annual-category','sp-annual-results','sp-reset','sp-dates','sp-category-summary','sp-category-options','sp-filters','sp-detail','sp-detail-title','sp-detail-content','sp-confirm','sp-confirm-title','sp-confirm-content','sp-confirm-error','sp-confirm-action'])add(id,root,['sp-detail','sp-confirm'].includes(id)?'dialog':'div');
  const form=add('sp-plan-form',root.querySelector('#sp-panel-planning'),'form');
  add('sp-target',form,'input');add('sp-plan-heading',form);add('sp-plan-content',form);
  const csrf=new Element('input');csrf.setAttribute('name','csrfmiddlewaretoken');csrf.value='synthetic-csrf';form.append(csrf);
  const close=add('close-confirm',root.querySelector('#sp-confirm'),'button');close.setAttribute('data-sp-close','');
  const document={querySelector:s=>root.matches(s)?root:root.querySelector(s),createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),createTextNode:t=>{const n=new Element('#text');n.textContent=t;return n;}};
  const attachDocument=node=>{node.ownerDocument=document;node.children.forEach(attachDocument);};attachDocument(root);
  const window=new Element('window'),navigator={onLine:true},requests=[];
  let failPlanning=0,failPreview=0;
  const fetch=async(url,request={})=>{
    const parsed=new URL(url),body=request.body?JSON.parse(request.body):null;requests.push({path:parsed.pathname,target:parsed.searchParams.get('target_month'),method:request.method||'GET',body});
    if(parsed.pathname==='/planning'){
      if(failPlanning){--failPlanning;throw new Error('Synthetic planning load failed');}
      const data=fixture(parsed.searchParams.get('target_month')||'2026-11');data.history_months=parsed.searchParams.get('history')?.split(',')||[];data.draft.history_months=data.history_months;return response(data);
    }
    if(parsed.pathname==='/preview'){
      if(failPreview){--failPreview;throw new Error('Synthetic preview failed');}
      const data=fixture(body.target_month);return response({target_month:body.target_month,draft:body,changes:[{name:'Inntekt',before_ore:100000,after_ore:body.expected_income_ore}],totals:data.totals,confirmation_digest:'confirm-digest'});
    }
    if(parsed.pathname==='/save')return response({saved:true,target_month:body.draft.target_month});
    if(parsed.pathname==='/spending')return response(options.spending||{category_options:[],categories:[],coverage:{unresolved_import_count:0},total_ore:12345,trend:Array.from({length:12},(_,i)=>({month:'2026-'+String(i+1).padStart(2,'0'),amount_ore:i===8?12345:null,has_entries:i===8,status:i===8?'partial':'missing'}))});
    throw new Error('Unexpected endpoint '+parsed.pathname);
  };
  const response=data=>({ok:true,redirected:false,json:async()=>data});
  const context=vm.createContext({document,window,navigator,Node:Element,fetch,URL,Intl,Date,AbortController,structuredClone,crypto:{randomUUID},setTimeout,clearTimeout,location:{origin:'https://family.test'},console});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../budget/static/budget/spending.js'),'utf8'),context);
  await settle();await settle();
  return {root,form,requests,document,$:selector=>root.querySelector(selector),async keydown(key){return tabs.dispatch('keydown',{key});},async input(selector,value){const node=root.querySelector(selector);node.value=value;await node.dispatch('input');},async change(selector,value){const node=root.querySelector(selector);node.value=value;await node.dispatch('change');},async online(value){navigator.onLine=value;await window.dispatch(value?'online':'offline');},failPlanning(){failPlanning++;},failPreview(){failPreview++;},settle};
}
module.exports={harness,Element};
