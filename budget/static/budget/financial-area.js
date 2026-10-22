// Area is URL-bound, so separate tabs keep separate budgets.
(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    const area = new URL(location.href).searchParams.get('area');
    if (!area) return originalFetch(input, options);
    const raw = input instanceof Request ? input.url : input;
    const url = new URL(raw, location.href);
    if (url.origin === location.origin && /^(\/app\/(forbruk|plan)\/|\/dokument\/|\/handleliste\/|\/handletur\/)/.test(url.pathname) && !url.searchParams.has('area')) {
      url.searchParams.set('area', area);
      input = input instanceof Request ? new Request(url, input) : url;
    }
    return originalFetch(input, options);
  };
})();
