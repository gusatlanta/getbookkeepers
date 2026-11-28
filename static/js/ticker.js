/* Auto-scrolling strip of real, blinded profiles.
   Source: the same public candidate feed as the carousel (100xrecruiting.com/api/public/candidates/search,
   metro Atlanta), which stafffinancial.com/temps.html also uses. No names or contact details; each item opens
   that candidate's blinded resume. Role pages keep bookkeeping and accounting titles. The home page
   (data-focus="bookkeepers") uses the display filter in candidate-focus.js. If fewer than 3 profiles
   load, the strip stays hidden. Pauses on hover or focus; no motion under prefers-reduced-motion. */
(function () {
  var API = 'https://100xrecruiting.com/api/public/candidates/search';
  var MAX = 24;
  var FIELD = /bookkeep|account|payroll|billing|\bA\/?P\b|\bA\/?R\b|controller|finance|financial|tax|audit|collections|reconcil/i;
  var strip = document.querySelector('.ticker');
  if (!strip || !window.fetch) return;
  var rail = strip.querySelector('.ticker-rail');
  var queries = (strip.getAttribute('data-queries') || '').split('|').filter(Boolean);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function cleanTitle(t) { return String(t || '').replace(/^[^A-Za-z0-9]+/, '').trim(); }
  function city(l) {
    var parts = String(l || '').split(',').map(function (p) { return p.trim(); }).filter(Boolean);
    if (!parts.length) return '';
    var c = parts[0].replace(/\b[a-z]/g, function (x) { return x.toUpperCase(); });
    return parts[1] && /^[a-z]{2}$/i.test(parts[1]) ? c + ', ' + parts[1].toUpperCase() : c;
  }
  function focused() { return strip.getAttribute('data-focus') === 'bookkeepers'; }
  function usable(c) {
    var t = cleanTitle(c.title);
    var ok = c.resume_url && /^https:\/\/100xrecruiting\.com\//.test(c.resume_url) && t && t.length <= 48 &&
      !/\s(at|@)\s|@/i.test(t);
    if (!ok) return false;
    if (focused()) return !!(window.gbFocus && window.gbFocus.passesTitle(c));
    return FIELD.test(t);
  }
  function item(c, hide) {
    var bits = [city(c.location), Number(c.years) > 0 ? c.years + ' yrs' : ''].filter(Boolean).map(esc).join(' &middot; ');
    return '<a class="tick" href="' + esc(c.resume_url) + '" target="_blank" rel="noopener nofollow"' +
      (hide ? ' tabindex="-1" aria-hidden="true"' : '') + '><span class="tick-dot" aria-hidden="true"></span>' +
      '<strong>' + esc(cleanTitle(c.title)) + '</strong>' + (bits ? '<span>' + bits + '</span>' : '') + '</a>';
  }
  function one(q, page) {
    var p = new URLSearchParams({ q: q, keywords: q, page: page, metro: 'atlanta', af: '1' });
    return fetch(API + '?' + p.toString()).then(function (r) { return r.ok ? r.json() : { results: [] }; })
      .then(function (j) { if (j.warming) warming = true; return j; })
      .catch(function () { return { results: [] }; });
  }
  function get(q) {
    if (!focused()) return one(q, 1).then(function (j) { return (j.results || []).filter(usable); });
    var acc = [];
    function next(page) {
      return one(q, page).then(function (j) {
        acc = acc.concat((j.results || []).filter(usable));
        var pages = Number(j.pages) || 1;
        if (page >= pages || page >= 6 || acc.length >= 40) return acc;
        return next(page + 1);
      });
    }
    return next(1);
  }
  var warming = false, tries = 0;
  function load() {
  tries++;
  var cap = focused() ? 40 : MAX;
  Promise.all(queries.map(get)).then(function (lists) {
    var seen = {}, out = [], i = 0, more = true;
    while (out.length < cap && more) {
      more = false;
      lists.forEach(function (list) {
        var c = list[i];
        if (c) { more = true; if (!seen[c.id] && out.length < cap) { seen[c.id] = 1; out.push(c); } }
      });
      i++;
    }
    var ready = focused() && window.gbFocus ? window.gbFocus.keep(out) : Promise.resolve(out);
    ready.then(function (kept) {
    if (strip.dataset.gbReady) return;
    var shown = (kept || []).slice(0, MAX);
    if (shown.length < 3) {               /* the feed answers "warming" while its cache fills; try again shortly */
      if (warming && tries < 4) { warming = false; setTimeout(load, 5000); }
      return;
    }
    strip.dataset.gbReady = '1';
    var once = shown.map(function (c) { return item(c, false); }).join('');
    var copy = shown.map(function (c) { return item(c, true); }).join('');
    rail.innerHTML = '<div class="ticker-set">' + once + '</div><div class="ticker-set" aria-hidden="true">' + copy + '</div>';
    rail.style.setProperty('--ticker-time', Math.max(40, shown.length * 5) + 's');
    strip.hidden = false;
    });
  });
  }
  load();
})();
