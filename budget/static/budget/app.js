/* Nett er påkrevd. Ingen privat lagring, lokal kø eller automatisk gjensending. */
(() => {
  const banner = document.getElementById('offline-banner');
  const state = () => {
    const offline = !navigator.onLine;
    banner.hidden = !offline;
    document.body.classList.toggle('offline', offline);
    document.querySelectorAll('form button').forEach(b => b.disabled = offline);
  };
  window.addEventListener('offline', state);
  window.addEventListener('online', () => { state(); if (!document.querySelector('[data-dirty="true"]')) location.reload(); });
  window.addEventListener('pageshow', e => { if (e.persisted) location.reload(); });
  state();
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('input', () => { if (form.hasAttribute('data-dirty-warning')) form.dataset.dirty = 'true'; });
    form.addEventListener('submit', e => {
      if (!navigator.onLine) { e.preventDefault(); state(); return; }
      if (form.dataset.submitting) { e.preventDefault(); return; }
      form.dataset.submitting = 'true';
      delete form.dataset.dirty;
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (button) { button.disabled = true; button.textContent = 'Lagrer…'; }
    });
  });
  window.addEventListener('beforeunload', e => { if (document.querySelector('[data-dirty="true"]')) { e.preventDefault(); e.returnValue = ''; } });
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', {updateViaCache: 'none'}).catch(() => {});
})();
