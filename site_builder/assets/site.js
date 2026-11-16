/* System Design in Production — page behaviour.
   No framework: theme, drawer, search, copy buttons, progress, TOC tracking. */
(function () {
  'use strict';

  var base = (document.currentScript && document.currentScript.dataset.base) || '';
  var root = document.documentElement;

  /* ---------- theme ---------- */
  function setTheme(t) {
    root.dataset.theme = t;
    try { localStorage.setItem('sdip-theme', t); } catch (e) {}
    document.dispatchEvent(new CustomEvent('sdip:theme', { detail: t }));
  }
  var themeBtn = document.getElementById('theme');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
  }

  /* ---------- mobile drawer ---------- */
  var menu = document.getElementById('menu');
  var drawer = document.getElementById('drawer');
  if (menu && drawer) {
    menu.addEventListener('click', function () {
      var open = drawer.hasAttribute('hidden');
      if (open) drawer.removeAttribute('hidden'); else drawer.setAttribute('hidden', '');
      menu.setAttribute('aria-expanded', String(open));
    });
  }

  /* ---------- reading progress ---------- */
  var bar = document.getElementById('progress');
  if (bar) {
    var onScroll = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = max > 0 ? (h.scrollTop / max) * 100 + '%' : '0%';
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- copy buttons ---------- */
  document.querySelectorAll('.prose .highlight, .prose pre').forEach(function (block) {
    if (block.querySelector('.copybtn')) return;
    var btn = document.createElement('button');
    btn.className = 'copybtn';
    btn.type = 'button';
    btn.textContent = 'copy';
    btn.addEventListener('click', function () {
      var code = block.querySelector('code');
      var text = code ? code.innerText : block.innerText;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = 'copied';
        setTimeout(function () { btn.textContent = 'copy'; }, 1400);
      });
    });
    block.appendChild(btn);
  });

  /* ---------- contents rail ---------- */
  // On narrow screens the contents list would push the article off-screen, so
  // it starts collapsed and expands on demand.
  if (window.matchMedia('(max-width: 1080px)').matches) {
    document.querySelectorAll('.rail__box').forEach(function (d) { d.open = false; });
  }

  /* ---------- contents rail: highlight the section you are in ---------- */
  var railLinks = Array.prototype.slice.call(document.querySelectorAll('.rail__link'));
  if (railLinks.length && 'IntersectionObserver' in window) {
    var byId = {};
    railLinks.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var targets = Object.keys(byId)
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);

    var visible = new Set();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) visible.add(e.target.id); else visible.delete(e.target.id);
      });
      var firstVisible = targets.filter(function (t) { return visible.has(t.id); })[0];
      railLinks.forEach(function (a) { a.classList.remove('is-active'); });
      if (firstVisible) {
        var link = byId[firstVisible.id];
        if (link) link.classList.add('is-active');
      }
    }, { rootMargin: '-72px 0px -70% 0px', threshold: 0 });

    targets.forEach(function (t) { io.observe(t); });
  }

  /* ---------- search ---------- */
  var overlay = document.getElementById('search');
  var input = document.getElementById('search-input');
  var results = document.getElementById('search-results');
  var index = null;
  var sel = -1;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch(base + '/search-index.json')
      .then(function (r) { return r.json(); })
      .then(function (data) { index = data; return index; });
  }

  function openSearch() {
    if (!overlay) return;
    overlay.removeAttribute('hidden');
    loadIndex();
    if (input) { input.value = ''; input.focus(); }
    render('');
  }

  function closeSearch() {
    if (!overlay) return;
    overlay.setAttribute('hidden', '');
  }

  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function snippet(text, q) {
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return esc(text.slice(0, 130)) + '…';
    var start = Math.max(0, i - 50);
    var out = (start > 0 ? '…' : '') + esc(text.slice(start, start + 170)) + '…';
    return out.replace(new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'i'), '<mark>$1</mark>');
  }

  function render(q) {
    if (!results) return;
    sel = -1;
    if (!index) { results.innerHTML = '<p class="search__empty">Loading…</p>'; return; }
    q = q.trim().toLowerCase();

    var hits = index.map(function (p) {
      var score = 0;
      if (!q) score = 1;
      else {
        if (p.t.toLowerCase().indexOf(q) >= 0) score += 8;
        if ((p.k || '').toLowerCase() === q) score += 10;
        if (p.s.toLowerCase().indexOf(q) >= 0) score += 3;
        if ((p.h || []).some(function (h) { return h.toLowerCase().indexOf(q) >= 0; })) score += 4;
        if (p.b.toLowerCase().indexOf(q) >= 0) score += 2;
      }
      return { p: p, score: score };
    }).filter(function (x) { return x.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, 12);

    if (!hits.length) {
      results.innerHTML = '<p class="search__empty">No matches. Try “idempotency”, “hot partition”, “token bucket”, “H3”.</p>';
      return;
    }

    results.innerHTML = hits.map(function (h, i) {
      var p = h.p;
      var head = (p.h || []).filter(function (x) { return q && x.toLowerCase().indexOf(q) >= 0; })[0];
      return '<a class="result" data-i="' + i + '" href="' + base + p.u + (head ? '#' + slug(head) : '') + '">' +
        '<span class="result__sec">' + esc(p.s) + (p.k ? ' · ' + esc(p.k) : '') + '</span>' +
        '<span class="result__title">' + esc(p.t) + '</span>' +
        '<span class="result__snippet">' + (q ? snippet(p.b, q) : esc(p.b.slice(0, 130)) + '…') + '</span>' +
        '</a>';
    }).join('');
  }

  function slug(s) {
    return s.toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');
  }

  if (overlay) {
    document.getElementById('search-open').addEventListener('click', openSearch);
    overlay.addEventListener('click', function (e) {
      if (e.target.hasAttribute('data-close')) closeSearch();
    });
    input.addEventListener('input', function () { render(input.value); });

    document.addEventListener('keydown', function (e) {
      var open = !overlay.hasAttribute('hidden');
      if ((e.key === '/' || (e.key === 'k' && (e.metaKey || e.ctrlKey))) && !open) {
        var tag = (document.activeElement.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        e.preventDefault(); openSearch(); return;
      }
      if (!open) return;
      if (e.key === 'Escape') { closeSearch(); return; }
      var items = results.querySelectorAll('.result');
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!items.length) return;
        sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items.forEach(function (el, i) { el.classList.toggle('is-sel', i === sel); });
        items[sel].scrollIntoView({ block: 'nearest' });
      }
      if (e.key === 'Enter' && sel >= 0 && items[sel]) {
        window.location.href = items[sel].getAttribute('href');
      }
    });
  }
})();
