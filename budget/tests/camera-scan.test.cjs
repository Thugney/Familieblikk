const test = require('node:test');
const assert = require('node:assert/strict');
const {install} = require('../static/budget/camera-scan.js');
function fixture() {
  const handlers = {}, released = [];
  const element = id => ({hidden:true, value:'', files:[], textContent:'',
    addEventListener:(event, fn)=>{handlers[id+':'+event]=fn;},
    setAttribute(name,value){this[name]=value;}, removeAttribute(name){delete this[name];}, click(){this.clicked=true;}, focus(){this.focused=true;}});
  const input = element('input');
  const ids = ['camera-scan-form','camera-preview','camera-status','camera-retake','camera-clear','camera-picker'];
  const nodes = Object.fromEntries(ids.map(id=>[id,element(id)]));
  nodes['camera-scan-form'].querySelector=()=>input;
  const window={navigator:{onLine:true},addEventListener:(event,fn)=>{handlers[event]=fn;}};
  let count=0;
  install({getElementById:id=>nodes[id]}, {createObjectURL:()=>`blob:${++count}`,revokeObjectURL:url=>released.push(url)},window);
  return {handlers,released,input,nodes,window};
}
test('preview is explicit and replaced URLs are released on retake, discard and page exit',()=>{
  const f=fixture();
  f.input.files=[{type:'image/jpeg',size:500}];
  f.handlers['input:change']();
  assert.equal(f.nodes['camera-preview'].src,'blob:1');
  assert.match(f.nodes['camera-status'].textContent,/ikke sendt/);
  f.handlers['camera-retake:click']();
  assert.deepEqual(f.released,['blob:1']);
  assert.equal(f.input.clicked,true);
  f.handlers['input:change']();
  f.handlers['camera-clear:click']();
  assert.deepEqual(f.released,['blob:1','blob:2']);
  f.handlers['input:change']();
  f.handlers.pagehide();
  assert.deepEqual(f.released,['blob:1','blob:2','blob:3']);
  assert.equal(f.input.value,'');
});
test('unsupported and oversized images get no preview; offline submission is blocked',()=>{
  const f=fixture();
  for (const file of [{type:'application/pdf',size:10},{type:'image/png',size:11*1024*1024}]) {
    f.input.files=[file]; f.handlers['input:change']();
    assert.equal(f.nodes['camera-preview'].hidden,true);
    assert.match(f.nodes['camera-status'].textContent,/JPEG eller PNG/);
  }
  f.window.navigator.onLine=false;
  let prevented=false;
  f.handlers['camera-scan-form:submit']({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
});
test('manual entry discards selected image before submitting',()=>{
  const f=fixture();
  f.input.files=[{type:'image/png',size:10}];
  f.handlers['input:change']();
  f.handlers['camera-scan-form:submit']({submitter:{value:'manual'}});
  assert.deepEqual(f.released,['blob:1']);
  assert.equal(f.input.value,'');
});

test('existing-image picker removes camera hint and retake restores it',()=>{
  const f=fixture();
  f.input.capture='environment';
  f.handlers['camera-picker:click']();
  assert.equal(f.input.capture,undefined);
  assert.equal(f.input.clicked,true);
  f.handlers['camera-retake:click']();
  assert.equal(f.input.capture,'environment');
});
