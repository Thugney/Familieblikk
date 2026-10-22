/* Photo preview lives only in page memory. No storage, cache or automatic upload. */
(() => {
  function install(document, URL, window) {
    const form = document.getElementById('camera-scan-form');
    if (!form) return;
    const input = form.querySelector('input[type=file]');
    const preview = document.getElementById('camera-preview');
    const status = document.getElementById('camera-status');
    const retake = document.getElementById('camera-retake');
    const clear = document.getElementById('camera-clear');
    const picker = document.getElementById('camera-picker');
    picker.hidden = false;
    picker.addEventListener('click', () => { input.removeAttribute('capture'); input.click(); });
    let current = null;
    function release() {
      if (current) URL.revokeObjectURL(current);
      current = null;
      preview.removeAttribute('src');
      preview.hidden = true;
      retake.hidden = clear.hidden = true;
    }
    input.addEventListener('change', () => {
      release();
      const file = input.files[0];
      if (!file) return;
      if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 10 * 1024 * 1024) {
        input.value = '';
        status.textContent = 'Velg JPEG eller PNG på høyst 10 MiB. Du kan også fylle inn manuelt.';
        return;
      }
      current = URL.createObjectURL(file);
      preview.src = current;
      preview.hidden = retake.hidden = clear.hidden = false;
      status.textContent = 'Kontroller at teksten er lesbar før du velger Skann bildet. Bildet er ikke sendt ennå.';
    });
    retake.addEventListener('click', () => { release(); input.value = ''; input.setAttribute('capture', 'environment'); input.click(); });
    clear.addEventListener('click', () => { release(); input.value = ''; status.textContent = 'Bildet er forkastet fra denne siden.'; input.focus(); });
    form.addEventListener('submit', event => {
      if (window.navigator.onLine === false) {
        event.preventDefault();
        status.textContent = 'Du er frakoblet. Koble til internett før du skanner eller lagrer.';
      } else if (event.submitter && event.submitter.value === 'manual') {
        release(); input.value = '';
      } else {
        status.textContent = 'Sender bildet til familiens server. Ingen økonomipost opprettes.';
      }
    });
    window.addEventListener('pagehide', () => { release(); input.value = ''; });
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {install};
  if (typeof document !== 'undefined') install(document, URL, window);
})();
