/* Diagrams: rendered from the vendored bundle, no CDN, re-drawn on theme change. */
(function () {
  'use strict';
  var blocks = Array.prototype.slice.call(document.querySelectorAll('.mermaid'));
  if (!blocks.length || typeof mermaid === 'undefined') return;

  blocks.forEach(function (el) { el.dataset.src = el.textContent; });

  function draw() {
    var dark = document.documentElement.dataset.theme === 'dark';
    mermaid.initialize({
      startOnLoad: false,
      theme: dark ? 'dark' : 'neutral',
      fontFamily: getComputedStyle(document.body).fontFamily,
      securityLevel: 'loose',
      flowchart: { curve: 'basis', padding: 14 },
      sequence: { useMaxWidth: true },
    });
    blocks.forEach(function (el) {
      el.removeAttribute('data-processed');
      el.textContent = el.dataset.src;
    });
    mermaid.run({ nodes: blocks }).catch(function (e) { console.warn('mermaid', e); });
  }

  draw();
  document.addEventListener('sdip:theme', draw);
})();
