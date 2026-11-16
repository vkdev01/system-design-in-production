/* Behaviour for the reference-site layout: colour schemes, sidebar filter,
   contents tracking, code copy, mobile contents toggle, search. */
(function () {
  'use strict';

  var base = (document.currentScript && document.currentScript.dataset.base) || '';
  var root = document.documentElement;
  var KEY = 'tutorial-theme';

  /* ---------- colour schemes ---------- */
  var trigger = document.getElementById('theme-trigger');
  var pop = document.getElementById('theme-pop');

  function markActive(id) {
    document.querySelectorAll('.theme-item').forEach(function (b) {
      b.setAttribute('aria-checked', String(b.dataset.themeId === id));
    });
    var item = document.querySelector('.theme-item[data-theme-id="' + id + '"]');
    var dot = item && item.querySelector('.theme-dot');
    if (trigger && dot) trigger.style.setProperty('--dot', dot.style.background);
  }

  function setTheme(id) {
    root.dataset.theme = id;
    try { localStorage.setItem(KEY, id); } catch (e) {}
    markActive(id);
    document.dispatchEvent(new CustomEvent('sdip:theme', { detail: id }));
  }

  markActive(root.dataset.theme || 'atlas');

  if (trigger && pop) {
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = pop.hasAttribute('hidden');
      if (open) pop.removeAttribute('hidden'); else pop.setAttribute('hidden', '');
      trigger.setAttribute('aria-expanded', String(open));
    });
    pop.addEventListener('click', function (e) {
      var b = e.target.closest('.theme-item');
      if (!b) return;
      setTheme(b.dataset.themeId);
      pop.setAttribute('hidden', '');
      trigger.setAttribute('aria-expanded', 'false');
    });
    document.addEventListener('click', function (e) {
      if (!pop.hasAttribute('hidden') && !pop.contains(e.target) && e.target !== trigger) {
        pop.setAttribute('hidden', '');
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        pop.setAttribute('hidden', '');
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- mobile contents ---------- */
  var idx = document.getElementById('idx');
  ['idx-toggle', 'menu-btn'].forEach(function (id) {
    var btn = document.getElementById(id);
    if (btn && idx) btn.addEventListener('click', function () { idx.classList.toggle('open'); });
  });

  /* ---------- sidebar filter ---------- */
  var filter = document.getElementById('idx-search');
  if (filter && idx) {
    filter.addEventListener('input', function () {
      var q = filter.value.trim().toLowerCase();
      idx.querySelectorAll('.idx li[data-title], .idx li').forEach(function (li) {
        var title = li.getAttribute('data-title') || (li.textContent || '').toLowerCase();
        var hit = !q || title.indexOf(q) >= 0;
        li.style.display = hit ? '' : 'none';
      });
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

  /* ---------- code copy ---------- */
  document.querySelectorAll('.code').forEach(function (block) {
    var btn = block.querySelector('.code-copy');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var code = block.querySelector('pre code');
      var text = code ? code.innerText : block.innerText;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = 'Copied';
        setTimeout(function () { btn.textContent = 'Copy'; }, 1400);
      });
    });
  });

  /* ---------- contents tracking ---------- */
  var subs = Array.prototype.slice.call(document.querySelectorAll('.idx .sub a[data-h]'));
  if (subs.length && 'IntersectionObserver' in window) {
    var map = {};
    subs.forEach(function (a) { map[a.dataset.h] = a; });
    var heads = Object.keys(map).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var seen = new Set();
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) seen.add(e.target.id); else seen.delete(e.target.id);
      });
      var first = heads.filter(function (h) { return seen.has(h.id); })[0];
      subs.forEach(function (a) { a.classList.remove('on'); });
      if (first && map[first.id]) map[first.id].classList.add('on');
    }, { rootMargin: '-80px 0px -70% 0px', threshold: 0 });
    heads.forEach(function (h) { io.observe(h); });
  }


  /* ---------- diagram zoom ---------- */
  var zoomBox = document.getElementById('zoom');
  var stage = document.getElementById('zoom-stage');
  var inner = document.getElementById('zoom-inner');
  var pctEl = document.getElementById('zoom-pct');
  var titleEl = document.getElementById('zoom-title');
  var zscale = 1, tx = 0, ty = 0, natural = { w: 0, h: 0 };

  function applyZoom() {
    if (!inner) return;
    inner.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + zscale + ')';
    if (pctEl) pctEl.textContent = Math.round(zscale * 100) + '%';
  }

  function fitZoom() {
    if (!stage || !natural.w) return;
    var pad = 48;
    var s = Math.min((stage.clientWidth - pad) / natural.w, (stage.clientHeight - pad) / natural.h, 2.4);
    zscale = Math.max(0.3, s);
    tx = Math.max(24, (stage.clientWidth - natural.w * zscale) / 2);
    ty = 24;
    applyZoom();
  }

  function openZoom(svg, label) {
    if (!zoomBox || !inner || !svg) return;
    inner.innerHTML = '';
    var clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    clone.setAttribute('width', svg.viewBox && svg.viewBox.baseVal.width ? svg.viewBox.baseVal.width : svg.getBoundingClientRect().width);
    clone.setAttribute('height', svg.viewBox && svg.viewBox.baseVal.height ? svg.viewBox.baseVal.height : svg.getBoundingClientRect().height);
    inner.appendChild(clone);
    var box = clone.getBoundingClientRect();
    natural = { w: box.width || 800, h: box.height || 600 };
    if (titleEl) titleEl.textContent = label || 'Diagram';
    zoomBox.classList.add('open');
    zoomBox.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    fitZoom();
  }

  function closeZoom() {
    if (!zoomBox) return;
    zoomBox.classList.remove('open');
    zoomBox.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function addZoomTools() {
    document.querySelectorAll('.fig.mermaid-fig').forEach(function (fig) {
      if (fig.querySelector('.fig-tools')) return;
      var svg = fig.querySelector('svg');
      if (!svg) return;
      var cap = fig.querySelector('figcaption');
      var label = cap ? cap.textContent.replace(/\s+/g, ' ').trim() : 'Diagram';

      var tools = document.createElement('div');
      tools.className = 'fig-tools';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'fig-btn';
      btn.innerHTML = '⤢ Expand';
      btn.setAttribute('aria-label', 'Expand diagram');
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        openZoom(fig.querySelector('svg'), label);
      });
      tools.appendChild(btn);
      fig.appendChild(tools);

      var out = fig.querySelector('.mermaid-out');
      if (out) {
        out.addEventListener('click', function () {
          openZoom(fig.querySelector('svg'), label);
        });
      }
    });
  }

  if (zoomBox) {
    addZoomTools();
    document.addEventListener('sdip:diagrams', addZoomTools);

    zoomBox.addEventListener('click', function (e) {
      var b = e.target.closest('[data-zoom]');
      if (!b) {
        if (e.target === stage || e.target === zoomBox) closeZoom();
        return;
      }
      var act = b.dataset.zoom;
      if (act === 'close') return closeZoom();
      if (act === 'in') { zscale = Math.min(4, zscale * 1.25); applyZoom(); }
      if (act === 'out') { zscale = Math.max(0.2, zscale / 1.25); applyZoom(); }
      if (act === 'reset') fitZoom();
    });

    document.addEventListener('keydown', function (e) {
      if (!zoomBox.classList.contains('open')) return;
      if (e.key === 'Escape') closeZoom();
      if (e.key === '+' || e.key === '=') { zscale = Math.min(4, zscale * 1.25); applyZoom(); }
      if (e.key === '-') { zscale = Math.max(0.2, zscale / 1.25); applyZoom(); }
      if (e.key === '0') fitZoom();
    });

    stage.addEventListener('wheel', function (e) {
      e.preventDefault();
      var factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      var rect = stage.getBoundingClientRect();
      var mx = e.clientX - rect.left, my = e.clientY - rect.top;
      var next = Math.min(4, Math.max(0.2, zscale * factor));
      var k = next / zscale;
      tx = mx - (mx - tx) * k;
      ty = my - (my - ty) * k;
      zscale = next;
      applyZoom();
    }, { passive: false });

    var dragging = false, sx = 0, sy = 0, ox = 0, oy = 0;
    stage.addEventListener('mousedown', function (e) {
      dragging = true; sx = e.clientX; sy = e.clientY; ox = tx; oy = ty;
      stage.classList.add('grabbing');
    });
    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      tx = ox + (e.clientX - sx);
      ty = oy + (e.clientY - sy);
      applyZoom();
    });
    window.addEventListener('mouseup', function () {
      dragging = false;
      if (stage) stage.classList.remove('grabbing');
    });
  }

  /* ---------- search ---------- */
  var modal = document.getElementById('search-modal');
  var input = document.getElementById('search-input');
  var results = document.getElementById('search-results');
  var index = null;
  var sel = -1;

  function load() {
    if (index) return Promise.resolve(index);
    return fetch(base + '/search-index.json').then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
  }
  function openSearch() {
    if (!modal) return;
    modal.classList.add('is-open');
    load();
    if (input) { input.value = ''; input.focus(); }
    render('');
  }
  function closeSearch() { if (modal) modal.classList.remove('is-open'); }
  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; });
  }
  function snip(text, q) {
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return esc(text.slice(0, 140)) + '…';
    var start = Math.max(0, i - 50);
    var out = (start > 0 ? '…' : '') + esc(text.slice(start, start + 180)) + '…';
    return out.replace(new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'i'), '<mark>$1</mark>');
  }
  function render(q) {
    if (!results) return;
    sel = -1;
    if (!index) { results.innerHTML = '<p class="empty">Loading…</p>'; return; }
    q = (q || '').trim().toLowerCase();
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
      results.innerHTML = '<p class="empty">No matches. Try “idempotency”, “hot partition”, “token bucket”, “H3”.</p>';
      return;
    }
    results.innerHTML = hits.map(function (h, i) {
      var p = h.p;
      return '<a class="hit" data-i="' + i + '" href="' + base + p.u + '">' +
        '<span class="sec">' + esc(p.s) + (p.k ? ' · ' + esc(p.k) : '') + '</span>' +
        '<span class="t">' + esc(p.t) + '</span>' +
        '<span class="s">' + (q ? snip(p.b, q) : esc(p.b.slice(0, 140)) + '…') + '</span></a>';
    }).join('');
  }

  if (modal) {
    document.addEventListener('click', function (e) {
      if (e.target.hasAttribute('data-close')) closeSearch();
    });
    if (input) input.addEventListener('input', function () { render(input.value); });
    document.addEventListener('keydown', function (e) {
      var open = modal.classList.contains('is-open');
      if ((e.key === '/' || (e.key === 'k' && (e.metaKey || e.ctrlKey))) && !open) {
        var tag = (document.activeElement.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        e.preventDefault(); openSearch(); return;
      }
      if (!open) return;
      if (e.key === 'Escape') { closeSearch(); return; }
      var items = results.querySelectorAll('.hit');
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!items.length) return;
        sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items.forEach(function (el, i) { el.classList.toggle('sel', i === sel); });
        items[sel].scrollIntoView({ block: 'nearest' });
      }
      if (e.key === 'Enter' && sel >= 0 && items[sel]) window.location.href = items[sel].getAttribute('href');
    });
  }
})();
