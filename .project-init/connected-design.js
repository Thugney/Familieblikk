// Decorate the existing prototype without replacing its navigation or financial behavior.
(()=>{
 document.querySelectorAll('.top-actions .avatar').forEach(profile=>profile.remove());
 const bar=document.querySelector('.preview');
 const options=document.createElement('details');options.innerHTML='<summary>Designvalg</summary><div class="design-options"></div>';
 const tray=options.querySelector('div');
 for(const id of ['preview-screen','preview-state']){const control=document.getElementById(id);const label=bar.querySelector(`label[for="${id}"]`);if(label)tray.append(label);tray.append(control)}
 bar.querySelector('.spacer')?.remove();bar.append(options);
 const footer=document.createElement('footer');footer.className='app-footer';footer.innerHTML='<div><strong>Familieblikk</strong><p>Designforslag · Fiktive familiedata · Ingenting lagres</p></div><div><button type="button" data-footer="privacy">Personvern</button><button type="button" data-footer="help">Hjelp og kontakt</button></div>';
 document.querySelector('.workspace').append(footer);
 footer.addEventListener('click',e=>{const key=e.target.closest('[data-footer]')?.dataset.footer;if(key)dialog(key==='privacy'?'Personvern':'Hjelp og kontakt',key==='privacy'?'<p>Dette designforslaget bruker bare fiktive familiedata. Ingen opplysninger lagres. Appens personvernerklæring utarbeides før lansering.</p>':'<p>Dette er en interaktiv designprototype. Bruk Designvalg øverst for å prøve ulike sider og tilstander. Kontaktfunksjonen er ikke satt opp ennå.</p>')});
 const prior=render;
 render=function(){prior();const main=document.getElementById('main');
  if(!['Empty','Loading','Offline','Error'].includes(state)){
   const copy={oversikt:['Familiens økonomi','Inntekter, utgifter og planer for oktober.'],poster:['Inntekter og utgifter'],budsjett:['Månedsbudsjett'],sparing:['Sparemål'],mer:['Flere oversikter']};
   const c=copy[screen];if(c){const h=main.querySelector('h1');if(h)h.textContent=c[0];if(c[1]){const p=main.querySelector('.pagehead p');if(p)p.textContent=c[1]}}
  }
  const hero=main.querySelector('.hero-grid'),metrics=main.querySelector('.mini-grid');
  if(screen==='oversikt'&&hero&&metrics){const flow=document.createElement('div');flow.className='overview-flow';hero.before(flow);flow.append(hero,metrics)}
  const labels={'Hvor går pengene?':'Forbruk per kategori','Mer rom i hverdagen':'Forbruk over tid','Små steg. Felles mål.':'Sparemål'};
  main.querySelectorAll('h2').forEach(h=>{if(labels[h.textContent])h.textContent=labels[h.textContent]});
 };
 applyPreview();
})();
