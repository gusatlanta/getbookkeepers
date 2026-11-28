/* Blinded candidate profile carousel.
   Source: the public candidate search feed that https://www.stafffinancial.com/temps.html uses
   (100xrecruiting.com/api/public/candidates/search, metro Atlanta). Profiles are blinded at the source:
   no names or contact details. Each card opens that candidate's blinded resume. Nothing is invented here;
   if the feed fails or returns fewer than 3 profiles, the section stays hidden. */
(function () {
  var API = 'https://100xrecruiting.com/api/public/candidates/search';
  var MAX = 14;
  var section = document.querySelector('.profiles');
  if (!section || !window.fetch) return;
  var track = section.querySelector('.profiles-track');
  var queries = (section.getAttribute('data-queries') || '').split('|').filter(Boolean);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function cleanTitle(t) { return String(t || '').replace(/^[^A-Za-z0-9]+/, '').trim(); }
  function cleanLoc(l) {
    return String(l || '').split(',').map(function (part) {
      part = part.trim();
      if (/^[a-z]{2}$/i.test(part)) return part.toUpperCase();
      return part.replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); });
    }).join(', ');
  }
  function usable(c) {
    var t = cleanTitle(c.title);
    return c.resume_url && /^https:\/\/100xrecruiting\.com\//.test(c.resume_url) && t && t.length <= 60 &&
      !/\s(at|@)\s|@/i.test(t);
  }
  function card(c) {
    var chips = [];
    (c.systems || []).concat(c.skills || []).forEach(function (s) {
      if (chips.length < 4 && chips.indexOf(s) < 0 && String(s).length <= 28) chips.push(s);
    });
    var years = Number(c.years) > 0 ? c.years + ' yrs experience' : '';
    var meta = [cleanLoc(c.location), years].filter(Boolean).map(esc).join(' &middot; ');
    return '<a class="profile" href="' + esc(c.resume_url) + '" target="_blank" rel="noopener nofollow">' +
      '<span class="profile-kicker">Blinded profile</span>' +
      '<strong class="profile-title">' + esc(cleanTitle(c.title)) + '</strong>' +
      (meta ? '<span class="profile-meta">' + meta + '</span>' : '') +
      (chips.length ? '<span class="chips">' + chips.map(function (s) { return '<span class="chip">' + esc(s) + '</span>'; }).join('') + '</span>' : '') +
      '<span class="profile-cta">View blinded resume &rarr;</span></a>';
  }
  function get(q) {
    var p = new URLSearchParams({ q: q, keywords: q, page: 1, metro: 'atlanta', af: '1' });
    return fetch(API + '?' + p.toString()).then(function (r) { return r.ok ? r.json() : { results: [] }; })
      .then(function (j) { if (j.warming) warming = true; return (j.results || []).filter(usable); })
      .catch(function () { return []; });
  }
  var warming = false, tries = 0;
  function load() {
  tries++;
  Promise.all(queries.map(get)).then(function (lists) {
    var seen = {}, out = [], i = 0, more = true;
    while (out.length < MAX && more) {           /* round-robin across role queries */
      more = false;
      lists.forEach(function (list) {
        var c = list[i];
        if (c) { more = true; if (!seen[c.id] && out.length < MAX) { seen[c.id] = 1; out.push(c); } }
      });
      i++;
    }
    if (out.length < 3) {               /* the feed answers "warming" while its cache fills; try again shortly */
      if (warming && tries < 4) { warming = false; setTimeout(load, 5000); }
      return;
    }
    track.innerHTML = out.map(card).join('');
    section.hidden = false;
    var step = function () { return Math.max(260, track.clientWidth * 0.8); };
    section.querySelectorAll('.pbtn').forEach(function (b) {
      b.addEventListener('click', function () { track.scrollBy({ left: step() * Number(b.getAttribute('data-dir')), behavior: 'smooth' }); });
    });
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      var paused = false;
      ['mouseenter', 'focusin', 'touchstart'].forEach(function (e) { track.addEventListener(e, function () { paused = true; }, { passive: true }); });
      ['mouseleave', 'focusout'].forEach(function (e) { track.addEventListener(e, function () { paused = false; }); });
      setInterval(function () {
        if (paused || document.hidden) return;
        var end = track.scrollLeft + track.clientWidth >= track.scrollWidth - 4;
        track.scrollTo({ left: end ? 0 : track.scrollLeft + 280, behavior: 'smooth' });
      }, 3500);
    }
  });
  }
  load();
})();
