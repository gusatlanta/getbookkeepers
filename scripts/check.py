#!/usr/bin/env python3
"""Check a built dist/: internal links, one H1 per page, unique titles and descriptions, JSON-LD parses,
canonicals, images, and (with --external) external links. Usage: python scripts/check.py [--external]"""
from __future__ import annotations

import json
import re
import subprocess
import time
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"
SITE = "https://www.getbookkeepers.com"
PAGES = DIST.parent / "pages"
MAX_DESC = 150
# Gus: no bill rates, fees, or pricing anywhere. Salary figures from the 2026 Salary Guide ($67K style) are allowed.
PRICING = [
    (r"\$\s?\d[\d,.]*", "dollar amount outside a salary or pay context"),
    (r"\bbill(ing)? rates? (of|is|are|from|start)", "bill rate amount"), (r"\b(per|an|/)\s?(hour|hr)\b", "hourly price"),
    (r"\bhourly rate", "hourly rate"), (r"\b(placement|flat|direct hire|search|conversion|finder'?s?) fees?\b", "fee"),
    (r"\bfees? (of|is|are|starts?)\b", "fee"), (r"\bmark-?ups?\b", "markup"), (r"\bpric(e|es|ed|ing)\b", "pricing"),
    (r"\bhiresmart\b", "HireSmart pricing"), (r"\bmembership\b", "membership pricing"),
    (r"\d+\s?%\s?(fee|of (the )?(first|annual|base|starting)|of (their|the candidate'?s) (salary|pay))", "percentage fee"),
    (r"\bquote[ds]?\b", "quotes"), (r"\bcost[s]? (of|to) (hire|hiring|a search|the search)", "cost of hiring"),
]
# Internal-link rules by page kind: "/path/" = that page, "*kind" = every page of that kind, "1kind" = at least one,
# "^area" = the city's own area guide, "^nearby" = the city's nearby cities, "^cities" = every city in an area.
LINK_RULES = {
    "role": ["/roles/", "*role", "1service", "/atlanta/", "/faq/"],
    "service": ["1role", "*service", "/atlanta/", "/faq/"],
    "local": ["*service", "*role", "*area", "*city"],
    "area": ["*service", "/atlanta/", "^cities"],
    "city": ["/atlanta/", "^area", "^nearby", "*service", "1role", "/faq/", "/bookkeeper-salary/"],
    "industry": ["/industries/", "1role", "1service", "/atlanta/", "1city"],
    "hub": ["1service"],
    "faq": ["*service", "*role"],
    "page": ["*role"],
}


META: dict[str, dict] = {}


def front_matter() -> dict[str, str]:
    kinds = {}
    for md in PAGES.rglob("*.md"):
        fm = md.read_text().split("---", 2)[1]
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", fm, re.M))
        kinds[meta["path"]] = meta["kind"]
        META[meta["path"]] = meta
    return kinds


def rule_targets(rule: str, path: str) -> list[str]:
    meta = META[path]
    if rule == "^area":
        return [meta["area"]]
    if rule == "^nearby":
        return [p.strip() for p in meta.get("nearby", "").split(",") if p.strip()]
    return [p for p, m in META.items() if m["kind"] == "city" and m.get("area") == path]


def main_links(text: str) -> set[str]:
    main = text.split('<main id="main">', 1)[-1].split("</main>", 1)[0]
    out = set()
    for h in re.findall(r'href="([^"]+)"', main):
        if h.startswith(SITE):
            h = h[len(SITE):] or "/"
        if h.startswith("/"):
            out.add(h.split("#")[0])
    return out


def visible_text(text: str) -> str:
    import html as _h
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
    return _h.unescape(re.sub(r"<[^>]+>", " ", t)) + " " + " ".join(_h.unescape(c) for c in re.findall(r'content="([^"]*)"', text))


