const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('budget/static/budget/push.js', 'utf8');
const worker = fs.readFileSync('budget/static/budget/sw.js', 'utf8');
const flush = async () => { for (let n = 0; n < 6; n++) await new Promise(resolve => setImmediate(resolve)); };

function setup({permission='default', online=true, supported=true, ios=false, installed=false, serverState=null, browserSubscription=false, statusMode='', readyStalled=false, permissionStalled=false, unread=0, receiptState='pending', pushPage='varsler', subscriptionDeferred=false, calendarRestricted=false}={}) {
  const calls = [], requests = [], handlers = {}, controls = {}, timers = new Map(); let timerId=0, stalledAction='';
  for (const name of ['status','enable','disable','test','recheck','test-status','notification-badge','notification-count-text','notification-bell']) controls[name] = {hidden:name !== 'status', disabled:false, textContent:'', focus(){document.activeElement=this;calls.push('focus:'+name)}, setAttribute(name,value){this[name]=value}, handlers:{}};
  for (const name of ['enable','disable','test','recheck']) controls[name].addEventListener = (event, fn) => controls[name].handlers[event] = fn;
  const subscription = {endpoint:'https://fcm.googleapis.com/fcm/send/synthetic', options:{}, toJSON(){return {endpoint:this.endpoint,keys:{p256dh:'synthetic-public',auth:'synthetic-auth'}}}, async unsubscribe(){calls.push('unsubscribe'); current=null; return true;}};
  let current = serverState || browserSubscription ? subscription : null;
  let deferredSubscription = null;
  const reg = {pushManager:{async getSubscription(){if(subscriptionDeferred){subscriptionDeferred=false;return new Promise(resolve=>{deferredSubscription=resolve})}return current},async subscribe(options){calls.push({subscribe:options});current=subscription;return current}}};
  const navigator = {onLine:online, userAgent:ios?'iPhone':'Synthetic Browser', platform:'', maxTouchPoints:0, serviceWorker:{async register(){calls.push('register');return reg},ready:readyStalled?new Promise(()=>{}):Promise.resolve(reg)}};
  const Notification = {permission,requestPermission(){calls.push('permission');if(permissionStalled)return new Promise(()=>{});Notification.permission='granted';return Promise.resolve('granted')}};
  const root = {hidden:true,dataset:{pushConfig:'/push/config/',pushDevice:'/push/device/',pushReceipt:'/push/receipt/',pushSummary:'/push/summary/',pushPage,pushRestricted:calendarRestricted?'true':''},querySelector(){return {value:'csrf-synthetic'}}};
  let failure = false, deniedReads = null;
  const document = {visibilityState:'visible',addEventListener(name,fn){handlers[name]=fn},querySelector(){return root},getElementById(id){return controls[id.replace('push-','')]}};
  const context = {document, navigator, Notification, AbortController, setTimeout(fn,delay){timers.set(++timerId,{fn,delay});return timerId},clearTimeout(id){timers.delete(id)},window:{isSecureContext:supported,PushManager:function(){},Notification,matchMedia(){return {matches:installed}},addEventListener(name,fn){handlers[name]=fn}},Uint8Array,Promise,atob:s=>Buffer.from(s,'base64').toString('binary'),fetch:async(url,options)=>{
    requests.push({url,options});
    if(failure) throw Error('Synthetic network failure');
    const requestedAction=options?.body ? JSON.parse(options.body).action : null;
    if(deniedReads && (url==='/push/summary/' || url==='/push/receipt/' || requestedAction==='status')) {
      return {ok:false,status:403,json:async()=>{
        if(deniedReads==='html')throw new SyntaxError('Synthetic HTML permission denial');
        return {error:'Kalendertilgang er slått av. Last inn siden på nytt.'};
      }};
    }
    if(url==='/push/config/')return stalledAction==='config'?new Promise(()=>{}):{ok:true,json:async()=>({public_key:Buffer.alloc(65).toString('base64url')})};
    if(url==='/push/summary/'){calls.push('summary');return {ok:true,json:async()=>({unread})};}
    const data=JSON.parse(options.body);calls.push(data);
    if(url==='/push/receipt/')return stalledAction==='receipt'?new Promise(()=>{}):{ok:true,json:async()=>({state:receiptState})};
    if(data.action===stalledAction || (data.action==='status'&&statusMode==='stall'))return new Promise(()=>{});
    if(data.action==='status'&&statusMode==='reject')throw Error('Synthetic rejected status');
    return {ok:true,json:async()=>data.action==='status' ? {state:serverState || 'disabled',active:!!serverState,id:'device-id'} : {id:'device-id',state:data.action==='test'?'queued':'active',delivery_id:'test-job'}};
  }};
  vm.runInNewContext(source,context);
  return {calls,requests,handlers,controls,navigator,Notification,root,document,denyReads(format='json'){deniedReads=format},deferSubscription(){subscriptionDeferred=true},releaseSubscription(value=current){deferredSubscription(value)},focus(name){controls[name].focus()},setUnread(n){unread=n},setReceipt(state){receiptState=state},fail(){failure=true},stall(action){stalledAction=action},expire(delay=10000){for(const [id,t]of [...timers])if(t.delay===delay){timers.delete(id);t.fn()}},click(name){return controls[name].handlers.click()}};
}

