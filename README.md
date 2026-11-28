# GetBookkeepers

Static lead site for [getbookkeepers.com](https://www.getbookkeepers.com), a Staff Financial Group service that helps businesses hire bookkeepers (Temp, Contract, Temp-to-Hire, Direct Hire, Payrolling). Every "Get Started" button goes to the Staff Financial Group hiring form at https://www.stafffinancial.com/opt-in.html.

## Layout

- `pages/**/*.md`: one file per page. Front matter sets the title, description, h1, lede, path, image, and related links. A `## Frequently asked questions` section with `### Question` headings becomes FAQ markup and FAQPage schema.
- `static/`: CSS, SVG art, and binary images stored as `.b64` (decoded at build time).
- `build.py`: renders `dist/` with canonical URLs, OG/Twitter tags, JSON-LD (Organization/ProfessionalService, WebPage, BreadcrumbList, Service, FAQPage), `robots.txt`, `sitemap.xml`, `llms.txt`, and `404.html`. It fails if the copy breaks a rule (dashes, "permanent", "project", "free", and so on).
- `scripts/make_art.py`: regenerates the logo, favicons, page illustrations, and per-page OG images (needs Pillow). Run it after adding a page.
- `scripts/check.py`: link crawl, one H1 per page, unique titles and descriptions, JSON-LD parsing, canonicals, orphan pages, internal-link rules by page kind (cities link to their area, nearby cities, services, and the Atlanta hub), description length, the job seeker CTA, and the pricing guard. Add `--external` to check outside links and the live 100X profile feed.
- `static/js/profiles.js` and `static/js/ticker.js`: the blinded profile carousel and the auto-scrolling profile strip, both loaded live from the public 100X candidate feed and hidden if fewer than 3 profiles load.
- `render.yaml`: Render static site (build `pip install -r requirements.txt && python build.py`, publish `dist`) with getbookkeepers.com and www.getbookkeepers.com.

## Build and preview

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pillow
.venv/bin/python build.py
.venv/bin/python scripts/check.py --external
python3 -m http.server 8010 --directory dist
```

## Before launch

- No bill rates, fees, or pricing anywhere on the site (salary data from the 2026 Salary Guide is fine). `scripts/check.py` fails the build check if pricing appears.
- Set `GA_ID` in `build.py` to the GA4 measurement ID for getbookkeepers.com. Clicks on Get Started then send a `generate_lead` event.