def pricing_hits(vis: str) -> list[str]:
    hits = []
    for pat, why in PRICING:
        for m in re.finditer(pat, vis, flags=re.I):
            if why.startswith("dollar"):
                if vis[m.end():m.end() + 2].lstrip().startswith("K"):
                    continue  # $67K style: salary figures from the Salary Guide
                if re.search(r"salary|salaries|\bpay\b|paid|\bask|median|BLS|wage", vis[max(0, m.start() - 250):m.end() + 250], re.I):
                    continue
            hits.append(f"pricing guard ({why}): ...{' '.join(vis[max(0, m.start() - 40):m.end() + 40].split())}...")
    return hits


def site_checks() -> list[str]:
    errors = []
    kinds = front_matter()
    by_kind: dict[str, list[str]] = {}
    for path, k in kinds.items():
        by_kind.setdefault(k, []).append(path)
    links, inbound = {}, {p: 0 for p in kinds}
    for path in kinds:
        text = (DIST / path.lstrip("/") / "index.html").read_text()
        links[path] = main_links(text)
        for t in links[path]:
            if t in inbound and t != path:
                inbound[t] += 1
        desc = re.search(r'<meta name="description" content="([^"]*)"', text).group(1)
        if len(desc) > MAX_DESC:
            errors.append(f"{path}: description {len(desc)} chars")
        errors += [f"{path}: {h}" for h in pricing_hits(visible_text(text))]
        if kinds[path] in ("home", "role") or path == "/roles/":
            if 'class="ticker"' not in text or "/js/ticker.js" not in text:
                errors.append(f"{path}: missing the scrolling profile strip")
        if path == "/":
            if text.count('data-focus="bookkeepers"') != 2 or "/js/candidate-focus.js" not in text:
                errors.append(f"{path}: home ticker and profile cards must use the bookkeeper display filter")
        elif 'data-focus="bookkeepers"' in text:
            errors.append(f"{path}: bookkeeper display filter is only for the home page")
        if kinds[path] == "page":
            ctas = re.findall(r'<a[^>]*data-cta="[^"]*"[^>]*>', text)
            targets = {re.search(r'href="([^"]+)"', c).group(1) for c in ctas}
            if targets != {"https://100xjobs.com/"}:
                errors.append(f"{path}: job seeker CTA targets {targets}")
    errors += [f"llms.txt: {h}" for h in pricing_hits((DIST / "llms.txt").read_text())]
    for path, n in inbound.items():
        if path != "/" and n == 0:
            errors.append(f"orphan page (no in-content links to it): {path}")
    for path, k in kinds.items():
        for rule in LINK_RULES.get(k, []):
            if rule.startswith("^"):
                missing = [x for x in rule_targets(rule, path) if x not in links[path]]
            elif rule.startswith("/"):
                missing = [rule] if rule != path and rule not in links[path] else []
            elif rule.startswith("*"):
                missing = [x for x in by_kind.get(rule[1:], []) if x != path and x not in links[path]]
            else:
                missing = [] if any(x in links[path] for x in by_kind.get(rule[1:], [])) else [f"at least one {rule[1:]}"]
            errors += [f"{path} ({k}): missing internal link to {m}" for m in missing]
    total = sum(len(v) for v in links.values())
    print(f"in-content internal links: {total} unique across {len(links)} pages; orphans, link rules, descriptions, pricing guard checked")
    return errors


