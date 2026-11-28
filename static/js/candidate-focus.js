/* Home-page display filter for the ticker and the blinded profile cards.
   Keeps bookkeeper titles, plus office managers and executive or administrative
   assistants only when QuickBooks is in the skills/systems on the public search
   record or the same feed's résumé keyword index. Does not edit candidate records.
   The résumé HTML page is not fetched: it is a different origin response and it
   can carry contact details that must never be copied onto a card. */
(function () {
  var API = 'https://100xrecruiting.com/api/public/candidates/search';
  var QB = /quick\s*books/i;
  var BOOK = /bookkeep/i;
  var OFFICE = /\boffice\s+managers?\b/i;
  var ASSIST = /\b(?:executive|exec\.?|administrative|admin\.?)\s+assistants?\b/i;
  var TEXT_FIELDS = ['summary', 'resume', 'resume_text', 'text', 'about', 'description', 'headline', 'software', 'software_tools', 'experience', 'work_history'];
  var pending = {};

  function titleOf(c) {
    return String((c && c.title) || '').replace(/^[^A-Za-z0-9]+/, '').replace(/\s+/g, ' ').trim();
  }

  function collect(value, out) {
    if (value == null) return;
    if (typeof value === 'string') { out.push(value); return; }
    if (Array.isArray(value)) { value.forEach(function (v) { collect(v, out); }); return; }
    if (typeof value === 'object') {
      Object.keys(value).forEach(function (k) {
        var v = value[k];
        if (typeof v === 'string' || Array.isArray(v)) collect(v, out);
      });
    }
  }

  function haystack(c) {
    var out = [titleOf(c)];
    collect(c && c.skills, out);
    collect(c && c.systems, out);
    TEXT_FIELDS.forEach(function (k) { collect(c && c[k], out); });
    return out.join('\n');
  }

  /* 'book' shows with no QuickBooks check. 'qb' shows only with a QuickBooks match. '' is hidden. */
  function passesTitle(c) {
    var t = titleOf(c);
    if (!t) return '';
    if (BOOK.test(t)) return 'book';
    if (OFFICE.test(t) || ASSIST.test(t)) return 'qb';
    return '';
  }

  function quickbooks(c) { return QB.test(haystack(c)); }

  function searchQuickbooksIds(title) {
    var key = title.toLowerCase();
    if (!pending[key]) {
      pending[key] = new Promise(function (resolve) {
        var ids = {};
        function page(n) {
          var p = new URLSearchParams({ q: title, keywords: 'quickbooks', page: n, metro: 'atlanta', af: '1' });
          fetch(API + '?' + p.toString()).then(function (r) { return r.ok ? r.json() : { results: [] }; })
            .then(function (j) {
              (j.results || []).forEach(function (row) { if (row && row.id != null) ids[row.id] = 1; });
              var pages = Number(j.pages) || 1;
              if (n >= pages || n >= 8) resolve(ids);
              else page(n + 1);
            })
            .catch(function () { resolve(ids); });
        }
        page(1);
      });
    }
    return pending[key];
  }

  /* Drop office managers and assistants the résumé index does not tie to QuickBooks.
     Bookkeepers stay. Order is unchanged. */
  function keep(list) {
    var need = [];
    var titles = {};
    list.forEach(function (c) {
      if (passesTitle(c) === 'qb' && !quickbooks(c)) {
        need.push(c);
        titles[titleOf(c)] = 1;
      }
    });
    function finish(ids) {
      return list.filter(function (c) {
        var kind = passesTitle(c);
        if (kind === 'book') return true;
        if (kind === 'qb' && (quickbooks(c) || (ids && ids[c.id]))) return true;
        return false;
      });
    }
    if (!need.length) return Promise.resolve(finish(null));
    return Promise.all(Object.keys(titles).map(searchQuickbooksIds)).then(function (sets) {
      var ids = {};
      sets.forEach(function (set) { Object.keys(set).forEach(function (id) { ids[id] = 1; }); });
      return finish(ids);
    });
  }

  window.gbFocus = { passesTitle: passesTitle, quickbooks: quickbooks, keep: keep, titleOf: titleOf };
})();