test('push permission is requested only by explicit activation; test and disable target this device',async()=>{
  const h=setup();await flush();assert.ok(!h.calls.includes('permission'));assert.equal(h.controls.enable.hidden,false);
  await h.click('enable');assert.equal(h.calls.filter(x=>x==='permission').length,1);assert.ok(h.calls.some(x=>x.action==='subscribe'));assert.equal(h.controls.enable.hidden,true);assert.equal(h.controls.test.hidden,false);
  await h.click('test');assert.ok(h.calls.some(x=>x.action==='test'&&x.id==='device-id'));assert.match(h.controls.status.textContent,/leveringskøen/);
  await h.click('disable');assert.ok(h.calls.some(x=>x.action==='disable'));assert.ok(h.calls.includes('unsubscribe'));assert.equal(h.controls.enable.hidden,false);assert.match(h.controls.status.textContent,/Deaktivert/);
});
test('denied, unsupported, iPhone browser and offline states never pretend activation',async()=>{
  for(const options of [{permission:'denied'},{supported:false},{ios:true}]){
    const h=setup(options);await flush();assert.equal(h.controls.enable.hidden,true);assert.ok(!h.calls.includes('permission'));assert.ok(!h.calls.some(x=>x.action==='subscribe'));assert.equal(h.controls.test.hidden,true);
  }
  const h=setup({online:false});await flush();assert.equal(h.controls.enable.disabled,true);assert.match(h.controls.status.textContent,/frakoblet/);await h.click('enable');assert.ok(!h.calls.includes('permission'));
});
test('already granted permission does not prompt and server failure does not claim activation',async()=>{
  const h=setup({permission:'granted'});await flush();h.fail();await h.click('enable');assert.ok(!h.calls.includes('permission'));assert.equal(h.controls.enable.hidden,false);assert.equal(h.controls.test.hidden,true);assert.match(h.controls.status.textContent,/network failure/);
});
test('server device status and reconnection show delayed delivery honestly',async()=>{
  const h=setup({permission:'granted',serverState:'retrying'});await flush();assert.equal(h.controls.enable.hidden,true);assert.match(h.controls.status.textContent,/forsinket/);
  h.navigator.onLine=false;h.handlers.offline();assert.equal(h.controls.test.disabled,true);
  h.navigator.onLine=true;await h.handlers.online();assert.equal(h.controls.test.disabled,false);
});

test('rejected or stalled status keeps browser disable available without a confirmed test device',async()=>{
  for(const statusMode of ['reject','stall']){
    const h=setup({permission:'granted',browserSubscription:true,statusMode});await flush();
    if(statusMode==='stall')assert.equal(h.root.hidden,true);assert.equal(h.controls.test.hidden,true);
    h.expire();await flush();assert.equal(h.controls.disable.disabled,false);assert.equal(h.controls.test.hidden,true);assert.match(h.controls.status.textContent,/Status er ukjent/);
    await h.click('test');assert.ok(!h.calls.some(x=>x.action==='test'));
    await h.click('disable');assert.ok(h.calls.includes('unsubscribe'));assert.match(h.controls.status.textContent,/Deaktivert/);
  }
});
test('stalled permission, worker readiness and fetch recover busy controls after the deadline',async()=>{
  for(const options of [{permissionStalled:true},{readyStalled:true},{fetchStalled:true}]){
    const h=setup(options);await flush();if(options.fetchStalled)h.stall('config');
    const activating=h.click('enable');await flush();assert.equal(h.controls.enable.disabled,true);
    h.expire();await activating;assert.equal(h.controls.enable.disabled,false);assert.equal(h.controls.test.hidden,true);assert.match(h.controls.status.textContent,/lang tid/);
  }
});
test('stalled test and disable requests release controls and preserve the browser subscription',async()=>{
  for(const action of ['test','disable']){
    const h=setup({permission:'granted',serverState:'active'});await flush();h.stall(action);
    const pending=h.click(action);await flush();assert.equal(h.controls.disable.disabled,true);
    h.expire();await pending;assert.equal(h.controls.disable.disabled,false);assert.equal(h.controls.disable.hidden,false);assert.match(h.controls.status.textContent,/lang tid/);
  }
});

