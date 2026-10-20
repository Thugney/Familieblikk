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
  const categorySearchEnhanced = enhanceCategoryFilters();
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('input', () => { if (form.hasAttribute('data-dirty-warning')) form.dataset.dirty = 'true'; });
    form.addEventListener('submit', e => {
      if (form.hasAttribute('data-calendar-form') || form.hasAttribute('data-spending-form')) return;
      if (categorySearchEnhanced && form.id === 'category-filters') return;
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

// Progressiv forbedring: vanlig GET-skjema virker også uten JavaScript.
function enhanceCategoryFilters() {
  const form = document.getElementById('category-filters');
  const results = document.getElementById('category-results');
  const status = document.getElementById('category-search-status');
  if (!form || !results || !status || !window.fetch || !window.AbortController) return false;
  let timer, controller, sequence = 0;
  const load = async () => {
    clearTimeout(timer);
    const current = ++sequence;
    if (controller) controller.abort();
    controller = new AbortController();
    const url = new URL(window.location.href);
    for (const key of ['category_q', 'category_status', 'month', 'category_all']) {
      const value = form.elements.namedItem(key).value.trim();
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    results.setAttribute('aria-busy', 'true');
    status.textContent = 'Oppdaterer kategorier…';
    try {
      const response = await fetch(url.href, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!response.ok || response.redirected) throw new Error('Unavailable categories');
      const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
      const incoming = parsed.getElementById('category-results');
      if (!incoming) throw new Error('Missing category results');
      if (current !== sequence) return;
      results.replaceChildren(...incoming.childNodes);
      window.history.replaceState(null, '', url.href);
      status.textContent = 'Kategoriene er oppdatert.';
    } catch (error) {
      if (current !== sequence) return;
      status.textContent = 'Kunne ikke oppdatere kategoriene. Tidligere resultat vises. Prøv Finn på nytt.';
    } finally {
      if (current === sequence) results.setAttribute('aria-busy', 'false');
    }
  };
  const schedule = () => {
    // Invalider straks, også mens neste søk venter på debounce.
    ++sequence;
    if (controller) controller.abort();
    clearTimeout(timer);
    timer = setTimeout(load, 300);
  };
  form.elements.namedItem('category_q').addEventListener('input', schedule);
  form.elements.namedItem('category_q').addEventListener('search', schedule);
  form.elements.namedItem('category_status').addEventListener('change', load);
  form.addEventListener('submit', event => { event.preventDefault(); load(); });
  return true;
}