def profile_feed_check() -> list[str]:
    js = (DIST / "js" / "profiles.js").read_text()
    api = re.search(r"var API = '([^']+)'", js).group(1)
    errs, n = [], 0
    for q in ("bookkeeper", "accounts payable", "payroll", "staff accountant"):
        url = api + "?" + urllib.parse.urlencode({"q": q, "keywords": q, "page": 1, "metro": "atlanta", "af": "1"})
        try:
            for _ in range(8):  # the feed answers {"warming": true} with no results while its cache fills
                data = json.loads(subprocess.run(["curl", "-s", "-m", "30", "-A", "Mozilla/5.0", url], capture_output=True, text=True).stdout)
                if not data.get("warming") or data.get("results"):
                    break
                time.sleep(10)
            n += sum(1 for r in data.get("results", []) if r.get("resume_url"))
        except Exception as e:
            errs.append(f"profile feed error for {q}: {e}")
    print(f"  profile feed: {n} blinded profiles with resume links across 4 queries")
    if n < 3:
        errs.append("profile feed returned fewer than 3 profiles (carousel will stay hidden)")
    return errs


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.h1, self.ld, self._ld, self.title, self._t, self.meta, self.canon = [], 0, [], None, "", False, {}, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("a", "link") and a.get("href"):
            if tag == "link" and a.get("rel") == "canonical":
                self.canon = a["href"]
            elif tag == "a" or a.get("rel") in ("icon", "apple-touch-icon", "stylesheet"):
                self.links.append(a["href"])
        if tag in ("img", "script") and a.get("src"):
            self.links.append(a["src"])
        if tag == "h1":
            self.h1 += 1
        if tag == "script" and a.get("type") == "application/ld+json":
            self._ld = ""
        if tag == "title":
            self._t = True
        if tag == "meta":
            k = a.get("name") or a.get("property")
            if k:
                self.meta[k] = a.get("content", "")

    def handle_endtag(self, tag):
        if tag == "script" and self._ld is not None:
            self.ld.append(self._ld)
            self._ld = None
        if tag == "title":
            self._t = False

    def handle_data(self, d):
        if self._ld is not None:
            self._ld += d
        if self._t:
            self.title += d


def resolve(href: str, page_url_path: str) -> Path | None:
    if href.startswith(SITE):
        href = href[len(SITE):] or "/"
    if re.match(r"^(https?:|mailto:|tel:|#)", href):
        return None
    href = href.split("#")[0].split("?")[0]
    if not href.startswith("/"):
        href = page_url_path.rsplit("/", 1)[0] + "/" + href
    p = DIST / href.lstrip("/")
    return p / "index.html" if href.endswith("/") else p


def main() -> int:
    errors, titles, descs, external = [], {}, {}, set()
    pages = sorted(DIST.rglob("*.html"))
    for f in pages:
        url_path = "/" + str(f.relative_to(DIST)).replace("index.html", "")
        p = P()
        p.feed(f.read_text())
        is404 = f.name == "404.html"
        if p.h1 != 1:
            errors.append(f"{url_path}: {p.h1} h1 tags")
        for blob in p.ld:
            try:
                data = json.loads(blob)
                types = [n.get("@type") for n in data.get("@graph", [data])]
            except Exception as e:
                errors.append(f"{url_path}: JSON-LD does not parse: {e}")
        if not is404:
            if p.canon != SITE + url_path:
                errors.append(f"{url_path}: canonical {p.canon}")
            titles.setdefault(p.title, []).append(url_path)
            descs.setdefault(p.meta.get("description"), []).append(url_path)
            for k in ("og:title", "og:image", "twitter:card", "description"):
                if not p.meta.get(k):
                    errors.append(f"{url_path}: missing {k}")
            og = resolve(p.meta.get("og:image", ""), url_path)
            if og and not og.exists():
                errors.append(f"{url_path}: og image missing {og}")
            print(f"  ok {url_path:48} h1={p.h1} ld={types}")
        for href in p.links:
            target = resolve(href, url_path)
            if target is None:
                if href.startswith("http"):
                    external.add(href)
                continue
            if not target.exists():
                errors.append(f"{url_path}: broken link {href}")
    for d, label in ((titles, "title"), (descs, "description")):
        for k, v in d.items():
            if len(v) > 1:
                errors.append(f"duplicate {label} on {v}")
    sm = (DIST / "sitemap.xml").read_text()
    for loc in re.findall(r"<loc>(.*?)</loc>", sm):
        if not resolve(loc, "/").exists():
            errors.append(f"sitemap entry missing: {loc}")
    errors += site_checks()
    print(f"{len(pages)} html files, {len(re.findall('<loc>', sm))} sitemap urls, {len(external)} external links")
    if "--external" in sys.argv:
        errors += profile_feed_check()
        for u in sorted(external):
            if "fonts.g" in u:
                continue
            code = subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0", "-o", "/dev/null", "-w", "%{http_code}", u],
                                  capture_output=True, text=True).stdout
            print(f"  {code} {u}")
            if code != "200":
                errors.append(f"external {code}: {u}")
    print("\n".join(errors) if errors else "ALL CHECKS PASSED")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