test('shared controller offers activation on every family page and hides it only for an active device',async()=>{
  const h=setup({pushPage:'oversikt',permission:'granted'});await flush();assert.equal(h.root.hidden,false);assert.equal(h.controls.enable.hidden,false);assert.ok(!h.calls.includes('permission'));
  await h.click('enable');assert.equal(h.root.hidden,true);assert.ok(!h.calls.includes('permission'));
  h.navigator.onLine=false;h.handlers.offline();assert.equal(h.root.hidden,false);
});
test('initial healthy active device panel stays hidden throughout asynchronous status checks',async()=>{
  const h=setup({pushPage:'oversikt',permission:'granted',serverState:'active',subscriptionDeferred:true});
  assert.equal(h.root.hidden,true);await flush();assert.equal(h.root.hidden,true);assert.equal(h.controls.enable.hidden,true);
  h.releaseSubscription();await flush();assert.equal(h.root.hidden,true);assert.match(h.controls.status.textContent,/Aktivert/);
  const template=fs.readFileSync('budget/templates/budget/push_preferences.html','utf8');
  // Django conditionals may surround the fallback. Inspect the HTML skeleton so
  // this still fails if noscript moves inside the initially hidden panel.
  const htmlSkeleton=template.replace(/{%[\s\S]*?%}/g,'');
  assert.match(htmlSkeleton,/<section[^>]*hidden[^>]*data-push-config/);assert.match(htmlSkeleton,/<\/section>\s*<noscript>/);
});
test('calendar-restricted family settings allow own-device disable without activation, tests or notification reads',async()=>{
  for(const browserSubscription of [false,true]){
    const h=setup({calendarRestricted:true,pushPage:'familie',permission:'granted',browserSubscription,unread:999});
    await flush();
    assert.equal(h.root.hidden,false);
    assert.equal(h.controls.enable.hidden,true);
    assert.equal(h.controls.test.hidden,true);
    assert.equal(h.controls.recheck.hidden,true);
    assert.equal(h.controls.disable.hidden,!browserSubscription);
    assert.deepEqual(h.requests,[]);
    assert.ok(!h.calls.includes('permission'));
    assert.equal(h.controls['notification-badge'].textContent,'');
    assert.match(h.controls.status.textContent,browserSubscription?/Kalendertilgang er slått av/:/Ingen nettleserabonnement/);
    h.navigator.onLine=false;h.handlers.offline();assert.equal(h.controls.disable.disabled,true);
    h.navigator.onLine=true;await h.handlers.online();
    h.document.visibilityState='hidden';h.handlers.visibilitychange();
    h.document.visibilityState='visible';h.handlers.visibilitychange();h.handlers.pageshow();
    h.expire(30000);await flush();
    // Even an obsolete test/recheck control cannot fetch a job after revocation.
    await h.click('test');await h.click('recheck');
    assert.deepEqual(h.requests,[]);
    assert.equal(h.controls.enable.hidden,true);assert.equal(h.controls.test.hidden,true);
    if(browserSubscription){
      assert.equal(h.controls.disable.disabled,false);
      await h.click('disable');
      assert.equal(h.requests.length,1);
      assert.equal(h.requests[0].url,'/push/device/');
      assert.deepEqual(JSON.parse(h.requests[0].options.body),{action:'disable',endpoint:'https://fcm.googleapis.com/fcm/send/synthetic'});
      assert.ok(h.calls.includes('unsubscribe'));
      assert.equal(h.controls.disable.hidden,true);
      assert.equal(h.controls.enable.hidden,true);assert.equal(h.controls.test.hidden,true);
      assert.match(h.controls.status.textContent,/Deaktivert/);
    }
    assert.ok(!h.calls.includes('summary'));
    assert.ok(!h.calls.some(x=>x&&typeof x==='object'&&(x.action==='subscribe'||x.action==='test'||x.action==='status')));
  }
});
test('open authorized notification page handles later JSON or HTML permission denials and still disables own device',async()=>{
  for(const format of ['json','html']){
    const h=setup({pushPage:'varsler',permission:'granted',serverState:'active',unread:4});
    await flush();
    assert.match(h.controls.status.textContent,/Aktivert/);
    assert.equal(h.controls['notification-badge'].textContent,'4');
    await h.click('test');await flush();
    assert.match(h.controls['test-status'].textContent,/venter i leveringskøen/);
    const before=h.requests.length;
    h.denyReads(format);
    h.setUnread(999); // A rejected summary must not apply this invented count.
    await h.handlers.online();await flush();
    const rejected=h.requests.slice(before);
    assert.ok(rejected.some(r=>r.url==='/push/summary/'));
    assert.ok(rejected.some(r=>r.url==='/push/receipt/'));
    assert.ok(rejected.some(r=>r.url==='/push/device/'&&JSON.parse(r.options.body).action==='status'));
    assert.match(h.controls.status.textContent,/Last inn/);
    assert.match(h.controls.status.textContent,/Status er ukjent; prøv igjen eller deaktiver/);
    assert.match(h.controls['test-status'].textContent,/Last inn/);
    assert.match(h.controls['test-status'].textContent,/Bruk Kontroller teststatus/);
    assert.equal(h.controls['notification-badge'].textContent,'4');
    assert.equal(h.controls['notification-count-text'].textContent,'4 uleste varsler');
    assert.match(h.controls['notification-bell']['aria-label'],/4 uleste/);
    assert.equal(h.controls.disable.hidden,false);
    assert.equal(h.controls.disable.disabled,false);
    assert.equal(h.controls.test.hidden,true);
    await h.click('recheck');
    assert.match(h.controls['test-status'].textContent,/Last inn/);
    await h.click('disable');
    assert.ok(h.requests.some(r=>r.url==='/push/device/'&&JSON.parse(r.options.body).action==='disable'));
    assert.ok(h.calls.includes('unsubscribe'));
    assert.match(h.controls.status.textContent,/Deaktivert på denne enheten/);
    assert.equal(h.controls.disable.hidden,true);
    assert.equal(h.controls['notification-badge'].textContent,'4');
    assert.ok(!h.calls.includes('permission'));
    assert.ok(!h.calls.some(x=>x&&typeof x==='object'&&x.action==='subscribe'));
  }
});
test('failed and retrying active device warnings remain actionable on ordinary pages',async()=>{
  for(const serverState of ['failed','retrying']){
    const h=setup({pushPage:'oversikt',permission:'granted',serverState});await flush();
    assert.equal(h.root.hidden,false);assert.equal(h.controls.disable.hidden,false);assert.equal(h.controls.test.hidden,false);
    assert.match(h.controls.status.textContent,serverState==='failed'?/feilet/:/forsinket/);
  }
});
test('delayed old getSubscription cannot overwrite a successful activation',async()=>{
  const h=setup({pushPage:'oversikt',permission:'granted'});await flush();h.deferSubscription();
  const refreshing=h.handlers.online();await flush();await h.click('enable');assert.equal(h.root.hidden,true);
  h.releaseSubscription(null);await refreshing;assert.equal(h.root.hidden,true);assert.equal(h.controls.disable.hidden,false);
  await h.click('disable');assert.ok(h.calls.some(x=>x.action==='disable'&&x.endpoint.endsWith('/synthetic')));assert.ok(h.calls.includes('unsubscribe'));
});
test('hiding activated panel moves focused activation to bell but preserves focus moved elsewhere',async()=>{
  for(const moved of [false,true]){
    const h=setup({pushPage:'oversikt',permission:'granted'});await flush();h.focus('enable');
    const activating=h.click('enable');if(moved)h.focus('status');await activating;
    assert.equal(h.root.hidden,true);assert.equal(h.document.activeElement,h.controls[moved?'status':'notification-bell']);
    assert.equal(h.calls.filter(x=>x==='focus:notification-bell').length,moved?0:1);
  }
});
test('badge keeps private server count, caps display and refreshes on visibility and online',async()=>{
  const h=setup({unread:102});await flush();assert.equal(h.controls['notification-badge'].textContent,'99+');assert.match(h.controls['notification-bell']['aria-label'],/102 uleste/);
  h.document.visibilityState='hidden';h.handlers.visibilitychange();const before=h.calls.length;h.expire(30000);await flush();assert.equal(h.calls.length,before);
  h.setUnread(0);h.document.visibilityState='visible';h.handlers.visibilitychange();await flush();assert.equal(h.controls['notification-badge'].hidden,true);assert.equal(h.controls['notification-count-text'].textContent,'Ingen uleste varsler');
  h.setUnread(2);h.handlers.online();await flush();assert.equal(h.controls['notification-badge'].textContent,'2');assert.equal(h.controls['notification-badge'].hidden,false);
});
test('test receipt distinguishes queue retry failure and provider acceptance without claiming OS delivery',async()=>{
  const h=setup({permission:'granted',serverState:'active'});await flush();await h.click('test');await flush();assert.match(h.controls['test-status'].textContent,/venter i leveringskøen/);
  h.setReceipt('retry');h.expire(2000);await flush();assert.match(h.controls['test-status'].textContent,/forsinket/);
  h.setReceipt('sent');h.expire(2000);await flush();assert.match(h.controls['test-status'].textContent,/tatt imot/);assert.match(h.controls['test-status'].textContent,/bekrefter ikke/);
  h.setReceipt('failed');await h.click('recheck');assert.match(h.controls['test-status'].textContent,/feilet/);
});
test('receipt polling stops after bounded checks and a stalled receipt recovers with manual recheck',async()=>{
  const h=setup({permission:'granted',serverState:'active'});await flush();await h.click('test');await flush();
  for(let n=0;n<8;n++){h.expire(2000);await flush()}
  assert.match(h.controls['test-status'].textContent,/Automatisk kontroll er avsluttet/);
  h.stall('receipt');const pending=h.click('recheck');await flush();h.expire();await pending;assert.match(h.controls['test-status'].textContent,/lang tid/);assert.equal(h.controls.recheck.disabled,false);
});

