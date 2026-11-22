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
PHONES = ("404-250-0790", "678-777-5627")
JOBS_URL = "https://100xjobs.com/"
# Google Analytics 4 measurement ID for getbookkeepers.com. Empty until a property exists.
GA_ID = ""
FAQ_HEADING = "## Frequently asked questions"
NAV = [
    ("/temp-contract-bookkeepers/", "Temp and Contract"),
    ("/temp-to-hire-bookkeepers/", "Temp-to-Hire"),
    ("/direct-hire-bookkeepers/", "Direct Hire"),
    ("/payrolling/", "Payrolling"),
    ("/roles/", "Roles"),
    ("/faq/", "FAQ"),
]
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


def load_pages() -> list[dict]:
    pages, paths, titles, descs = [], set(), set(), set()
    required = ("title", "description", "h1", "lede", "path", "kicker", "image", "crumb", "kind", "date")
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
        if not (STATIC_DIR / "images" / meta["image"]).is_file():
            raise SystemExit(f"{src.name}: image {meta['image']} not found")
        main, faqs = split_faq(body, src.name)
        pages.append({**meta, "body": main, "faqs": faqs, "date": dt.date.fromisoformat(meta["date"]),
                      "related": [p.strip() for p in meta.get("related", "").split(",") if p.strip()],
                      "og_image": f"og-{Path(meta['image']).stem}.png"})
    return pages


def md(text: str) -> str:
    return markdown.markdown(text, extensions=["extra", "sane_lists"])


def cta_button(label: str = "Get Started", url: str = GET_STARTED_URL, extra: str = "") -> str:
    return f'<a class="btn btn-cta{extra}" href="{html.escape(url)}" data-cta="get-started">{html.escape(label)}</a>'


def ga_snippet() -> str:
    if not GA_ID:
        return ""
    return f"""
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');
  document.addEventListener('click',function(e){{var a=e.target.closest('[data-cta]');if(a){{gtag('event','generate_lead',{{cta:a.dataset.cta,page:location.pathname}});}}}});</script>"""


def page_shell(page: dict, content: str, schema: list[dict]) -> str:
    url = SITE_URL + page["path"]
    t, d = html.escape(page["title"]), html.escape(page["description"])
    og_img = f"{SITE_URL}/images/{page['og_image']}"
    nav = "".join(
        f'<a href="{h}"{" aria-current=\"page\"" if page["path"].startswith(h) else ""}>{l}</a>' for h, l in NAV
    )
    ld = json.dumps({"@context": "https://schema.org", "@graph": schema}, ensure_ascii=False, indent=1)
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
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.png" type="image/png" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:type" content="website">
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
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700&display=swap">
  <link rel="stylesheet" href="/css/styles.css">
  <script type="application/ld+json">
{ld}
  </script>{ga_snippet()}
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="wrap header-inner">
      <a class="brand" href="/" aria-label="GetBookkeepers home"><img src="/favicon.svg" alt="" width="36" height="36"><span class="wordmark">Get<span>Bookkeepers</span></span></a>
      <nav class="nav" aria-label="Main">{nav}</nav>
      {cta_button(extra=" btn-sm header-cta")}
    </div>
  </header>
  <main id="main">
{content}
  </main>
  <footer class="site-footer">
    <div class="wrap footer-grid">
      <div>
        <a class="brand brand-footer" href="/"><img src="/favicon.svg" alt="" width="32" height="32"><span class="wordmark">Get<span>Bookkeepers</span></span></a>
        <p>GetBookkeepers is a service of <a href="{SF_URL}">Staff Financial Group</a>, a finance and accounting recruiting and staffing firm in metro Atlanta since 2005, powered by NorthPoint Search Group.</p>
      </div>
      <div>
        <h2 class="footer-h">Hire</h2>
        <ul>{''.join(f'<li><a href="{h}">{l}</a></li>' for h, l in NAV[:5])}<li><a href="/atlanta/">Atlanta bookkeepers</a></li></ul>
      </div>
      <div>
        <h2 class="footer-h">Staff Financial Group</h2>
        <ul>
          <li><a href="tel:+14042500790">{PHONES[0]}</a></li>
          <li><a href="tel:+16787775627">{PHONES[1]}</a></li>
          <li><a href="https://www.stafffinancial.com/temps.html">Browse available temps</a></li>
          <li><a href="https://www.stafffinancial.com/salary-guide.html">2026 Salary Guide</a></li>
          <li><a href="/job-seekers/">Bookkeeping jobs</a></li>
        </ul>
      </div>
    </div>
    <div class="wrap footer-base">Atlanta, GA &middot; &copy; {dt.date.today().year} Staff Financial Group. All rights reserved.</div>
  </footer>
