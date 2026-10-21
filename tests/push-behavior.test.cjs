const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('budget/static/budget/push.js', 'utf8');
const worker = fs.readFileSync('budget/static/budget/sw.js', 'utf8');
const flush = async () => { for (let n = 0; n < 6; n++) await new Promise(resolve => setImmediate(resolve)); };

function setup({permission='default', online=true, supported=true, ios=false, installed=false, serverState=null, browserSubscription=false, statusMode='', readyStalled=false, permissionStalled=false}={}) {
  const calls = [], handlers = {}, controls = {}, timers = new Map(); let timerId=0, stalledAction='';
  for (const name of ['status','enable','disable','test']) controls[name] = {hidden:name !== 'status', disabled:false, textContent:'', addEventListener:(name, fn) => controls[name === 'click' ? 'unused' : name], handlers:{}};
  for (const name of ['enable','disable','test']) controls[name].addEventListener = (event, fn) => controls[name].handlers[event] = fn;
  const subscription = {endpoint:'https://fcm.googleapis.com/fcm/send/synthetic', options:{}, toJSON(){return {endpoint:this.endpoint,keys:{p256dh:'synthetic-public',auth:'synthetic-auth'}}}, async unsubscribe(){calls.push('unsubscribe'); current=null; return true;}};
  let current = serverState || browserSubscription ? subscription : null;
  const reg = {pushManager:{async getSubscription(){return current},async subscribe(options){calls.push({subscribe:options});current=subscription;return current}}};
  const navigator = {onLine:online, userAgent:ios?'iPhone':'Synthetic Browser', platform:'', maxTouchPoints:0, serviceWorker:{async register(){calls.push('register');return reg},ready:readyStalled?new Promise(()=>{}):Promise.resolve(reg)}};
  const Notification = {permission,requestPermission(){calls.push('permission');if(permissionStalled)return new Promise(()=>{});Notification.permission='granted';return Promise.resolve('granted')}};
  const root = {dataset:{pushConfig:'/push/config/',pushDevice:'/push/device/'},querySelector(){return {value:'csrf-synthetic'}}};
  let failure = false;
  const context = {document:{querySelector(){return root},getElementById(id){return controls[id.replace('push-','')]}}, navigator, Notification, AbortController, setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout(id){timers.delete(id)},window:{isSecureContext:supported,PushManager:function(){},Notification,matchMedia(){return {matches:installed}},addEventListener(name,fn){handlers[name]=fn}},Uint8Array,Promise,atob:s=>Buffer.from(s,'base64').toString('binary'),fetch:async(url,options)=>{
    if(failure) throw Error('Synthetic network failure');
    if(url==='/push/config/')return stalledAction==='config'?new Promise(()=>{}):{ok:true,json:async()=>({public_key:Buffer.alloc(65).toString('base64url')})};
    const data=JSON.parse(options.body);calls.push(data);
    if(data.action===stalledAction || (data.action==='status'&&statusMode==='stall'))return new Promise(()=>{});
    if(data.action==='status'&&statusMode==='reject')throw Error('Synthetic rejected status');
    return {ok:true,json:async()=>data.action==='status' ? {state:serverState || 'disabled',active:!!serverState,id:'device-id'} : {id:'device-id',state:data.action==='test'?'queued':'active'}};
  }};
  vm.runInNewContext(source,context);
  return {calls,handlers,controls,navigator,Notification,fail(){failure=true},stall(action){stalledAction=action},expire(){for(const [id,fn]of [...timers]){timers.delete(id);fn()}},click(name){return controls[name].handlers.click()}};
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
    assert.equal(h.controls.disable.hidden,false);assert.equal(h.controls.test.hidden,true);
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
