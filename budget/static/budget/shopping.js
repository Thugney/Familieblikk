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
  // Instant tick: the same save command as the edit page (version and replay protection included), without a page reload.
  const forms = document.querySelectorAll ? Array.from(document.querySelectorAll('[data-tick-form]')) : [];
  const refreshVersions = async () => {
    try {
      const result = await fetch(root.dataset.revisionUrl, {cache: 'no-store', credentials: 'same-origin'});
      if (!result.ok) return false;
      const data = await result.json();
      root.dataset.shoppingRevision = String(data.version);
      forms.forEach(form => { form.elements.version.value = String(data.version); });
      return true;
    } catch (_) { return false; }
  };
  const recount = () => {
    const total = forms.length;
    const done = forms.filter(form => form.querySelector('.shopping-check-badge.checked')).length;
    const label = document.querySelector('[data-shopping-count]');
    const bar = document.querySelector('[data-shopping-progress]');
    if (label) label.textContent = done + ' av ' + total + ' kjøpt';
    if (bar) bar.style.width = (total ? Math.round(done * 100 / total) : 0) + '%';
  };
  forms.forEach(form => form.addEventListener('submit', async event => {
    if (!window.fetch || form.dataset.busy) return;
    event.preventDefault();
    form.dataset.busy = '1';
    const button = form.querySelector('button');
    const row = form.closest('.shopping-item-row');
    try {
      form.elements.key.value = crypto.randomUUID ? crypto.randomUUID() : form.elements.key.value;
      const result = await fetch(form.action, {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
      const ok = result.redirected && /\/handleliste\/[0-9a-f-]{36}\/$/.test(new URL(result.url).pathname);
      if (!ok) { delete form.dataset.busy; form.submit(); return; }
      const nowChecked = !button.classList.contains('checked');
      button.classList.toggle('checked', nowChecked);
      button.setAttribute('aria-pressed', nowChecked ? 'true' : 'false');
      button.textContent = nowChecked ? '✓' : '';
      row.classList.toggle('is-purchased', nowChecked);
      const status = row.querySelector('.ui-status');
      if (status) { status.textContent = nowChecked ? 'Kjøpt' : 'Gjenstår'; status.classList.toggle('actual', nowChecked); status.classList.toggle('neutral', !nowChecked); }
      const purchased = form.querySelector('input[name="purchased"]');
      if (nowChecked && purchased) purchased.remove();
      if (!nowChecked && !purchased) { const flag = document.createElement('input'); flag.type = 'hidden'; flag.name = 'purchased'; flag.value = 'on'; form.appendChild(flag); }
      recount();
      await refreshVersions();
    } catch (_) {
      delete form.dataset.busy; form.submit(); return;
    }
    delete form.dataset.busy;
  }));
})();
