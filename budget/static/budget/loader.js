(() => {
  'use strict';
  const loader = document.getElementById('app-loader');
  if (!loader) return;
  let timer = null;
  const active = new Set();
  function hide() { active.clear(); clearTimeout(timer); loader.hidden = true; }
  function start(mode = 'content') {
    const token = {};
    active.add(token); loader.dataset.mode = mode; loader.hidden = false;
    clearTimeout(timer);
    // Recovery deadline only: successful work hides immediately, with no minimum wait.
    timer = setTimeout(hide, 3000);
    return token;
  }
  function stop(token) { active.delete(token); if (!active.size) hide(); }
  window.FamilieblikkLoader = {start, stop};
  if (document.readyState === 'loading') start('boot');
  document.addEventListener('DOMContentLoaded', hide, {once:true});
  for (const name of ['pageshow','popstate','error','unhandledrejection','offline','focus']) window.addEventListener(name, hide);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') hide(); });
  function navigation(event, node) {
    const dirty = Boolean(document.querySelector('[data-dirty="true"]'));
    // Wait for existing form/dirty-state handlers to cancel the default action.
    queueMicrotask(() => {
      if (event.defaultPrevented || dirty || !navigator.onLine) return;
      if (event.type === 'submit') {
        if (node.matches('[data-calendar-form], [data-spending-form], #category-filters, #push-controls')) return;
        if (node.target && node.target !== '_self') return;
        if (node.checkValidity && !node.checkValidity()) return;
      }
      start('content');
    });
  }
  document.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || (target.pathname === location.pathname && target.search === location.search)) return;
    navigation(event, link);
  }, true);
  document.addEventListener('submit', event => navigation(event, event.target), true);
})();
