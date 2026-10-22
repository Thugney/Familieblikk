(() => {
  const root = document.querySelector('[data-shopping-revision]');
  if (!root) return;
  let dirty = root.dataset.preservedDraft === 'true' || Boolean(document.querySelector('.errorlist'));
  document.addEventListener('input', () => { dirty = true; });
  document.addEventListener('change', () => { dirty = true; });
  async function refresh() {
    if (!navigator.onLine || document.hidden) return;
    try {
      const result = await fetch(root.dataset.revisionUrl, {cache: 'no-store', credentials: 'same-origin'});
      if (!result.ok || result.redirected) return;
      const data = await result.json();
      if (String(data.version) !== root.dataset.shoppingRevision) {
        if (dirty) document.getElementById('shopping-updates').hidden = false;
        else location.reload();
      }
    } catch (_) { /* Offline banner already explains connectivity. */ }
  }
  setInterval(refresh, 5000);
})();
