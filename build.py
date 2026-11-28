#!/usr/bin/env python3
"""Build the GetBookkeepers static site (getbookkeepers.com) from pages/**/*.md into dist/."""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
PAGES_DIR = ROOT / "pages"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

SITE_NAME = "GetBookkeepers"
SITE_URL = "https://www.getbookkeepers.com"
# The real Staff Financial Group hiring request form (Get Started). Every page's one CTA points here.
GET_STARTED_URL = "https://www.stafffinancial.com/opt-in.html"
SF_URL = "https://www.stafffinancial.com/"
TEMPS_URL = "https://www.stafffinancial.com/temps.html"
SALARY_GUIDE_URL = "https://www.stafffinancial.com/salary-guide.html"
PHONES = ("404-250-0790", "678-777-5627")
JOBS_URL = "https://100xjobs.com/"
# Google Analytics 4 measurement ID for getbookkeepers.com. Empty until a property exists.
GA_ID = ""
FAQ_HEADING = "## Frequently asked questions"
MAX_DESC = 150
KINDS = {"home", "service", "hub", "role", "local", "area", "city", "industry", "salary", "faq", "page"}
# Pages that get Article schema (guides), matching how oneminuteinterviewtips marks up its guides.
ARTICLE_KINDS = {"role", "local", "area", "city", "industry", "salary"}
ATLANTA, FAQ, ROLES_HUB, IND_HUB, SALARY, JOBS_PAGE = (
    "/atlanta/", "/faq/", "/roles/", "/industries/", "/bookkeeper-salary/", "/job-seekers/")
DEFAULT_PROFILE_QUERIES = "bookkeeper|accounts payable|accounts receivable|payroll specialist|staff accountant"
# Copy rules (see the copy-and-page-rules-check skill). The build fails if rendered text breaks one.
BANNED = [
    ("\u2014", "em dash"), ("\u2013", "en dash"), (r"\bpermanent\b", "say Direct Hire"),
    (r"\bprojects?\b", "say job"), (r"\bscout\b", "never Scout"), (r"zip\s?apply", "promote 100X"),
    (r"\bfree\b", "no free claims"), (r"video resume", "say video intro"), ("\u2122", "no TM"),
    (r"\bclaude\b", "no vendor names"),
]

ORG = {
    "@type": ["Organization", "ProfessionalService"],
    "@id": f"{SITE_URL}/#org",
    "name": "Staff Financial Group",
    "alternateName": SITE_NAME,
    "url": SF_URL,
    "logo": f"{SITE_URL}/images/logo-mark-512.png",
    "image": f"{SITE_URL}/images/og-default.png",
    "description": "Finance and accounting recruiting and staffing firm in metro Atlanta. Bookkeepers through Temp, Contract, Temp-to-Hire, Direct Hire, and Payrolling.",
    "telephone": "+1-404-250-0790",
    "foundingDate": "2005",
    "address": {"@type": "PostalAddress", "addressLocality": "Atlanta", "addressRegion": "GA", "addressCountry": "US"},
    "areaServed": [{"@type": "City", "name": "Atlanta"}, {"@type": "AdministrativeArea", "name": "Southeast United States"},
                   {"@type": "Country", "name": "United States"}],
    "parentOrganization": {"@type": "Organization", "name": "NorthPoint Search Group", "url": "https://www.northpointsearchgroup.com/"},
    "sameAs": [SF_URL],
}

SLUG_PATH_RE = re.compile(r"^/(?:[a-z0-9]+(?:-[a-z0-9]+)*/)*$")


# ---------- loading ----------

