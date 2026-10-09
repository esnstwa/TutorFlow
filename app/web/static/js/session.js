(() => {
  'use strict';
  if (window.tutorflowSessionInstalled) return;
  window.tutorflowSessionInstalled = true;
  const nativeFetch = window.fetch.bind(window);
  const safeMethods = new Set(['GET', 'HEAD', 'OPTIONS']);
  window.fetch = (input, options = {}) => {
    const request = typeof Request !== 'undefined' && input instanceof Request ? input : null;
    const url = new URL(request ? request.url : String(input), window.location.href);
    const method = String(options.method || request?.method || 'GET').toUpperCase();
    if (url.origin !== window.location.origin || safeMethods.has(method)) {
      return nativeFetch(input, options);
    }
    const headers = new Headers(options.headers || request?.headers);
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
    if (csrf) headers.set('X-CSRF-Token', csrf);
    return nativeFetch(input, {...options, headers});
  };
})();
