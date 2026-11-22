# GetBookkeepers

Static lead site for [getbookkeepers.com](https://www.getbookkeepers.com), a Staff Financial Group service that helps businesses hire bookkeepers (Temp, Contract, Temp-to-Hire, Direct Hire, Payrolling). Every "Get Started" button goes to the Staff Financial Group hiring form at https://www.stafffinancial.com/opt-in.html.

## Layout

- `pages/**/*.md`: one file per page. Front matter sets the title, description, h1, lede, path, image, and related links. A `## Frequently asked questions` section with `### Question` headings becomes FAQ markup and FAQPage schema.
- `static/`: CSS, SVG art, and binary images stored as `.b64` (decoded at build time).
- `build.py`: renders `dist/` with canonical URLs, OG/Twitter tags, JSON-LD (Organization/ProfessionalService, WebPage, BreadcrumbList, Service, FAQPage), `robots.txt`, `sitemap.xml`, `llms.txt`, and `404.html`. It fails if the copy breaks a rule (dashes, "permanent", "project", "free", and so on).
- `scripts/make_art.py`: regenerates the logo, favicons, page illustrations, and per-page OG images (needs Pillow). Run it after adding a page.
- `scripts/check.py`: link crawl, one H1 per page, unique titles and descriptions, JSON-LD parsing, canonicals. Add `--external` to check outside links.

## Build and preview

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pillow
.venv/bin/python build.py
.venv/bin/python scripts/check.py --external
python3 -m http.server 8010 --directory dist
```

## Before launch

- Replace the PLACEHOLDER on the home page with real bookkeeper bill rates and the Direct Hire fee.
- Set `GA_ID` in `build.py` to the GA4 measurement ID for getbookkeepers.com. Clicks on Get Started then send a `generate_lead` event.