</body>
</html>
"""


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
        <div>
          {crumbs}
          <p class="kicker">{html.escape(page['kicker'])}</p>
          <h1>{html.escape(page['h1'])}</h1>
          <p class="lede">{html.escape(page['lede'])}</p>
          <div class="hero-actions">{cta_button(cta_label, cta_url, ' btn-lg')}<span class="hero-note">{html.escape(page.get('cta_note', 'Tell us about the job. A blinded shortlist comes back in 48 to 72 hours.'))}</span></div>
        </div>
        <figure class="hero-art"><img src="/images/{page['image']}" alt="{html.escape(page['image_alt'] if page.get('image_alt') else page['h1'])}" width="800" height="520"></figure>
      </div>
    </section>"""


def crumb_trail(page: dict) -> list[tuple[str, str]]:
    trail = [("/", "Home")]
    if page["path"].startswith("/roles/") and page["path"] != "/roles/":
        trail.append(("/roles/", "Bookkeeper roles"))
    if page["path"] != "/":
        trail.append((page["path"], page["crumb"]))
    return trail


def faq_html(faqs: list[tuple[str, str]]) -> str:
    if not faqs:
        return ""
    items = "".join(f"<details><summary>{html.escape(q)}</summary>{md(a)}</details>" for q, a in faqs)
    return f'<section class="faq" aria-labelledby="faq-h"><h2 id="faq-h">Frequently asked questions</h2>{items}</section>'


def related_html(page: dict, by_path: dict[str, dict]) -> str:
    if not page["related"]:
        return ""
    cards = []
    for p in page["related"]:
        if p not in by_path:
            raise SystemExit(f"{page['path']}: related page {p} does not exist")
        r = by_path[p]
        cards.append(f'<a class="card card-link" href="{p}"><span class="card-kicker">{html.escape(r["kicker"])}</span>'
                     f'<strong>{html.escape(r["crumb"])}</strong><span>{html.escape(r["description"])}</span></a>')
    return f'<section class="related" aria-labelledby="rel-h"><h2 id="rel-h">{html.escape(page.get("related_heading", "Related"))}</h2><div class="cards">{"".join(cards)}</div></section>'


def aside_html(page: dict) -> str:
    if page.get("cta_url"):
        return f"""<aside class="side"><div class="side-card"><h2>Find your next job</h2>
<p>{html.escape(page.get('cta_note', ''))}</p>{cta_button(page['cta_label'], page['cta_url'])}</div></aside>"""
    return f"""<aside class="side"><div class="side-card"><h2>Start a bookkeeper search</h2>
<ul><li>Blinded shortlist in 48 to 72 hours</li><li>A screening questionnaire built with you</li><li>Temp, Contract, Temp-to-Hire, Direct Hire, or Payrolling</li></ul>
{cta_button()}<p class="side-phone">Prefer to talk? <a href="tel:+14042500790">{PHONES[0]}</a></p></div></aside>"""


def cta_band(page: dict) -> str:
    if page.get("cta_url"):
        return ""
    return f"""    <section class="cta-band">
      <div class="wrap cta-inner">
        <div><h2>Ready to hire a bookkeeper?</h2><p>Send the job through the Get Started form. Staff Financial Group follows up, builds a screening questionnaire with you, and sends a blinded shortlist in 48 to 72 hours.</p></div>
        {cta_button(extra=' btn-lg btn-light')}
      </div>
    </section>"""