def parse_front_matter(text: str, name: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise ValueError(f"{name}: missing front matter")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.strip()


def split_faq(body: str, name: str) -> tuple[str, list[tuple[str, str]]]:
    if FAQ_HEADING not in body:
        return body, []
    main, faq_md = body.split(FAQ_HEADING, 1)
    faqs = []
    for block in re.split(r"^### ", faq_md, flags=re.M)[1:]:
        q, _, a = block.partition("\n")
        if not a.strip():
            raise SystemExit(f"{name}: FAQ '{q}' has no answer")
        faqs.append((q.strip(), a.strip()))
    return main.strip(), faqs


def plain(md_text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md_text)
    return re.sub(r"[*_`#>]", "", text).strip()


def split_list(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def load_pages() -> list[dict]:
    pages, paths, titles, descs = [], set(), set(), set()
    required = ("title", "description", "h1", "lede", "path", "kicker", "image", "crumb", "kind", "date", "anchor")
    for src in sorted(PAGES_DIR.rglob("*.md")):
        meta, body = parse_front_matter(src.read_text(encoding="utf-8"), src.name)
        for f in required:
            if not meta.get(f):
                raise SystemExit(f"{src.name} is missing '{f}'")
        if not SLUG_PATH_RE.match(meta["path"]):
            raise SystemExit(f"{src.name}: bad path {meta['path']}")
        for seen, key in ((paths, "path"), (titles, "title"), (descs, "description")):
            if meta[key] in seen:
                raise SystemExit(f"{src.name}: duplicate {key}")
            seen.add(meta[key])
        if len(meta["description"]) > MAX_DESC:
            raise SystemExit(f"{src.name}: description is {len(meta['description'])} chars (max {MAX_DESC})")
        if meta["kind"] not in KINDS:
            raise SystemExit(f"{src.name}: unknown kind {meta['kind']}")
        if not (STATIC_DIR / "images" / meta["image"]).is_file():
            raise SystemExit(f"{src.name}: image {meta['image']} not found")
        main, faqs = split_faq(body, src.name)
        pages.append({**meta, "body": main, "faqs": faqs, "date": dt.date.fromisoformat(meta["date"]),
                      "services": split_list(meta.get("services", "")), "roles": split_list(meta.get("roles", "")),
                      "order": int(meta.get("order", "50")), "og_image": f"og-{Path(meta['image']).stem}.png"})
    by = {p["path"]: p for p in pages}
    for p in pages:
        if p["kind"] == "city" and p.get("area") in by:
            p["area_crumb"] = by[p["area"]]["crumb"]
    return pages


def of_kind(pages: list[dict], kind: str) -> list[dict]:
    return sorted((p for p in pages if p["kind"] == kind), key=lambda p: (p["order"], p["path"]))


def md(text: str) -> str:
    return markdown.markdown(text, extensions=["extra", "sane_lists"])


# ---------- page parts ----------

def cta_button(label: str = "Get Started", url: str = GET_STARTED_URL, extra: str = "") -> str:
    kind = "get-started" if url == GET_STARTED_URL else "find-jobs"
    return f'<a class="btn btn-cta{extra}" href="{html.escape(url)}" data-cta="{kind}">{html.escape(label)}</a>'


def ga_snippet() -> str:
    if not GA_ID:
        return ""
    return f"""
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');
  document.addEventListener('click',function(e){{var a=e.target.closest('[data-cta]');if(a){{gtag('event','generate_lead',{{cta:a.dataset.cta,page:location.pathname}});}}}});</script>"""


def article_meta(page: dict) -> str:
    if page.get("kind") not in ARTICLE_KINDS:
        return ""
    d = page["date"].isoformat()
    return f'\n  <meta property="article:published_time" content="{d}">\n  <meta property="article:modified_time" content="{d}">'


def nav_html(page: dict, pages: list[dict]) -> str:
    def menu(label: str, href: str, items: list[dict], current: bool) -> str:
        links = "".join(f'<a href="{p["path"]}">{html.escape(p["crumb"])}</a>' for p in items)
        cur = ' aria-current="page"' if current else ""
        return (f'<div class="nav-item has-menu"><a class="nav-top" href="{href}"{cur}>{label}</a>'
                f'<div class="nav-menu{" nav-menu-wide" if len(items) > 8 else ""}">{links}</div></div>')

    path, kind = page["path"], page.get("kind")
    areas = of_kind(pages, "area")
    atl_items = [p for p in pages if p["path"] == ATLANTA] + areas + of_kind(pages, "city")
    return (
        menu("Ways to hire", "/#ways-to-hire", of_kind(pages, "service"), kind == "service")
        + menu("Roles", ROLES_HUB, of_kind(pages, "role"), path.startswith(ROLES_HUB))
        + menu("Industries", IND_HUB, of_kind(pages, "industry"), path.startswith(IND_HUB))
        + menu("Atlanta", ATLANTA, atl_items, path.startswith(ATLANTA))
        + f'<div class="nav-item"><a class="nav-top" href="{SALARY}"{" aria-current=\"page\"" if path == SALARY else ""}>Salary data</a></div>'
        + f'<div class="nav-item"><a class="nav-top" href="{FAQ}"{" aria-current=\"page\"" if path == FAQ else ""}>FAQ</a></div>'
    )


def brand_html(extra: str = "") -> str:
    return (f'<a class="brand{extra}" href="/" aria-label="GetBookkeepers.com home">'
            '<img src="/images/sfg-mark.png" alt="Staff Financial Group logo" width="38" height="45">'
            '<span class="brand-text"><span class="brand-name">GetBookkeepers.com</span>'
            '<span class="brand-tag">Staff Financial Group &middot; Powered by NorthPoint</span></span></a>')


def page_shell(page: dict, content: str, schema: list[dict], pages: list[dict], scripts: str = "") -> str:
    url = SITE_URL + page["path"]
    t, d = html.escape(page["title"]), html.escape(page["description"])
    og_img = f"{SITE_URL}/images/{page['og_image']}"
    ld = json.dumps({"@context": "https://schema.org", "@graph": schema}, ensure_ascii=False, indent=1)
    services, roles, inds, areas = (of_kind(pages, k) for k in ("service", "role", "industry", "area"))

    def col(title: str, items: list[tuple[str, str]]) -> str:
        return f'<div><h2 class="footer-h">{title}</h2><ul>' + "".join(f'<li><a href="{h}">{html.escape(l)}</a></li>' for h, l in items) + "</ul></div>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{t}</title>
  <meta name="description" content="{d}">
  <link rel="canonical" href="{url}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#0b1f3d">
  <link rel="icon" href="/favicon.png" type="image/png" sizes="32x32">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:type" content="{'article' if page.get('kind') in ARTICLE_KINDS else 'website'}">{article_meta(page)}
  <meta property="og:locale" content="en_US">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{og_img}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{og_img}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700&display=swap">
  <link rel="stylesheet" href="/css/styles.css">
  <script type="application/ld+json">
{ld}
  </script>{ga_snippet()}
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="wrap header-inner">
      {brand_html()}
      <nav class="nav" aria-label="Main">{nav_html(page, pages)}</nav>
      {cta_button("Search jobs", page["cta_url"], " btn-sm header-cta") if page.get("cta_url") else cta_button(extra=" btn-sm header-cta")}
    </div>
  </header>
  <main id="main">
{content}
  </main>
  <footer class="site-footer">
    <div class="wrap footer-grid">
      <div class="footer-about">
        {brand_html(" brand-footer")}
        <p>GetBookkeepers is a service of <a href="{SF_URL}">Staff Financial Group</a>, a finance and accounting recruiting and staffing firm in metro Atlanta since 2005, powered by NorthPoint Search Group.</p>
        <p><a href="tel:+14042500790">{PHONES[0]}</a> &middot; <a href="tel:+16787775627">{PHONES[1]}</a></p>
      </div>
      {col("Ways to hire", [(p["path"], p["crumb"]) for p in services])}
      {col("Roles", [(ROLES_HUB, "All bookkeeper roles")] + [(p["path"], p["crumb"]) for p in roles])}
      {col("Industries", [(IND_HUB, "All industries")] + [(p["path"], p["crumb"]) for p in inds])}
      {col("Atlanta", [(ATLANTA, "Metro Atlanta")] + [(p["path"], p["crumb"]) for p in areas] + [(SALARY, "Bookkeeper salary data"), (FAQ, "FAQ"), (JOBS_PAGE, "Bookkeeping jobs")])}
      {col("Atlanta cities", [(p["path"], p["crumb"]) for p in of_kind(pages, "city")])}
    </div>
    <div class="wrap footer-base">Atlanta, GA &middot; &copy; {dt.date.today().year} Staff Financial Group. Powered by NorthPoint. All rights reserved. &middot; <a href="{TEMPS_URL}">Browse available talent</a> &middot; <a href="{SALARY_GUIDE_URL}">2026 Salary Guide</a></div>
  </footer>{scripts}
</body>
</html>
"""


def crumb_trail(page: dict) -> list[tuple[str, str]]:
    trail = [("/", "Home")]
    p = page["path"]
    if page["kind"] == "role":
        trail.append((ROLES_HUB, "Bookkeeper roles"))
    elif page["kind"] == "industry":
        trail.append((IND_HUB, "Industries"))
    elif page["kind"] == "area":
        trail.append((ATLANTA, "Atlanta"))
    elif page["kind"] == "city":
        trail.append((ATLANTA, "Atlanta"))
        if page.get("area") and page["area"] != ATLANTA:
            trail.append((page["area"], page["area_crumb"]))
    if p != "/":
        trail.append((p, page["crumb"]))
    return trail


def h1_html(page: dict) -> str:
    h1 = html.escape(page["h1"])
    acc = page.get("h1_accent")
    if acc and html.escape(acc) in h1:
        h1 = h1.replace(html.escape(acc), f'<span class="accent">{html.escape(acc)}</span>', 1)
    return h1


def hero(page: dict) -> str:
    cta_url = page.get("cta_url", GET_STARTED_URL)
    cta_label = page.get("cta_label", "Get Started")
    crumbs = ""
    if page["path"] != "/":
        crumbs = '<nav class="crumbs" aria-label="Breadcrumb">' + " / ".join(
            f'<a href="{h}">{html.escape(l)}</a>' for h, l in crumb_trail(page)[:-1]
        ) + f' / <span aria-current="page">{html.escape(page["crumb"])}</span></nav>'
    return f"""    <section class="hero">
      <div class="wrap hero-grid">
        <div class="hero-copy">
          {crumbs}
          <p class="eyebrow"><span class="dot"></span>{html.escape(page['kicker'])}</p>
          <h1>{h1_html(page)}</h1>
          <p class="lede">{html.escape(page['lede'])}</p>
          <div class="hero-actions">{cta_button(cta_label, cta_url, ' btn-lg')}<span class="hero-note">{html.escape(page.get('cta_note', 'Tell us about the job. A blinded shortlist comes back in 48 to 72 hours.'))}</span></div>
        </div>
        <figure class="hero-art"><img src="/images/{page['image']}" alt="{html.escape(page.get('image_alt') or page['h1'])}" width="800" height="520"></figure>
      </div>
    </section>"""


TICKER_QUERIES = "bookkeeper|full charge bookkeeper|accounts payable|accounts receivable|payroll specialist|staff accountant|accountant|billing specialist"


def ticker_html(page: dict) -> str:
    """Auto-scrolling strip of real, blinded bookkeeping and accounting profiles from the same public feed as the carousel.
    Sits right under the header on the home page and the roles pages. Hidden until at least 3 profiles load."""
    if page["kind"] not in ("home", "role") and page["path"] != ROLES_HUB:
        return ""
    return f"""    <section class="ticker" data-queries="{TICKER_QUERIES}" aria-label="Blinded bookkeeping and accounting profiles available in metro Atlanta" hidden>
      <div class="ticker-label"><a href="{TEMPS_URL}">Available now<span> in metro Atlanta</span></a></div>
      <div class="ticker-window"><div class="ticker-rail"></div></div>
    </section>"""


def profiles_html(page: dict) -> str:
    """Carousel of real, blinded candidate profiles, loaded live from the same public feed stafffinancial.com/temps.html uses.
    Hidden until at least 3 profiles load, so nothing shows if the feed is down."""
    if page["kind"] not in ("home", "role") and page["path"] != ROLES_HUB:
        return ""
    queries = page.get("profiles", DEFAULT_PROFILE_QUERIES)
    heading = page.get("profiles_heading", "Bookkeeping and accounting candidates in our database")
    return f"""    <section class="profiles" data-queries="{html.escape(queries)}" aria-labelledby="profiles-h" hidden>
      <div class="wrap profiles-head">
        <div><h2 id="profiles-h">{html.escape(heading)}</h2>
        <p>Real, blinded profiles from Staff Financial Group's metro Atlanta candidate database. No names or contact details. Click a card to see the blinded resume.</p></div>
        <div class="profiles-ctrl"><button type="button" class="pbtn" data-dir="-1" aria-label="Previous profiles">&#8249;</button><button type="button" class="pbtn" data-dir="1" aria-label="Next profiles">&#8250;</button></div>
      </div>
      <div class="profiles-track" tabindex="0" aria-label="Candidate profiles"></div>
      <p class="wrap profiles-foot"><a href="{TEMPS_URL}">Browse all available talent at Staff Financial Group</a></p>
    </section>"""


def faq_html(faqs: list[tuple[str, str]]) -> str:
    if not faqs:
        return ""
    items = "".join(f"<details><summary>{html.escape(q)}</summary>{md(a)}</details>" for q, a in faqs)
    return f'<section class="faq" aria-labelledby="faq-h"><h2 id="faq-h">Frequently asked questions</h2>{items}</section>'


def link_groups(page: dict, pages: list[dict]) -> list[tuple[str, list[str], bool]]:
    """Internal-link plan by page kind: (heading, paths, as_cards). check.py verifies the required links."""
    paths = lambda k: [p["path"] for p in of_kind(pages, k)]  # noqa: E731
    services, roles, inds, areas = paths("service"), paths("role"), paths("industry"), paths("area")
    me, kind = page["path"], page["kind"]
    others = lambda xs: [x for x in xs if x != me]  # noqa: E731
    if kind == "home":
        return [("Bookkeeper role guides", roles, True), ("Bookkeeping by industry", inds, True),
                ("Hiring in metro Atlanta", areas, True), ("More", [ROLES_HUB, IND_HUB, ATLANTA, SALARY, FAQ, JOBS_PAGE], False)]
    if kind == "service":
        return [("Bookkeeper roles that fit this hire type", page["roles"], True),
                ("Other ways to hire a bookkeeper", others(services), True), ("More", [ATLANTA, SALARY, IND_HUB, FAQ], False)]
    if kind == "role":
        return [("Best ways to hire for this role", page["services"], True),
                ("Other bookkeeper roles", others(roles), True), ("More", [ROLES_HUB, ATLANTA, SALARY, IND_HUB, FAQ], False)]
    if kind == "hub" and me == ROLES_HUB:
        return [("Role guides", roles, True), ("Ways to hire a bookkeeper", services, True),
                ("More", [IND_HUB, ATLANTA, SALARY, FAQ], False)]
    if kind == "hub":
        return [("Industry guides", inds, True), ("Ways to hire a bookkeeper", services, True),
                ("More", [ROLES_HUB, ATLANTA, SALARY, FAQ], False)]
    cities = paths("city")
    if kind == "city":
        more = [x for x in [page.get("area"), ATLANTA, SALARY, IND_HUB, FAQ] if x]
        return [(f"Nearby cities", split_list(page.get("nearby", "")), True),
                (f"Ways to hire a bookkeeper in {page['city']}", services, True),
                ("Bookkeeper roles", roles, False), ("More", list(dict.fromkeys(more)), False)]
    if kind == "local":
        return [("Metro Atlanta areas", areas, True), ("Metro Atlanta cities", cities, True), ("Ways to hire a bookkeeper in Atlanta", services, True),
                ("Bookkeeper roles we fill in Atlanta", roles, True), ("More", [SALARY, IND_HUB, FAQ], False)]
    if kind == "area":
        return [("Cities in this area", [p["path"] for p in of_kind(pages, "city") if p.get("area") == me], True),
                ("Other metro Atlanta areas", others(areas), True), ("Ways to hire a bookkeeper", services, True),
                ("Bookkeeper roles", roles, False), ("More", [ATLANTA, SALARY, IND_HUB, FAQ], False)]
    if kind == "industry":
        return [("Roles this industry hires most", page["roles"], True), ("Ways to hire", page["services"], True),
                ("Other industry guides", others(inds), False), ("Hire a bookkeeper near you in metro Atlanta", cities, False),
                ("More", [IND_HUB, ATLANTA, SALARY, FAQ], False)]
    if kind == "salary":
        return [("Hire for these roles", roles, True), ("Ways to hire a bookkeeper", services, True),
                ("More", [ATLANTA, IND_HUB, FAQ], False)]
    if kind == "faq":
        return [("Ways to hire a bookkeeper", services, True), ("Bookkeeper role guides", roles, True),
                ("Industry guides", inds, False), ("More", [ROLES_HUB, ATLANTA, SALARY], False)]
    return [("What employers look for, by role", [ROLES_HUB] + roles, False), ("Pay data", [SALARY], False)]


def related_html(page: dict, pages: list[dict], by_path: dict[str, dict]) -> str:
    out = []
    for heading, paths, as_cards in link_groups(page, pages):
        for p in paths:
            if p not in by_path:
                raise SystemExit(f"{page['path']}: linked page {p} does not exist")
        if as_cards:
            cards = "".join(
                f'<a class="card card-link" href="{p}"><span class="card-kicker">{html.escape(by_path[p]["kicker"])}</span>'
                f'<strong>{html.escape(by_path[p]["anchor"])}</strong><span>{html.escape(by_path[p]["description"])}</span></a>'
                for p in paths)
            out.append(f'<h2>{html.escape(heading)}</h2><div class="cards">{cards}</div>')
        else:
            pills = "".join(f'<a class="pill" href="{p}">{html.escape(by_path[p]["anchor"])}</a>' for p in paths)
            out.append(f'<h2 class="h-small">{html.escape(heading)}</h2><div class="pills">{pills}</div>')
    return f'<section class="related" aria-label="Related pages">{"".join(out)}</section>'


def aside_html(page: dict) -> str:
    if page.get("cta_url"):
        return f"""<aside class="side"><div class="side-card"><h2>Find your next job</h2>
<p>{html.escape(page.get('cta_note', ''))}</p>{cta_button(page['cta_label'], page['cta_url'])}</div></aside>"""
    return f"""<aside class="side"><div class="side-card"><p class="side-eyebrow">For hiring managers</p><h2>Start a bookkeeper search</h2>
<ul><li>Blinded shortlist in 48 to 72 hours</li><li>A screening questionnaire built with you</li><li>Temp, Contract, Temp-to-Hire, Direct Hire, or Payrolling</li></ul>
{cta_button()}<p class="side-phone">Prefer to talk? <a href="tel:+14042500790">{PHONES[0]}</a></p></div></aside>"""


def cta_band(page: dict) -> str:
    if page.get("cta_url"):
        return ""
    return f"""    <section class="cta-band">
      <div class="wrap cta-inner">
        <div><p class="eyebrow eyebrow-dark"><span class="dot"></span>Ready to hire?</p><h2>Tell us about your bookkeeping job</h2><p>Send it through the Get Started form. Staff Financial Group follows up, builds a screening questionnaire with you, and sends a blinded shortlist in 48 to 72 hours.</p></div>
        {cta_button(extra=' btn-lg btn-light')}
      </div>
    </section>"""


# ---------- schema ----------

def schema_for(page: dict, pages: list[dict]) -> list[dict]:
    url = SITE_URL + page["path"]
    graph: list[dict] = [ORG]
    web = {"@type": "CollectionPage" if page["kind"] in ("hub", "local") else "WebPage", "@id": f"{url}#webpage",
           "url": url, "name": page["title"], "description": page["description"],
           "isPartOf": {"@id": f"{SITE_URL}/#website"}, "about": {"@id": f"{SITE_URL}/#org"}, "inLanguage": "en-US",
           "primaryImageOfPage": f"{SITE_URL}/images/{page['og_image']}", "dateModified": page["date"].isoformat()}
    if page["path"] == "/":
        graph.append({"@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/", "name": SITE_NAME,
                      "publisher": {"@id": f"{SITE_URL}/#org"}, "inLanguage": "en-US"})
    else:
        web["breadcrumb"] = {"@id": f"{url}#breadcrumb"}
        graph.append({"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": SITE_URL + h} for i, (h, n) in enumerate(crumb_trail(page), 1)]})
    part_kind = {ROLES_HUB: "role", IND_HUB: "industry", ATLANTA: "area"}.get(page["path"])
    if part_kind:
        parts = of_kind(pages, part_kind) + (of_kind(pages, "city") if part_kind == "area" else [])
        web["hasPart"] = [{"@type": "Article", "headline": p["h1"], "url": SITE_URL + p["path"]} for p in parts]
    graph.append(web)
    if page["kind"] in ARTICLE_KINDS:
        graph.append({"@type": "Article", "@id": f"{url}#article", "headline": page["h1"], "description": page["description"],
                      "datePublished": page["date"].isoformat(), "dateModified": page["date"].isoformat(),
                      "image": f"{SITE_URL}/images/{page['og_image']}", "author": {"@id": f"{SITE_URL}/#org"},
                      "publisher": {"@id": f"{SITE_URL}/#org"}, "mainEntityOfPage": {"@id": f"{url}#webpage"},
                      "inLanguage": "en-US"})
    if page["kind"] == "city":
        graph.append({"@type": "Service", "@id": f"{url}#service", "name": page["h1"], "serviceType": page["service_type"],
                      "description": page["description"], "provider": {"@id": f"{SITE_URL}/#org"}, "url": url,
                      "areaServed": [{"@type": "City", "name": f"{page['city']}, Georgia"},
                                     {"@type": "AdministrativeArea", "name": f"{page['county']}, Georgia"}],
                      "audience": {"@type": "BusinessAudience", "audienceType": "Employers hiring bookkeepers"},
                      "hasOfferCatalog": {"@type": "OfferCatalog", "name": "Ways to hire", "itemListElement": [
                          {"@type": "Offer", "itemOffered": {"@type": "Service", "name": n}}
                          for n in ("Temp and Contract", "Temp-to-Hire", "Direct Hire", "Payrolling")]}})
    elif page.get("service_type"):
        graph.append({"@type": "Service", "@id": f"{url}#service", "name": page["h1"], "serviceType": page["service_type"],
                      "description": page["description"], "provider": {"@id": f"{SITE_URL}/#org"}, "url": url,
                      "areaServed": page.get("area_served") and [{"@type": "Place", "name": a} for a in split_list(page["area_served"])] or ORG["areaServed"]})
    if page["faqs"]:
        graph.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in page["faqs"]]})
    return graph


# ---------- checks and output ----------

def check_copy(path: str, page_html: str) -> list[str]:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    meta = html.unescape(" ".join(re.findall(r'content="([^"]*)"', page_html)))
    problems = []
    for pattern, why in BANNED:
        for m in re.finditer(pattern, text + " " + meta, flags=re.I):
            ctx = (text + " " + meta)[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
            problems.append(f"{path}: {why}: ...{ctx}...")
    return problems


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_static() -> None:
    for src in STATIC_DIR.rglob("*"):
        if src.is_dir():
            continue
        dest = DIST_DIR / src.relative_to(STATIC_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".b64":
            dest.with_suffix("").write_bytes(base64.b64decode(src.read_text()))
        else:
            shutil.copy2(src, dest)


def llms_txt(pages: list[dict]) -> str:
    lines = [f"# {SITE_NAME}", "",
             "> GetBookkeepers (getbookkeepers.com) helps businesses hire bookkeepers through Temp, Contract, Temp-to-Hire, "
             "Direct Hire, and Payrolling. It is a service of Staff Financial Group, a finance and accounting recruiting and "
             "staffing firm in metro Atlanta, GA, since 2005, powered by NorthPoint Search Group.", "",
             "## Key facts",
             f"- Start a search: Get Started form at {GET_STARTED_URL}",
             f"- Phone: {PHONES[0]} or {PHONES[1]}",
             "- Shortlist timing: a blinded shortlist 48 to 72 hours after the hiring request",
             "- Screening: a questionnaire built with the employer for each job; answers come with every resume",
             "- Video intros: every candidate is invited to record an optional video intro",
             "- Direct Hire placements carry Staff Financial Group's replacement guarantee",
             "- Temp, Contract, and Payrolling: Staff Financial Group is the Employer of Record (weekly payroll, tax withholdings, workers comp, W-2) and sends one invoice",
             f"- Salary data: Staff Financial Group 2026 Salary Guide, {SALARY_GUIDE_URL}",
             f"- Main site: {SF_URL}", f"- Bookkeeping job seekers: 100X Jobs at {JOBS_URL}"]
    sections = [("Ways to hire", "service"), ("Role guides", "role"), ("Industry guides", "industry"),
                ("Metro Atlanta", "local"), ("Metro Atlanta areas", "area"), ("Metro Atlanta cities", "city")]
    listed = set()
    for title, kind in sections:
        lines += ["", f"## {title}"]
        for p in of_kind(pages, kind):
            lines.append(f"- [{p['h1']}]({SITE_URL}{p['path']}): {p['description']}")
            listed.add(p["path"])
    lines += ["", "## Other pages"]
    for p in sorted(pages, key=lambda p: p["path"]):
        if p["path"] not in listed:
            lines.append(f"- [{p['h1']}]({SITE_URL}{p['path']}): {p['description']}")
    return "\n".join(lines) + "\n"


def build() -> int:
    pages = load_pages()
    by_path = {p["path"]: p for p in pages}
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir()
    copy_static()
    problems: list[str] = []
    for page in pages:
        body_html = md(page["body"])
        content = (ticker_html(page) + "\n" + hero(page) + "\n" + profiles_html(page)
                   + f'\n    <div class="wrap content-grid"><article class="prose">{body_html}{faq_html(page["faqs"])}</article>{aside_html(page)}</div>\n'
                   + f'    <div class="wrap">{related_html(page, pages, by_path)}</div>\n' + cta_band(page))
        scripts = '\n  <script src="/js/profiles.js" defer></script>' if profiles_html(page) else ""
        if ticker_html(page):
            scripts += '\n  <script src="/js/ticker.js" defer></script>'
        out = page_shell(page, content, schema_for(page, pages), pages, scripts)
        problems += check_copy(page["path"], out)
        write(DIST_DIR / page["path"].lstrip("/") / "index.html", out)
    if problems:
        raise SystemExit("Copy rule violations:\n" + "\n".join(problems))
    nf = {"path": "/404/", "title": "Page not found | GetBookkeepers", "description": "This page does not exist.",
          "og_image": "og-default.png", "kind": "page"}
    write(DIST_DIR / "404.html", page_shell(
        nf, '<section class="hero"><div class="wrap"><h1>Page not found</h1><p class="lede">Try the <a href="/">home page</a> or the <a href="/faq/">FAQ</a>.</p></div></section>',
        [ORG], pages).replace('content="index, follow"', 'content="noindex"').replace(f'  <link rel="canonical" href="{SITE_URL}/404/">\n', ""))
    write(DIST_DIR / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    write(DIST_DIR / "llms.txt", llms_txt(pages))
    urls = "\n".join(f"  <url><loc>{SITE_URL}{p['path']}</loc><lastmod>{p['date'].isoformat()}</lastmod></url>"
                     for p in sorted(pages, key=lambda p: (p["path"] != "/", p["path"])))
    write(DIST_DIR / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{urls}\n</urlset>\n")
    print(f"Built {len(pages)} pages into {DIST_DIR}")
    for p in sorted(pages, key=lambda p: p["path"]):
        print(f"  {p['path']:46} {p['title']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build())
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
