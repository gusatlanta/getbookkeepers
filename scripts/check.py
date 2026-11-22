#!/usr/bin/env python3
"""Check a built dist/: internal links, one H1 per page, unique titles and descriptions, JSON-LD parses,
canonicals, images, and (with --external) external links. Usage: python scripts/check.py [--external]"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"
SITE = "https://www.getbookkeepers.com"


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
    print(f"{len(pages)} html files, {len(re.findall('<loc>', sm))} sitemap urls, {len(external)} external links")
    if "--external" in sys.argv:
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
