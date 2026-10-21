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
})();
