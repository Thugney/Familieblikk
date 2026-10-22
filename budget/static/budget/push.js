(() => {
  'use strict';
  const root = document.querySelector('[data-push-config]');
  if (!root) return;
  const status = document.getElementById('push-status');
  const enable = document.getElementById('push-enable');
  const disable = document.getElementById('push-disable');
  const test = document.getElementById('push-test');
  const recheck = document.getElementById('push-recheck');
  const testStatus = document.getElementById('push-test-status');
  const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  let subscription = null, deviceId = null, registration = null, busy = false;
  let lastDelivery = null, receiptTimer = null, receiptGeneration = 0, summaryTimer = null, refreshing = false;
  let deviceGeneration = 0, unreadGeneration = 0;
  let bindingState = 'unknown';
  const supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const installed = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  function message(text) { status.textContent = text; }
  function testMessage(text) { testStatus.hidden = false; testStatus.textContent = text; }
  function controls(active) {
    const hidePanel = active && bindingState === 'active' && root.dataset.pushPage !== 'varsler';
    if (hidePanel && !root.hidden && document.activeElement === enable) document.getElementById('notification-bell').focus();
    root.hidden = hidePanel;
    enable.hidden = active; disable.hidden = !subscription; test.hidden = !active;
    if (supported && Notification.permission === 'denied') enable.hidden = true;
    enable.disabled = busy || !navigator.onLine; disable.disabled = busy || !navigator.onLine; test.disabled = busy || !navigator.onLine || !deviceId;
    recheck.hidden = !lastDelivery; recheck.disabled = busy || !navigator.onLine;
  }
  function bounded(promise, cancel = () => {}) {
    let timer;
    const deadline = new Promise((_, reject) => { timer = setTimeout(() => { cancel(); reject(new Error('Det tok for lang tid å kontrollere varsler. Prøv igjen, eller deaktiver denne enheten.')); }, 10000); });
    return Promise.race([promise, deadline]).finally(() => clearTimeout(timer));
  }
  async function requestJson(url, options) {
    const controller = new AbortController();
    return bounded((async () => {
      const response = await fetch(url, {...options, signal:controller.signal});
      let result;
      try { result = await response.json(); } catch { throw new Error('Økten kan være utløpt. Last inn og logg inn på nytt.'); }
      if (!response.ok || response.redirected) throw new Error(result.error || 'Varsler kunne ikke oppdateres. Prøv igjen.');
      return result;
    })(), () => controller.abort());
  }
  async function post(data, url = root.dataset.pushDevice) {
    if (!navigator.onLine) throw new Error('Du er frakoblet. Koble til før du endrer varsler.');
    return requestJson(url, {method:'POST', credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf}, body:JSON.stringify(data)});
  }
  async function refreshUnread() {
    clearTimeout(summaryTimer);
    const generation = ++unreadGeneration;
    if (document.visibilityState === 'hidden') return;
    try {
      if (!navigator.onLine) return;
      const result = await requestJson(root.dataset.pushSummary, {credentials:'same-origin', cache:'no-store'});
      if (generation !== unreadGeneration || document.visibilityState === 'hidden') return;
      if (!Number.isSafeInteger(result.unread) || result.unread < 0) return;
      const count = result.unread, badge = document.getElementById('notification-badge');
      badge.hidden = count === 0; badge.textContent = count > 99 ? '99+' : String(count);
      document.getElementById('notification-count-text').textContent = count ? `${count} uleste varsler` : 'Ingen uleste varsler';
      document.getElementById('notification-bell').setAttribute('aria-label', count ? `Varsler, ${count} uleste` : 'Varsler, ingen uleste');
    } catch { /* Retain server-rendered count; never invent an empty state. */ }
    finally { if (generation === unreadGeneration) summaryTimer = setTimeout(refreshUnread, 30000); }
  }
  async function checkReceipt(generation, remaining = 8) {
    if (generation !== receiptGeneration || !lastDelivery) return;
    if (!navigator.onLine || document.visibilityState === 'hidden') return;
    try {
      const result = await post({delivery_id:lastDelivery}, root.dataset.pushReceipt);
      if (generation !== receiptGeneration) return;
      const labels = {
        pending:'Testvarselet venter i leveringskøen. Arbeideren har ikke sendt det ennå.',
        sending:'Arbeideren sender testvarselet til pushtjenesten.',
        retry:'Levering er forsinket. Arbeideren prøver igjen automatisk.',
        sent:'Pushtjenesten har tatt imot testvarselet. Dette bekrefter ikke at operativsystemet har vist det. Sjekk nettleserens og enhetens varselinnstillinger hvis det ikke dukker opp.',
        failed:'Testleveringen feilet. Kontroller enhetens varsler, eller deaktiver og aktiver igjen.',
        cancelled:'Testleveringen er stoppet. Aktiver varsler på nytt for denne innloggingen.'
      };
      testMessage(labels[result.state] || 'Leveringsstatus er ukjent. Kontroller teststatus igjen.');
      if (['pending','sending','retry'].includes(result.state)) {
        if (remaining > 1) receiptTimer = setTimeout(() => checkReceipt(generation, remaining - 1), 2000);
        else testMessage(testStatus.textContent + ' Automatisk kontroll er avsluttet; bruk Kontroller teststatus for å sjekke igjen.');
      }
    } catch (error) { if (generation === receiptGeneration) testMessage(error.message + ' Bruk Kontroller teststatus når forbindelsen er tilbake.'); }
  }
  function startReceiptCheck() {
    clearTimeout(receiptTimer);
    const generation = ++receiptGeneration;
    return checkReceipt(generation);
  }
  async function refresh() {
    const generation = deviceGeneration;
    if (!supported) { controls(false); enable.hidden = true; message(ios && !installed ? 'På iPhone må du først legge Familieblikk til på Hjem-skjerm og åpne appen derfra.' : 'Denne nettleseren støtter ikke enhetsvarsler her. Bruk kalenderoversikten nedenfor. Varsler krever HTTPS eller localhost.'); return; }
    if (ios && !installed) { controls(false); enable.hidden = true; message('Legg først Familieblikk til på Hjem-skjerm via Del-menyen. Åpne appen derfra for å aktivere varsler.'); return; }
    if (!navigator.onLine) { controls(Boolean(deviceId)); message('Du er frakoblet. Status kontrolleres når du er på nett igjen.'); return; }
    if (Notification.permission === 'denied') { controls(false); enable.hidden = true; message('Varsler er avslått i nettleseren. Endre tillatelsen i nettleserens innstillinger hvis du vil aktivere dem.'); return; }
    let candidateRegistration = null, candidateSubscription = null;
    try {
      candidateRegistration = await bounded(navigator.serviceWorker.register('/sw.js', {scope:'/'}));
      candidateSubscription = await bounded(candidateRegistration.pushManager.getSubscription());
      if (generation !== deviceGeneration) return;
      if (!candidateSubscription) { registration = candidateRegistration; subscription = null; deviceId = null; bindingState = 'disabled'; controls(false); message('Varsler er ikke aktivert på denne enheten.'); return; }
      await bounded(navigator.serviceWorker.ready);
      if (generation !== deviceGeneration) return;
      const result = await post({action:'status', endpoint:candidateSubscription.endpoint});
      if (generation !== deviceGeneration) return;
      registration = candidateRegistration; subscription = candidateSubscription;
      deviceId = result.active ? result.id : null;
      bindingState = result.state;
      controls(Boolean(deviceId));
      const labels = {active:'Aktivert på denne enheten.', retrying:'Aktivert. Levering er forsinket og prøves igjen.', failed:'Levering feilet. Deaktiver og aktiver igjen, eller prøv et testvarsel.', expired:'Økten eller abonnementet er utgått. Aktiver varsler på nytt.', disabled:'Varsler er ikke aktivert for denne innloggingen.'};
      message(labels[result.state] || labels.disabled);
    } catch (error) { if(generation !== deviceGeneration) return; if(candidateSubscription) { registration = candidateRegistration; subscription = candidateSubscription; } deviceId = null; bindingState = 'unknown'; controls(false); message((error.message || 'Kunne ikke kontrollere varsler.') + ' Status er ukjent; prøv igjen eller deaktiver denne enheten.'); }
  }
  enable.addEventListener('click', async () => {
    if (busy || !navigator.onLine) return;
    // Request permission directly in the user gesture, before asynchronous I/O.
    deviceGeneration++; busy = true; controls(false); message('Aktiverer varsler …');
    try {
      const permission = Notification.permission === 'granted' ? Promise.resolve('granted') : Notification.requestPermission();
      if (await bounded(permission) !== 'granted') { await refresh(); return; }
      registration = await bounded(navigator.serviceWorker.register('/sw.js', {scope:'/'}));
      await bounded(navigator.serviceWorker.ready);
      const config = await requestJson(root.dataset.pushConfig, {credentials:'same-origin', cache:'no-store'});
      const bytes = Uint8Array.from(atob(config.public_key.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
      subscription = await bounded(registration.pushManager.getSubscription());
      if (subscription) {
        const existingKey = subscription.options && subscription.options.applicationServerKey;
        if (existingKey && !equalPushKeys(existingKey, bytes)) { await bounded(subscription.unsubscribe()); subscription = null; }
      }
      if (!subscription) subscription = await bounded(registration.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:bytes}));
      const result = await post({action:'subscribe', subscription:subscription.toJSON()});
      deviceId = result.id; bindingState = 'active'; message('Aktivert på denne enheten. Send gjerne et testvarsel til deg selv.');
    } catch (error) { deviceId = null; message(error.message || 'Kunne ikke aktivere varsler. Prøv igjen.'); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  disable.addEventListener('click', async () => {
    if (busy) return;
    deviceGeneration++; busy = true; controls(true);
    try {
      await post({action:'disable', endpoint:subscription.endpoint});
      clearTimeout(receiptTimer); receiptGeneration++; lastDelivery = null; testStatus.hidden = true;
      deviceId = null;
      try { await bounded(subscription.unsubscribe()); } catch { /* Server has stopped delivery. */ }
      subscription = null; message('Deaktivert på denne enheten. Kalenderoversikten beholdes.');
    } catch (error) { message(error.message); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  test.addEventListener('click', async () => {
    if (busy || !deviceId) return;
    busy = true; controls(true);
    try {
      const result = await post({action:'test', id:deviceId});
      message('Testvarselet ligger i leveringskøen. Kontrollerer arbeiderens levering …');
      lastDelivery = result.delivery_id;
      testMessage('Testvarselet venter i leveringskøen. Dette er ikke en bekreftelse på visning.');
      if (lastDelivery) startReceiptCheck();
    }
    catch (error) { message(error.message); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  async function refreshDevice() {
    if (busy || refreshing || document.visibilityState === 'hidden') return;
    refreshing = true;
    try { await refresh(); } finally { refreshing = false; }
  }
  recheck.addEventListener('click', startReceiptCheck);
  window.addEventListener('online', async () => { await Promise.all([refreshDevice(), refreshUnread(), lastDelivery ? startReceiptCheck() : Promise.resolve()]); });
  window.addEventListener('offline', () => { controls(Boolean(deviceId)); root.hidden = false; message('Du er frakoblet. Koble til før du endrer varsler.'); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'hidden') { refreshDevice(); refreshUnread(); if(lastDelivery) startReceiptCheck(); }
    else { clearTimeout(summaryTimer); unreadGeneration++; clearTimeout(receiptTimer); receiptGeneration++; }
  });
  window.addEventListener('pageshow', () => { refreshDevice(); refreshUnread(); });
  refreshDevice(); refreshUnread();
})();

function equalPushKeys(first, second) {
  const bytes = new Uint8Array(first);
  return bytes.length === second.length && bytes.every((value, index) => value === second[index]);
}
