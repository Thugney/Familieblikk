(() => {
  'use strict';
  const root = document.querySelector('[data-push-config]');
  if (!root) return;
  const status = document.getElementById('push-status');
  const enable = document.getElementById('push-enable');
  const disable = document.getElementById('push-disable');
  const test = document.getElementById('push-test');
  const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  let subscription = null, deviceId = null, registration = null, busy = false;
  const supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const installed = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  function message(text) { status.textContent = text; }
  function controls(active) {
    enable.hidden = active; disable.hidden = !subscription; test.hidden = !active;
    if (supported && Notification.permission === 'denied') enable.hidden = true;
    enable.disabled = busy || !navigator.onLine; disable.disabled = busy || !navigator.onLine; test.disabled = busy || !navigator.onLine || !deviceId;
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
  async function post(data) {
    if (!navigator.onLine) throw new Error('Du er frakoblet. Koble til før du endrer varsler.');
    return requestJson(root.dataset.pushDevice, {method:'POST', credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf}, body:JSON.stringify(data)});
  }
  async function refresh() {
    if (!supported) { controls(false); enable.hidden = true; message(ios && !installed ? 'På iPhone må du først legge Familieblikk til på Hjem-skjerm og åpne appen derfra.' : 'Denne nettleseren støtter ikke enhetsvarsler her. Bruk kalenderoversikten nedenfor. Varsler krever HTTPS eller localhost.'); return; }
    if (ios && !installed) { controls(false); enable.hidden = true; message('Legg først Familieblikk til på Hjem-skjerm via Del-menyen. Åpne appen derfra for å aktivere varsler.'); return; }
    if (!navigator.onLine) { controls(Boolean(deviceId)); message('Du er frakoblet. Status kontrolleres når du er på nett igjen.'); return; }
    if (Notification.permission === 'denied') { controls(false); enable.hidden = true; message('Varsler er avslått i nettleseren. Endre tillatelsen i nettleserens innstillinger hvis du vil aktivere dem.'); return; }
    deviceId = null; controls(false);
    try {
      registration = await bounded(navigator.serviceWorker.register('/sw.js', {scope:'/'}));
      subscription = await bounded(registration.pushManager.getSubscription());
      controls(false);
      if (!subscription) { deviceId = null; controls(false); message('Varsler er ikke aktivert på denne enheten.'); return; }
      await bounded(navigator.serviceWorker.ready);
      const result = await post({action:'status', endpoint:subscription.endpoint});
      deviceId = result.active ? result.id : null;
      controls(Boolean(deviceId));
      const labels = {active:'Aktivert på denne enheten.', retrying:'Aktivert. Levering er forsinket og prøves igjen.', failed:'Levering feilet. Deaktiver og aktiver igjen, eller prøv et testvarsel.', expired:'Økten eller abonnementet er utgått. Aktiver varsler på nytt.', disabled:'Varsler er ikke aktivert for denne innloggingen.'};
      message(labels[result.state] || labels.disabled);
    } catch (error) { deviceId = null; controls(false); message((error.message || 'Kunne ikke kontrollere varsler.') + ' Status er ukjent; prøv igjen eller deaktiver denne enheten.'); }
  }
  enable.addEventListener('click', async () => {
    if (busy || !navigator.onLine) return;
    // Request permission directly in the user gesture, before asynchronous I/O.
    busy = true; controls(false); message('Aktiverer varsler …');
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
      deviceId = result.id; message('Aktivert på denne enheten. Send gjerne et testvarsel til deg selv.');
    } catch (error) { deviceId = null; message(error.message || 'Kunne ikke aktivere varsler. Prøv igjen.'); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  disable.addEventListener('click', async () => {
    if (busy) return;
    busy = true; controls(true);
    try {
      await post({action:'disable', endpoint:subscription.endpoint});
      deviceId = null;
      try { await bounded(subscription.unsubscribe()); } catch { /* Server has stopped delivery. */ }
      subscription = null; message('Deaktivert på denne enheten. Kalenderoversikten beholdes.');
    } catch (error) { message(error.message); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  test.addEventListener('click', async () => {
    if (busy || !deviceId) return;
    busy = true; controls(true);
    try { await post({action:'test', id:deviceId}); message('Testvarselet ligger i leveringskøen. Nettleseren og operativsystemet styrer når det vises.'); }
    catch (error) { message(error.message); }
    finally { busy = false; controls(Boolean(deviceId)); }
  });
  window.addEventListener('online', refresh);
  window.addEventListener('offline', () => { controls(Boolean(deviceId)); message('Du er frakoblet. Koble til før du endrer varsler.'); });
  refresh();
})();

function equalPushKeys(first, second) {
  const bytes = new Uint8Array(first);
  return bytes.length === second.length && bytes.every((value, index) => value === second[index]);
}