def schema_for(page: dict) -> list[dict]:
    url = SITE_URL + page["path"]
    graph: list[dict] = [ORG]
    web = {"@type": "WebPage", "@id": f"{url}#webpage", "url": url, "name": page["title"], "description": page["description"],
           "isPartOf": {"@id": f"{SITE_URL}/#website"}, "about": {"@id": f"{SITE_URL}/#org"}, "inLanguage": "en-US",
           "primaryImageOfPage": f"{SITE_URL}/images/{page['og_image']}", "dateModified": page["date"].isoformat()}
    if page["path"] == "/":
        graph.append({"@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/", "name": SITE_NAME,
                      "publisher": {"@id": f"{SITE_URL}/#org"}, "inLanguage": "en-US"})
    else:
        web["breadcrumb"] = {"@id": f"{url}#breadcrumb"}
        graph.append({"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": SITE_URL + h} for i, (h, n) in enumerate(crumb_trail(page), 1)]})
    graph.append(web)
    if page.get("service_type"):
        graph.append({"@type": "Service", "@id": f"{url}#service", "name": page["h1"], "serviceType": page["service_type"],
                      "description": page["description"], "provider": {"@id": f"{SITE_URL}/#org"}, "url": url,
                      "areaServed": ORG["areaServed"]})
    if page["faqs"]:
        graph.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in page["faqs"]]})
    return graph


def check_copy(path: str, page_html: str) -> list[str]:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    meta = " ".join(re.findall(r'content="([^"]*)"', page_html))
    problems = []
    for pattern, why in BANNED:
        for m in re.finditer(pattern, text + " " + html.unescape(meta), flags=re.I):
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
             "- Temp, Contract, and Payrolling: Staff Financial Group is the Employer of Record (weekly payroll, taxes, workers comp, W-2) and sends one invoice at the agreed bill rate",
             f"- Main site: {SF_URL}", f"- Bookkeeping job seekers: 100X Jobs at {JOBS_URL}", "", "## Pages"]
    for p in pages:
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
        content = (hero(page) + f'\n    <div class="wrap content-grid"><article class="prose">{body_html}{faq_html(page["faqs"])}</article>{aside_html(page)}</div>\n'
                   + f'    <div class="wrap">{related_html(page, by_path)}</div>\n' + cta_band(page))
        out = page_shell(page, content, schema_for(page))
        problems += check_copy(page["path"], out)
        if "PLACEHOLDER" in out:
            print(f"  note: {page['path']} still has a labeled PLACEHOLDER for Gus to fill")
        write(DIST_DIR / page["path"].lstrip("/") / "index.html", out)
    if problems:
        raise SystemExit("Copy rule violations:\n" + "\n".join(problems))
    write(DIST_DIR / "404.html", page_shell(
        {"path": "/404/", "title": "Page not found | GetBookkeepers", "description": "This page does not exist.",
         "og_image": "og-default.png"},
        '<section class="hero"><div class="wrap"><h1>Page not found</h1><p class="lede">Try the <a href="/">home page</a> or the <a href="/faq/">FAQ</a>.</p></div></section>',
        [ORG]).replace('content="index, follow"', 'content="noindex"').replace(f'<link rel="canonical" href="{SITE_URL}/404/">\n', ""))
    write(DIST_DIR / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    write(DIST_DIR / "llms.txt", llms_txt(pages))
    urls = "\n".join(f"  <url><loc>{SITE_URL}{p['path']}</loc><lastmod>{p['date'].isoformat()}</lastmod></url>"
                     for p in sorted(pages, key=lambda p: (p["path"] != "/", p["path"])))
    write(DIST_DIR / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{urls}\n</urlset>\n")
    print(f"Built {len(pages)} pages into {DIST_DIR}")
    for p in sorted(pages, key=lambda p: p["path"]):
        print(f"  {p['path']:38} {p['title']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build())
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
