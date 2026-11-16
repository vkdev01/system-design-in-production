/* Diagrams render at their natural size (no shrink-to-fit) and can be zoomed.
   Mermaid is vendored, so nothing here touches the network. */
(function () {
  'use strict';
  var blocks = Array.prototype.slice.call(document.querySelectorAll('.mermaid'));
  if (!blocks.length || typeof mermaid === 'undefined') return;

  blocks.forEach(function (el) { el.dataset.src = el.textContent; });

  function draw() {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'neutral',
      fontFamily: getComputedStyle(document.body).fontFamily,
      fontSize: 15,
      securityLevel: 'loose',
      // keep the intrinsic size: a diagram squeezed into a 800px column is
      // unreadable, and the container can scroll instead
      flowchart: { useMaxWidth: false, curve: 'basis', padding: 16, nodeSpacing: 40, rankSpacing: 46 },
      sequence: { useMaxWidth: false, actorMargin: 60, boxMargin: 12, messageFontSize: 14 },
      state: { useMaxWidth: false },
      er: { useMaxWidth: false },
    });
    blocks.forEach(function (el) {
      el.removeAttribute('data-processed');
      el.textContent = el.dataset.src;
    });
    return mermaid.run({ nodes: blocks }).catch(function (e) { console.warn('mermaid', e); });
  }

  draw().then(function () {
    document.dispatchEvent(new CustomEvent('sdip:diagrams'));
  });

  document.addEventListener('sdip:theme', function () {
    draw().then(function () {
      document.dispatchEvent(new CustomEvent('sdip:diagrams'));
    });
  });
})();
