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

  const keyboardChoice = (controls, activate) => {
    controls.forEach((control, index) => control.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % controls.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + controls.length - 1) % controls.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = controls.length - 1;
      else return;
      event.preventDefault();
      activate(controls[next]);
      controls[next].focus();
    }));
  };
  document.querySelectorAll('[data-calendar-quick-create]').forEach(button => {
    const create = document.getElementById('calendar-create');
    if (!create) return;
    button.hidden = false;
    button.addEventListener('click', () => create.click());
  });

  document.querySelectorAll('[data-hero-distribution]').forEach(section => {
    const buttons = section.querySelectorAll('[data-hero-mode]');
    const panels = section.querySelectorAll('[data-hero-panel]');
    keyboardChoice(buttons, button => button.click());
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

  document.querySelectorAll('[data-entry-create-surface]').forEach((surface, surfaceIndex) => {
    const tabs = surface.querySelectorAll('[data-capture-mode]');
    const panels = surface.querySelectorAll('[data-capture-panel]');
    tabs.forEach((tab, index) => {
      const mode = tab.getAttribute('data-capture-mode');
      const panel = Array.from(panels).find(item => item.getAttribute('data-capture-panel') === mode);
      if (!panel) return;
      tab.id = tab.id || `capture-tab-${surfaceIndex}-${index}`;
      panel.id = panel.id || `capture-panel-${surfaceIndex}-${index}`;
      tab.setAttribute('aria-controls', panel.id);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', tab.id);
    });
    const activateMode = mode => {
      tabs.forEach(t => {
        const active = t.getAttribute('data-capture-mode') === mode;
        t.classList.toggle('is-active', active);
        t.setAttribute('aria-selected', active ? 'true' : 'false');
        t.tabIndex = active ? 0 : -1;
      });
      panels.forEach(panel => {
        panel.hidden = panel.getAttribute('data-capture-panel') !== mode;
      });
    };
    keyboardChoice(tabs, tab => activateMode(tab.getAttribute('data-capture-mode')));
    activateMode('manual');
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
    const setOpen = (open, restoreFocus = false) => {
      sheet.hidden = !open;
      fab.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) sheet.querySelector('a, button')?.focus();
      else if (restoreFocus) fab.focus();
    };
    fab.addEventListener('click', e => {
      e.stopPropagation();
      setOpen(sheet.hidden);
    });
    document.addEventListener('click', e => {
      if (!sheet.hidden && !container.contains(e.target)) setOpen(false);
    });
    container.addEventListener('focusout', e => {
      if (!sheet.hidden && !container.contains(e.relatedTarget)) setOpen(false);
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !sheet.hidden) { e.preventDefault(); setOpen(false, true); }
    });
  });
  // Month stepper: previous/next arrows and auto-submit around the native month input.
  document.querySelectorAll('.header-month-form').forEach(form => {
    const input = form.querySelector('input[type="month"]');
    if (!input || !document.createElement) return;
    const shift = delta => {
      const match = /^(\d{4})-(\d{2})$/.exec(input.value);
      if (!match) return;
      const date = new Date(Date.UTC(+match[1], +match[2] - 1 + delta, 1));
      input.value = date.getUTCFullYear() + '-' + String(date.getUTCMonth() + 1).padStart(2, '0');
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    };
    const arrow = (label, delta, path) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'month-step';
      button.setAttribute('aria-label', label);
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + path + '"/></svg>';
      button.addEventListener('click', () => shift(delta));
      return button;
    };
    form.insertBefore(arrow('Forrige måned', -1, 'm15 6-6 6 6 6'), form.firstChild);
    input.after(arrow('Neste måned', 1, 'm9 6 6 6-6 6'));
    const apply = form.querySelector('button:not(.month-step)');
    if (apply) apply.hidden = true;
    input.addEventListener('change', () => { if (input.value) { if (form.requestSubmit) form.requestSubmit(); else form.submit(); } });
  });
  // Ctrl/Cmd-K: jump to any page or action. Entries come from the real navigation, so permissions are respected.
  if (document.addEventListener && document.createElement && document.body) {
    let overlay = null;
    const close = () => { if (overlay) { overlay.remove(); overlay = null; } };
    const open = () => {
      if (overlay) return;
      const seen = new Set();
      const entries = [];
      document.querySelectorAll('.pc-nav-btn, .header-quick-add, #notification-bell').forEach(link => {
        const label = (link.getAttribute('aria-label') || link.textContent || '').replace(/\s+/g, ' ').trim();
        const href = link.getAttribute('href');
        if (!label || !href || seen.has(href + label)) return;
        seen.add(href + label);
        entries.push({label, href});
      });
      overlay = document.createElement('div');
      overlay.className = 'cmdk';
      overlay.innerHTML = '<div class="cmdk-box" role="dialog" aria-modal="true" aria-label="Gå til side eller handling"><input type="search" placeholder="Gå til side eller handling…" aria-label="Søk"><ul></ul></div>';
      document.body.appendChild(overlay);
      const input = overlay.querySelector('input');
      const list = overlay.querySelector('ul');
      const render = () => {
        const q = input.value.trim().toLowerCase();
        list.innerHTML = '';
        entries.filter(e => !q || e.label.toLowerCase().includes(q)).forEach(entry => {
          const item = document.createElement('li');
          const anchor = document.createElement('a');
          anchor.href = entry.href;
          anchor.textContent = entry.label;
          item.appendChild(anchor);
          list.appendChild(item);
        });
      };
      input.addEventListener('input', render);
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { const first = list.querySelector('a'); if (first) window.location.href = first.href; }
      });
      overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
      render();
      input.focus();
    };
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === 'k') { event.preventDefault(); overlay ? close() : open(); }
      else if (event.key === 'Escape' && overlay) { event.preventDefault(); close(); }
    });
  }
  // Calm entrance: count-up for the hero figure, bar growth and the pace line drawing in.
  const calmMotion = typeof window !== 'undefined' && window.matchMedia && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (calmMotion && typeof requestAnimationFrame === 'function') {
    document.querySelectorAll('.hero-big-amount').forEach(node => {
      const text = (node.textContent || '').trim();
      const match = /^(-?)([\d\s\u00a0]+),(\d{2})\s*kr$/.exec(text);
      if (!match) return;
      const target = Number(match[2].replace(/[\s\u00a0]/g, '') + '.' + match[3]) * (match[1] ? -1 : 1);
      const fmt = new Intl.NumberFormat('nb-NO', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      const unit = node.querySelector('.kr');
      let start = null;
      const tick = now => {
        start = start === null ? now : start;
        const t = Math.min((now - start) / 900, 1), eased = 1 - Math.pow(1 - t, 3);
        const shown = fmt.format(target * eased).replace('-', match[1] || '-').replace(/\u202f/g, '\u00a0');
        if (!unit) node.textContent = shown + ' kr';
        if (t < 1) requestAnimationFrame(tick); else node.textContent = text;
      };
      if (!unit) requestAnimationFrame(tick);
    });
    document.querySelectorAll('.sheet .bar i').forEach(bar => {
      const width = bar.style.width;
      if (!width) return;
      bar.style.width = '0';
      requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.transition = 'width .9s cubic-bezier(.2,.7,.2,1)'; bar.style.width = width; }));
    });
    document.querySelectorAll('.hero-chart-box polyline').forEach((line, index) => {
      if (index === 0 && line.getAttribute('stroke-dasharray')) return;
      line.setAttribute('pathLength', '1');
      line.style.strokeDasharray = '1';
      line.style.strokeDashoffset = '1';
      requestAnimationFrame(() => requestAnimationFrame(() => { line.style.transition = 'stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)'; line.style.strokeDashoffset = '0'; }));
    });
  }
})();
