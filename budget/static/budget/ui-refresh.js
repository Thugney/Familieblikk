/* Progressive disclosure only; native details and form submission work without JS. */
(() => {
  document.querySelectorAll('form[data-dirty-warning]').forEach(form => {
    const kind = form.querySelector('[name="kind"]');
    const advanced = form.querySelector('.entry-form-advanced');
    if (!kind || !advanced) return;
    const reveal = () => {
      if (kind.value === 'refund' || kind.value === 'remittance') advanced.open = true;
    };
    kind.addEventListener('change', reveal);
    reveal();
  });

  document.querySelectorAll('[data-hero-distribution]').forEach(section => {
    const buttons = section.querySelectorAll('[data-hero-mode]');
    const panels = section.querySelectorAll('[data-hero-panel]');
    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-hero-mode');
        buttons.forEach(b => {
          const active = b === btn;
          b.classList.toggle('is-active', active);
          b.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        panels.forEach(panel => {
          panel.hidden = panel.getAttribute('data-hero-panel') !== target;
        });
      });
    });
  });

  document.querySelectorAll('[data-entry-create-surface]').forEach(surface => {
    const tabs = surface.querySelectorAll('[data-capture-mode]');
    const panels = surface.querySelectorAll('[data-capture-panel]');
    const activateMode = mode => {
      tabs.forEach(t => {
        const active = t.getAttribute('data-capture-mode') === mode;
        t.classList.toggle('is-active', active);
        t.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      panels.forEach(panel => {
        panel.hidden = panel.getAttribute('data-capture-panel') !== mode;
      });
    };
    tabs.forEach(tab => {
      tab.addEventListener('click', () => activateMode(tab.getAttribute('data-capture-mode')));
    });
    if (typeof URLSearchParams !== 'undefined' && new URLSearchParams(window.location.search).get('mode') === 'camera') {
      activateMode('camera');
    }
  });

  document.querySelectorAll('[data-mobile-quick-actions]').forEach(container => {
    const fab = container.querySelector('[data-mobile-fab]');
    const sheet = container.querySelector('[data-mobile-sheet]');
    if (!fab || !sheet) return;
    const setOpen = open => {
      sheet.hidden = !open;
      fab.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    fab.addEventListener('click', e => {
      e.stopPropagation();
      setOpen(sheet.hidden);
    });
    document.addEventListener('click', e => {
      if (!sheet.hidden && !container.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !sheet.hidden) setOpen(false);
    });
  });
})();
