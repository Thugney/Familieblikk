(() => {
  'use strict';
  const root = document.querySelector('.family-calendar');
  if (!root) return;
  const events = JSON.parse(document.getElementById('calendar-events').textContent);
  const form = document.getElementById('calendar-form');
  const detail = document.getElementById('calendar-detail');
  const editor = document.getElementById('calendar-editor');
  const confirm = document.getElementById('calendar-confirm');
  installCalendarDraftGuard(form, editor);
  const labels = {none: 'Ikke svart', yes: 'Passer', no: 'Passer ikke'};
  let active = null, editing = false, requestKey = null;
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function show(dialog) { dialog.showModal(); }
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  async function send(data, errorId, dialog) {
    const output = document.getElementById(errorId);
    output.textContent = '';
    if (!navigator.onLine) { output.textContent = 'Du er frakoblet. Koble til og prøv igjen. Feltene dine er beholdt.'; return false; }
    const buttons = dialog.querySelectorAll('button');
    const loading = window.FamilieblikkLoader?.start();
    buttons.forEach(b => b.disabled = true);
    try {
      const response = await fetch(root.dataset.api, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify(data)});
      let result;
      try { result = await response.json(); } catch { throw new Error(response.status === 403 ? 'Du har ikke rettighet til handlingen, eller økten er utløpt. Last inn på nytt.' : 'Svaret kunne ikke leses. Prøv igjen.'); }
      if (!response.ok) throw new Error(result.error || 'Handlingen er ikke tillatt. Last inn på nytt.');
      delete form.dataset.dirty;
      location.reload(); return true;
    } catch (error) { output.textContent = error.message || 'Lagring mislyktes. Prøv igjen.'; return false; }
    finally { window.FamilieblikkLoader?.stop(loading); buttons.forEach(b => b.disabled = false); }
  }
  function openDetail(event) {
    active = event;
    document.getElementById('calendar-detail-title').textContent = event.title;
    document.getElementById('calendar-detail-error').textContent = '';
    const content = document.getElementById('calendar-detail-content'); content.replaceChildren();
    content.append(node('p', formatCalendarDate(event.start, true) + (event.end !== event.start ? ' – ' + formatCalendarDate(event.end, true) : '') + (event.all_day ? ' · Heldag' : ' · ' + event.start_time + '–' + event.end_time)));
    content.append(node('p', event.scope === 'shared' ? 'Felles familieavtale' : 'Valgte familiemedlemmer'));
    if (event.recurrence !== 'none') content.append(node('p', event.recurrence === 'weekly' ? 'Gjentas ukentlig' : 'Gjentas månedlig, med siste dag i kortere måneder'));
    if (event.place) content.append(node('p', 'Sted: ' + event.place));
    if (event.note) content.append(node('p', event.note, 'calendar-note'));
    if (event.warning) content.append(node('p', event.warning + ' Oppretter eller administrator må avklare tidspunktet.', 'notice'));
    content.append(node('h3', 'Passer avtalen?'));
    event.people.forEach(person => {
      const row = node('div', undefined, 'calendar-response');
      row.append(node('strong', person.name), node('span', labels[person.status]));
      if (person.self) {
        const controls = node('div', undefined, 'calendar-response-actions');
        Object.entries(labels).forEach(([status,label]) => {
          const button = node('button', label, 'secondary'); button.type = 'button'; button.setAttribute('aria-pressed', String(person.status === status));
          const key = crypto.randomUUID();
          button.addEventListener('click', () => send({action:'respond',key,event_id:event.id,original:event.original,revision:event.revision,status,response_revision:person.revision}, 'calendar-detail-error', detail));
          controls.append(button);
        }); row.append(controls);
      }
      content.append(row);
    });
    if (!event.people.some(p => p.self)) content.append(node('p', 'Du kan lese svarene. Bare avtalens deltakere kan svare for seg selv.'));
    document.getElementById('calendar-edit').hidden = !event.editable;
    document.getElementById('calendar-delete').hidden = !event.editable;
    if (!event.editable) content.append(node('p','Bare oppretter eller administrator kan endre denne avtalen.'));
    show(detail);
  }
  document.querySelectorAll('[data-event]').forEach(button => button.addEventListener('click', () => openDetail(events.find(e => e.id === button.dataset.event && e.original === button.dataset.original))));
  function updateFields() {
    const allDay=form.elements.all_day.checked;
    ['start_time','end_time','fold'].forEach(name => { form.elements[name].closest('.calendar-fields > div').hidden=allDay; });
    document.getElementById('id_participants').closest('.calendar-fields > div').hidden=form.elements.scope.value !== 'selected';
    form.elements.until.closest('.calendar-fields > div').hidden=form.elements.recurrence.value === 'none';
  }
  function openEditor(event=null, day=null) {
    editing=!!event; active=event; requestKey=crypto.randomUUID(); form.reset();
    document.getElementById('calendar-form-error').textContent='';
    document.getElementById('calendar-edit-policy').hidden=!editing;
    document.getElementById('calendar-editor-title').textContent=editing ? 'Endre avtale' : 'Ny avtale';
    const p=event || {start:day || new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Oslo'}),start_time:'17:00',end_time:'18:00',scope:'shared',recurrence:'none'};
    ['title','start','end','start_time','end_time','place','note','scope','recurrence','until','fold'].forEach(name => { form.elements[name].value = p[name] ?? (name==='end' ? p.start : ''); });
    form.elements.all_day.checked=!!p.all_day;
    form.querySelectorAll('[name=participants]').forEach(input => input.checked=(p.participants || []).includes(input.value));
    document.getElementById('calendar-edit-scope').hidden=!(editing && event.recurrence!=='none');
    form.querySelector('[name=edit_scope][value=one]').checked=true;
    // Show exactly which future exceptions would be replaced, including moved occurrences.
    const future=editing ? (event.future_exceptions || []) : [];
    document.getElementById('calendar-future-warning').textContent='Fra originaldato '+(event ? formatCalendarDate(event.original) : '')+': tidligere avtaler og unntak bevares. Fremtidige unntak erstattes.'+(future.length ? ' Synlige unntak: '+future.map(e=>e.title+' ('+formatCalendarDate(e.original)+' → '+formatCalendarDate(e.start)+')').join(', ')+'.' : '')+' Svar nullstilles ved endret dato, tid eller deltakere, og på fremtidige unntak som erstattes med en endret avtale. Uendrede avtaler beholder svar ved endring av tittel, sted og notat.';
    ['recurrence','until'].forEach(name => form.elements[name].disabled=editing && form.elements.edit_scope.value==='one');
    updateFields(); show(editor);
  }
  document.getElementById('calendar-create').addEventListener('click', () => openEditor());
  // The quick menu's "Familieavtale" opens the new-event editor directly.
  if (location.hash === '#ny-avtale') { history.replaceState(null, '', location.pathname + location.search); openEditor(); }
  let selectedDay = new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Oslo'});
  function selectDay(day) {
    selectedDay=day;
    document.querySelectorAll('[data-select-date]').forEach(button=>{ const selected=button.dataset.selectDate===day; button.setAttribute('aria-pressed',String(selected)); button.closest('.calendar-day').classList.toggle('selected',selected); });
    document.getElementById('calendar-selected-day').textContent=new Intl.DateTimeFormat('nb-NO',{weekday:'long',day:'numeric',month:'long',timeZone:'Europe/Oslo'}).format(new Date(day+'T12:00:00Z'));
    const container=document.getElementById('calendar-selected-events');container.replaceChildren();
    const matching=events.filter(event=>event.start<=day && event.display_end>=day);
    matching.forEach(event=>{
      const button=node('button',undefined,'calendar-day-event');button.type='button';
      button.append(node('small',event.all_day?'Heldag':event.start_time),node('strong',event.title),node('span',event.scope==='shared'?'Felles familieavtale':event.people.map(p=>p.name).join(', ')));
      button.addEventListener('click',()=>openDetail(event));container.append(button);
    });
    if (!matching.length) container.append(node('p','Ingen avtaler denne dagen.','calendar-help'));
  }
  document.querySelectorAll('[data-select-date]').forEach(button=>button.addEventListener('click',()=>selectDay(button.dataset.selectDate)));
  document.getElementById('calendar-add-selected').addEventListener('click',()=>openEditor(null,selectedDay));
  if (!document.querySelector('[data-select-date="'+selectedDay+'"]')) selectedDay=document.querySelector('[data-select-date]')?.dataset.selectDate || selectedDay;
  selectDay(selectedDay);
  form.querySelectorAll('[name=edit_scope]').forEach(input=>input.addEventListener('change',()=>{ ['recurrence','until'].forEach(name=>form.elements[name].disabled=form.elements.edit_scope.value==='one'); }));
  ['all_day','scope','recurrence'].forEach(name=>form.elements[name].addEventListener('change',updateFields));
  form.addEventListener('input',()=>{ requestKey=crypto.randomUUID(); });
  document.getElementById('calendar-edit').addEventListener('click',()=>{ const event=active; detail.close(); openEditor(event); });
  document.getElementById('calendar-delete').addEventListener('click',()=>{
    detail.close(); requestKey=crypto.randomUUID();
    document.getElementById('calendar-delete-error').textContent='';
    document.getElementById('calendar-delete-description').textContent=active.title+' · opprinnelig '+formatCalendarDate(active.original)+'. Fremtidige unntak som også slettes ved fremtidig omfang: '+(active.future_exceptions || []).map(e=>formatCalendarDate(e.original)+' ('+e.title+')').join(', ');
    document.getElementById('calendar-delete-scope').hidden=active.recurrence==='none';
    document.querySelector('[name=delete_scope][value=one]').checked=true; show(confirm);
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault(); const payload={};
    ['title','start','end','start_time','end_time','place','note','scope','recurrence','until'].forEach(name=>payload[name]=form.elements[name].value);
    payload.all_day=form.elements.all_day.checked;
    payload.fold=form.elements.fold.value==='' ? null : Number(form.elements.fold.value);
    payload.participants=[...form.querySelectorAll('[name=participants]:checked')].map(el=>el.value);
    await send({action:editing?'edit':'create',key:requestKey,...(editing?{event_id:active.id,original:active.original,revision:active.revision,scope:form.elements.edit_scope.value}:{}),payload},'calendar-form-error',editor);
  });
  document.getElementById('calendar-delete-form').addEventListener('submit',event=>{
    event.preventDefault(); send({action:'delete',key:requestKey,event_id:active.id,original:active.original,revision:active.revision,scope:document.querySelector('[name=delete_scope]:checked').value},'calendar-delete-error',confirm);
  });
  const monthButton=document.getElementById('calendar-month-view'), agendaButton=document.getElementById('calendar-agenda-view');
  function view(agenda) { root.classList.toggle('agenda-mode',agenda); monthButton.setAttribute('aria-pressed',String(!agenda)); agendaButton.setAttribute('aria-pressed',String(agenda)); }
  view(window.matchMedia('(max-width:760px)').matches);
  monthButton.addEventListener('click',()=>view(false)); agendaButton.addEventListener('click',()=>view(true));
  const target = new URLSearchParams(location.search);
  const notifiedEvent = events.find(event => event.id === target.get('event') && event.original === target.get('original'));
  if (notifiedEvent) { selectDay(notifiedEvent.start); openDetail(notifiedEvent); }
})();

// Closing the editor is an explicit discard action, including the native Escape key.
// While it stays open, app.js protects dirty fields across offline/reconnect events.
function installCalendarDraftGuard(form, dialog) {
  dialog.addEventListener('close', () => {
    delete form.dataset.dirty;
    form.reset();
  });
}

function formatCalendarDate(value, detailed = false) {
  if (!value) return 'slettet';
  return new Intl.DateTimeFormat('nb-NO', detailed
    ? {weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Oslo'}
    : {day:'numeric',month:'short',timeZone:'Europe/Oslo'})
    .format(new Date(value + 'T12:00:00Z'));
}
