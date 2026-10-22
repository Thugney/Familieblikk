/* OCR stays a proposal until the user explicitly copies, reviews and saves it. */
(() => {
  function suggestionsForDraft(source) {
    const result = {};
    if (!source || typeof source !== 'object' || Array.isArray(source)) return result;
    for (const name of ['supplier', 'invoice_number']) {
      const value = typeof source[name] === 'string' ? source[name].trim() : '';
      if (value && value.length <= (name === 'supplier' ? 120 : 100) && !/[\x00-\x1f\x7f]/.test(value)) result[name] = value;
    }
    if (typeof source.kid === 'string') {
      const value = source.kid.replace(/\s/g, '');
      if (/^\d{1,30}$/.test(value)) result.kid = value;
    }
    if (typeof source.amount === 'string') {
      const value = source.amount.replace(/[ \u00a0]/g, '').replace(',', '.');
      if (/^\d{1,12}\.\d{2}$/.test(value) && Number(value) > 0) result.amount = value;
    }
    for (const name of ['document_date', 'due_date']) {
      const value = source[name];
      if (typeof value !== 'string') continue;
      const parts = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value.trim());
      if (!parts) continue;
      const [, day, month, year] = parts;
      const iso = `${year}-${month}-${day}`;
      const date = new Date(`${iso}T00:00:00Z`);
      if (Number(year) > 0 && !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === iso) result[name] = iso;
    }
    return result;
  }

  function install(document) {
    const form = document.getElementById('document-draft-form');
    const button = document.getElementById('use-document-suggestions');
    const data = document.getElementById('document-suggestions');
    const status = document.getElementById('document-suggestions-status');
    if (!form || !button || !data || !status) return;
    let suggestions;
    try { suggestions = suggestionsForDraft(JSON.parse(data.textContent)); }
    catch (_) { return; }
    const touched = new Set();
    form.addEventListener('input', event => touched.add(event.target.name));
    form.addEventListener('change', event => touched.add(event.target.name));
    button.addEventListener('click', () => {
      let filled = 0;
      for (const [name, value] of Object.entries(suggestions)) {
        const field = form.elements.namedItem(name);
        // Even an intentionally cleared saved/typed field belongs to the user.
        if (!field || field.disabled || field.readOnly || field.value !== '' || field.defaultValue !== '' || touched.has(name)) continue;
        field.value = value;
        field.dispatchEvent(new Event('input', {bubbles: true}));
        filled += 1;
      }
      status.textContent = filled
        ? `${filled} tomme felt er fylt med forslag. Kontroller kvitteringen eller fakturaen, fyll ut resten og lagre utkastet. Ingenting er lagret eller bokført.`
        : 'Ingen urørte, tomme felt kunne fylles. Dine verdier er beholdt. Fyll ut manglende felt manuelt.';
      if (!suggestions.supplier) status.textContent += ' Leverandør / butikk må fylles ut manuelt.';
    });
    button.hidden = false;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {suggestionsForDraft, install};
  if (typeof document !== 'undefined') install(document);
})();
