const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('C:/Users/Editor/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const out=path.join(__dirname,'evidence');fs.mkdirSync(out,{recursive:true});
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'visual-cases.json'),'utf8')).cases;
const screens=JSON.parse(fs.readFileSync(path.join(__dirname,'ui-design.json'),'utf8')).screens;
const results=[];const errors=[];
function check(name,ok,details){results.push({name,passed:!!ok,details});}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(String(e)));
 const external=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:4173')&&!r.url().startsWith('data:'))external.push(r.url())});
 const base='http://127.0.0.1:4173/.project-init/familieblikk-mockup.html';
 for(const width of [360,390,768,1024,1440]){
   await page.setViewportSize({width,height:width<700?844:1100});
   for(const s of screens){
     await page.goto(`${base}?screen=${s.id}`,{waitUntil:'load'});
     const state=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,h1:document.querySelector('main h1')?.textContent,screen:document.documentElement.dataset.screen}));
     check(`layout:${s.id}:${width}`,state.scroll<=width+1&&!!state.h1&&state.screen===s.id,state);
     check(`shared-layout:${s.id}:${width}`,await page.evaluate(()=>{
       const footer=document.querySelector('footer.app-footer');
       const profile=document.querySelector('.aside-foot .row');
       const controls=[...document.querySelectorAll('.top-actions select,.top-actions button')].map(x=>x.getBoundingClientRect());
       return !!footer&&footer.textContent.includes('Personvern')&&getComputedStyle(profile).justifyContent==='flex-start'&&document.querySelectorAll('.top-actions .avatar').length===0&&document.querySelectorAll('.aside-foot .avatar').length===1&&controls.every(x=>Math.abs(x.height-44)<1)&&[...document.querySelectorAll('main .card:not(.daily)')].every(x=>getComputedStyle(x).borderTopLeftRadius==='0px');
     }));
   }
 }
 for(const c of cases){
   await page.setViewportSize({width:c.width,height:c.height});
   await page.goto(`${base}?screen=${c.screen}&state=${c.state}`,{waitUntil:'load'});
   const p=path.join(root,c.reference);fs.mkdirSync(path.dirname(p),{recursive:true});
   // Candidate references, not human-approved references; no implementation actuals.
   await page.screenshot({path:p,animations:'disabled'});
 }
 await page.setViewportSize({width:1440,height:1100});await page.goto(base);
 await page.screenshot({path:path.join(out,'design-desktop.png'),animations:'disabled',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'design-mobile.png'),animations:'disabled'});
 await page.getByRole('button',{name:'Se beregningen'}).click();
 check('core-calculation-dialog',await page.locator('dialog').innerText().then(t=>{t=t.replace(/\s/g,' ');return t.includes('18 400')&&t.includes('6 500')}));
 await page.getByRole('button',{name:'Lukk dialog'}).click();
 await page.goto(`${base}?screen=tilpass`);
 for(const name of ['Gjeld og nedbetaling','Årsutgifter','Penger sendt til utlandet'])await page.getByRole('switch',{name,exact:true}).click();
 await page.locator('#mobile-nav').getByRole('button',{name:'Oversikt',exact:true}).click();
 check('optional-module-reconciliation',await page.locator('.hero .amount').innerText().then(t=>t.replace(/\s/g,' ').includes('11 400')));
 await page.getByRole('button',{name:'Se beregningen'}).click();
 check('optional-calculation-explained',await page.locator('dialog').innerText().then(t=>{t=t.replace(/\s/g,' ');return t.includes('3 500')&&t.includes('2 000')&&t.includes('29 950')&&t.includes('11 400')}));
 await page.getByRole('button',{name:'Lukk dialog'}).click();
 await page.locator('#mobile-nav [data-go="mer"]').click();await page.locator('main [data-go="tilpass"]').click();
 await page.getByRole('switch',{name:'Gjeld og nedbetaling',exact:true}).click();
 await page.getByRole('switch',{name:'Sparemål i oversikten',exact:true}).click();
 await page.getByRole('switch',{name:'Årsoversikt i Mer',exact:true}).click();
 await page.locator('#mobile-nav [data-go="oversikt"]').click();
 check('hiding-preserves-financial-obligations',await page.locator('.hero .amount').innerText().then(t=>t.replace(/\s/g,' ').includes('11 400')));
 check('savings-card-visibility',(await page.getByRole('heading',{name:'Sparemål',exact:true}).count())===0);
 await page.locator('#mobile-nav [data-go="mer"]').click();
 check('year-link-visibility',(await page.locator('main [data-go="arsoversikt"]').count())===0);
 await page.goto(`${base}?screen=poster&state=Member`);
 check('member-own-record-controls',(await page.locator('tbody button').count())===3);
 await page.goto(`${base}?screen=sparing&state=Member`);
 check('member-cannot-manage-goals',(await page.locator('[data-action="goal-edit"],[data-action="goal-new"]').count())===0);
 await page.goto(`${base}?screen=tilpass&state=Member`);
 check('member-cannot-change-modules',await page.getByRole('switch').evaluateAll(bs=>bs.every(b=>b.disabled)));
 await page.goto(`${base}?screen=regninger`);await page.getByRole('button',{name:'Marker betalt',exact:true}).first().click();
 check('bill-confirmation',await page.locator('dialog').innerText().then(t=>{t=t.replace(/\s/g,' ');return t.includes('én gang')&&t.includes('2 950')}));
 await page.keyboard.press('Escape');check('dialog-escape-close',!(await page.locator('dialog').evaluate(d=>d.open)));
 await page.goto(`${base}?screen=oversikt&state=Negative`);
 check('negative-visible',await page.locator('.hero .amount').innerText().then(t=>/[-−]2.400/.test(t)));
 await page.goto(`${base}?screen=innlogging`);await page.getByLabel('E-postadresse',{exact:true}).fill('demo@example.test');await page.getByRole('button',{name:'Send engangskode',exact:true}).click();await page.getByLabel('Engangskode',{exact:true}).fill('123456');await page.getByRole('button',{name:'Fortsett',exact:true}).click();
 check('demo-auth-to-family',await page.locator('h1').innerText().then(t=>t==='Gi familien et navn'));
 await page.goto(`${base}?screen=gjeld`);const first=await page.locator('main').innerText();await page.getByLabel('Strategi',{exact:true}).selectOption('snowball');check('debt-demo-has-model',first.includes('anslag')&&await page.getByLabel('Strategi',{exact:true}).inputValue()==='snowball');
 check('zero-page-errors',errors.length===0,errors);check('offline-reference-assets',external.length===0,external);
 const review='http://127.0.0.1:4173/.project-init/review.html';await page.goto(review);
 check('project-init-review-loads',await page.locator('body').innerText().then(t=>t.includes('Familieblikk')||t.includes('test 2')));
 await browser.close();
 const crypto=require('node:crypto');const sourceHashes=['.project-init/familieblikk-mockup.html','.project-init/ui-design.json'].map(p=>({path:p,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,p))).digest('hex')}));
 const report={schemaVersion:1,kind:'design-prototype-only',checkedAt:new Date().toISOString(),sourceHashes,browser:'Installed Microsoft Edge via bundled Playwright',screens:screens.length,widths:[360,390,768,1024,1440],candidateScreenshots:cases.length,humanApproved:false,applicationImplemented:false,passed:results.every(x=>x.passed),checks:results,limitations:['No backend, OTP delivery, real family isolation, persistence or installed PWA tested.','Candidate reference PNGs await human acceptance; no actual/reference implementation comparison.','Detailed secondary forms and annual 12-month table remain specified rather than fully interactive.','Project Init visual plan also demands dark-mode cases, outside approved light-only product scope.']};
 fs.writeFileSync(path.join(out,'design-checks.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({passed:report.passed,checks:results.length,failures:results.filter(x=>!x.passed),screenshots:cases.length}));
 process.exitCode=report.passed?0:1;
})().catch(e=>{fs.writeFileSync(path.join(out,'design-check-error.txt'),String(e.stack));console.error(e);process.exitCode=1});