function swSetup(){
  const listeners={},shown=[],opened=[],navigated=[];
  const client={url:'https://blikk.example.test/app/oversikt/',async navigate(url){navigated.push(url)},async focus(){opened.push('focus')}};
  const self={location:{origin:'https://blikk.example.test'},addEventListener(n,f){listeners[n]=f},registration:{async showNotification(...args){shown.push(args)}},clients:{async matchAll(){throw Error('Existing windows must not be inspected or navigated')},async openWindow(url){opened.push(url)}}};
  vm.runInNewContext(worker,{self,URL,Request,Set,caches:{},fetch(){throw Error('Unexpected fetch')}});
  async function dispatch(name,event){let done;listeners[name]({...event,waitUntil(p){done=p}});await done}
  return {shown,opened,navigated,dispatch};
}
test('serviceworker push handler displays a generic payload and retains its stable tag',async()=>{
  const h=swSetup();await h.dispatch('push',{data:{json:()=>({body:'En ny kalenderavtale er lagt til.',url:'/push/open/12345678-1234-1234-1234-123456789abc/',tag:'job-id',private_title:'PRIVATE'})}});
  assert.equal(h.shown[0][0],'Familieblikk');assert.equal(h.shown[0][1].tag,'job-id');assert.equal(h.shown[0][1].data.url,'https://blikk.example.test/push/open/12345678-1234-1234-1234-123456789abc/');assert.doesNotMatch(JSON.stringify(h.shown),/PRIVATE/);
});
test('service worker strips unexpected private text and rejects external click targets',async()=>{
  for(const payload of [null,{body:'PRIVATE TITLE',url:'https://evil.example.test/'},{url:'//evil.example.test/'},{url:'/utlogging/'}]){
    const h=swSetup();await h.dispatch('push',{data:{json:()=>payload}});assert.doesNotMatch(JSON.stringify(h.shown),/PRIVATE TITLE/);assert.equal(h.shown[0][1].data.url,'https://blikk.example.test/app/varsler/');
    await h.dispatch('notificationclick',{notification:{data:{url:'https://evil.example.test/'},close(){}}});assert.equal(h.opened[0],'https://blikk.example.test/app/varsler/');assert.deepEqual(h.navigated,[]);
  }
});
test('notification click opens its authenticated destination separately and leaves existing dirty windows untouched',async()=>{
  const h=swSetup(),url='/push/open/12345678-1234-1234-1234-123456789abc/';
  await h.dispatch('notificationclick',{notification:{data:{url},close(){}}});
  assert.deepEqual(h.opened,['https://blikk.example.test'+url]);assert.deepEqual(h.navigated,[]);
});
