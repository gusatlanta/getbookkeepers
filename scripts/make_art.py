#!/usr/bin/env python3
"""Generate the site's branded art: logo, favicons, page illustrations (SVG), and OG images (PNG as .b64).

Run after adding a page or changing an h1:  python scripts/make_art.py
Needs Pillow (dev only; the site build itself does not).
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "static" / "images"
STATIC = ROOT / "static"
PAGES = ROOT / "pages"

NAVY = "#0b1f3d"
NAVY_MID = "#12325a"
GREEN = "#0e8a5f"
GREEN_LT = "#e8f6ef"
GREEN_MID = "#7fcfab"
TEAL = "#2a9cc0"
PAPER = "#ffffff"
LINE = "#d7e3ea"

FONT_DIR = Path("/usr/share/fonts/truetype/sand-box/google")
OUTFIT = FONT_DIR / "Outfit" / "Outfit-VariableFont_wght.ttf"
INTER = FONT_DIR / "Inter" / "Inter-VariableFont_opsz,wght.ttf"


def font(path: Path, size: int, weight: str) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(path), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


MARK = (
    '<rect x="0" y="0" width="64" height="64" rx="14" fill="{g}"/>'
    '<rect x="14" y="16" width="36" height="5" rx="2.5" fill="#fff" opacity=".55"/>'
    '<rect x="14" y="29" width="22" height="5" rx="2.5" fill="#fff" opacity=".55"/>'
    '<path d="M30 44 l7 7 l14 -16" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'
).format(g=GREEN)


def write_svg(name: str, body: str, w: int, h: int) -> None:
    (IMG / name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">{body}</svg>\n'
    )


def logo() -> None:
    body = (
        f"<title>GetBookkeepers</title>{MARK}"
        f'<text x="78" y="44" font-family="Outfit, Inter, Arial, sans-serif" font-size="34" font-weight="700" fill="{NAVY}">Get<tspan fill="{GREEN}">Bookkeepers</tspan></text>'
    )
    write_svg("logo.svg", body, 330, 64)
    (STATIC / "favicon.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{MARK}</svg>\n'
    )


def mark_png(size: int) -> Image.Image:
    s = 8
    im = Image.new("RGBA", (64 * s, 64 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, 64 * s - 1, 64 * s - 1], radius=14 * s, fill=GREEN)
    light = (255, 255, 255, 140)
    d.rounded_rectangle([14 * s, 16 * s, 50 * s, 21 * s], radius=int(2.5 * s), fill=light)
    d.rounded_rectangle([14 * s, 29 * s, 36 * s, 34 * s], radius=int(2.5 * s), fill=light)
    d.line([(30 * s, 44 * s), (37 * s, 51 * s), (51 * s, 35 * s)], fill="white", width=6 * s, joint="curve")
    for x, y in [(30, 44), (51, 35)]:
        d.ellipse([(x - 3) * s, (y - 3) * s, (x + 3) * s, (y + 3) * s], fill="white")
    return im.resize((size, size), Image.LANCZOS)


def save_b64(im: Image.Image, dest: Path) -> None:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    dest.write_text(base64.b64encode(buf.getvalue()).decode())


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def og(dest: Path, headline: str, kicker: str) -> None:
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    # ledger grid motif on the right
    for i in range(9):
        y = 120 + i * 48
        d.rounded_rectangle([780, y, 1120, y + 26], radius=8, fill=NAVY_MID)
        d.rounded_rectangle([780, y, 780 + 60 + (i * 37) % 200, y + 26], radius=8, fill=GREEN if i % 3 == 0 else "#1d4a7a")
    d.rectangle([0, H - 14, W, H], fill=GREEN)
    m = mark_png(72)
    im.paste(m, (80, 70), m)
    d.text((168, 82), "Get", font=font(OUTFIT, 40, "Bold"), fill="white")
    gx = 168 + d.textlength("Get", font=font(OUTFIT, 40, "Bold"))
    d.text((gx, 82), "Bookkeepers", font=font(OUTFIT, 40, "Bold"), fill=GREEN_MID)
    d.text((80, 200), kicker.upper(), font=font(INTER, 24, "SemiBold"), fill=GREEN_MID)
    hf = font(OUTFIT, 60, "Bold")
    y = 245
    for line in wrap(d, headline, hf, 650)[:4]:
        d.text((80, y), line, font=hf, fill="white")
        y += 72
    d.text((80, 540), "A Staff Financial Group service  |  getbookkeepers.com", font=font(INTER, 24, "Medium"), fill="#b8c7d9")
    save_b64(im, dest)


# ---------- page illustrations (SVG) ----------

def frame(inner: str, title: str) -> str:
    return (
        f"<title>{title}</title>"
        f'<rect width="800" height="520" rx="28" fill="{GREEN_LT}"/>'
        f'<circle cx="690" cy="90" r="120" fill="{GREEN_MID}" opacity=".25"/>'
        f'<circle cx="90" cy="470" r="90" fill="{TEAL}" opacity=".12"/>'
        + inner
    )


def ledger(x=170, y=90, rows=7, checks=(1, 3, 5)) -> str:
    out = [f'<rect x="{x}" y="{y}" width="460" height="340" rx="18" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/>',
           f'<rect x="{x}" y="{y}" width="460" height="56" rx="18" fill="{NAVY}"/><rect x="{x}" y="{y+38}" width="460" height="18" fill="{NAVY}"/>',
           f'<rect x="{x+24}" y="{y+20}" width="150" height="14" rx="7" fill="#fff" opacity=".8"/>']
    for i in range(rows):
        ry = y + 80 + i * 36
        out.append(f'<rect x="{x+24}" y="{ry}" width="{180 + (i*53)%90}" height="12" rx="6" fill="{LINE}"/>')
        out.append(f'<rect x="{x+330}" y="{ry}" width="70" height="12" rx="6" fill="{"#b9dfcc" if i in checks else LINE}"/>')
        if i in checks:
            out.append(f'<path d="M{x+414} {ry+6} l6 6 l12 -12" fill="none" stroke="{GREEN}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(out)


def calendar(x, y, w=230, marked=(3, 4, 5, 10, 11, 12)) -> str:
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{w}" rx="18" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/>',
           f'<rect x="{x}" y="{y}" width="{w}" height="46" rx="18" fill="{GREEN}"/><rect x="{x}" y="{y+30}" width="{w}" height="16" fill="{GREEN}"/>']
    cell = (w - 30) / 5
    for i in range(20):
        cx = x + 15 + (i % 5) * cell
        cy = y + 60 + (i // 5) * cell * 0.85
        fill = GREEN if i in marked else LINE
        out.append(f'<rect x="{cx+4:.0f}" y="{cy:.0f}" width="{cell-8:.0f}" height="{cell*0.6:.0f}" rx="6" fill="{fill}" opacity="{1 if i in marked else .7}"/>')
    return "".join(out)


def person(cx, cy, color=NAVY, scale=1.0) -> str:
    r = 26 * scale
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
            f'<path d="M{cx-48*scale} {cy+92*scale} q0 -54 {48*scale} -54 q{48*scale} 0 {48*scale} 54 z" fill="{color}"/>')


def arrow(x1, y, x2, color=GREEN) -> str:
    return (f'<line x1="{x1}" y1="{y}" x2="{x2-14}" y2="{y}" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="2 14"/>'
            f'<path d="M{x2-18} {y-12} l14 12 l-14 12" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')


def badge(cx, cy, text, color=GREEN) -> str:
    return (f'<rect x="{cx-80}" y="{cy-24}" width="160" height="48" rx="24" fill="{color}"/>'
            f'<text x="{cx}" y="{cy+8}" text-anchor="middle" font-family="Outfit, Inter, Arial, sans-serif" font-size="22" font-weight="700" fill="#fff">{text}</text>')


def stub(x, y) -> str:
    out = [f'<rect x="{x}" y="{y}" width="300" height="190" rx="16" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/>',
           f'<rect x="{x+20}" y="{y+22}" width="120" height="14" rx="7" fill="{NAVY}"/>',
           f'<text x="{x+280}" y="{y+40}" text-anchor="end" font-family="Outfit, Inter, Arial" font-size="22" font-weight="700" fill="{GREEN}">W-2</text>']
    for i in range(4):
        out.append(f'<rect x="{x+20}" y="{y+62+i*28}" width="{150-(i*23)%60}" height="10" rx="5" fill="{LINE}"/>'
                   f'<rect x="{x+210}" y="{y+62+i*28}" width="70" height="10" rx="5" fill="{"#b9dfcc" if i==3 else LINE}"/>')
    return "".join(out)


def illustrations() -> dict[str, str]:
    a = {}
    a["home"] = frame(ledger() + person(118, 210, NAVY) + badge(630, 450, "Hired"), "A bookkeeping ledger with reviewed lines and a new hire")
    a["temp-contract"] = frame(calendar(120, 130) + arrow(380, 245, 470) + ledger(470, 120, 5, (0, 2, 4)).replace('width="460"', 'width="230"').replace(f'x="{470+330}"', 'x="620"'), "A calendar of covered weeks next to a ledger")
    a["direct-hire"] = frame(person(300, 190, NAVY, 1.4) + person(500, 190, GREEN, 1.4) + badge(400, 420, "Direct Hire", NAVY), "Two people representing an employer and a Direct Hire bookkeeper")
    a["temp-to-hire"] = frame(calendar(110, 140, 210, (0, 1, 2, 3, 4, 5, 6, 7)) + arrow(345, 245, 450) + person(560, 190, GREEN, 1.3) + badge(560, 420, "Converted"), "Weeks of a trial period followed by a conversion to employee")
    a["payrolling"] = frame(stub(120, 120) + stub(250, 230) + badge(640, 150, "One invoice", NAVY), "Pay stubs and W-2 forms handled by an employer of record")
    a["roles"] = frame(person(190, 180, NAVY) + person(330, 180, GREEN) + person(470, 180, TEAL) + person(610, 180, NAVY_MID) +
                       "".join(f'<rect x="{x-60}" y="330" width="120" height="16" rx="8" fill="{LINE}"/>' for x in (190, 330, 470, 610)), "Four bookkeeping and accounting roles side by side")
    a["ap-ar"] = frame(ledger(150, 90, 7, (0, 1, 2, 3)) + badge(650, 160, "Paid", GREEN) + badge(650, 380, "Collected", NAVY), "Payables and receivables lines being cleared")
    a["full-charge"] = frame(ledger(150, 90, 7, (0, 1, 2, 3, 4, 5, 6)) + badge(640, 450, "Closed", NAVY), "A fully reconciled ledger closed for the month")
    a["payroll-specialist"] = frame(stub(150, 110) + calendar(480, 150, 190, (4, 9, 14, 19)), "A pay stub and a payroll calendar")
    a["staff-accountant"] = frame(ledger(150, 90, 7, (2, 5)) + f'<rect x="560" y="300" width="160" height="150" rx="16" fill="{NAVY}"/>' +
                                  "".join(f'<rect x="{580+i*34}" y="{430-h}" width="22" height="{h}" rx="4" fill="{GREEN_MID}"/>' for i, h in enumerate((40, 70, 55, 100))), "A ledger and a small report chart")
    pins = "".join(f'<path d="M{x} {y} c-22 0 -36 -16 -36 -34 a36 36 0 0 1 72 0 c0 18 -14 34 -36 34 z" fill="{c}"/><circle cx="{x}" cy="{y-36}" r="12" fill="#fff"/>'
                   for x, y, c in ((400, 270, GREEN), (300, 190, NAVY), (520, 170, NAVY_MID), (250, 340, TEAL), (560, 360, NAVY)))
    roads = f'<path d="M120 420 C 300 300, 420 320, 680 120" stroke="{LINE}" stroke-width="18" fill="none" stroke-linecap="round"/><path d="M140 160 C 320 260, 480 260, 700 420" stroke="{LINE}" stroke-width="18" fill="none" stroke-linecap="round"/><circle cx="400" cy="270" r="170" fill="none" stroke="{GREEN}" stroke-width="4" stroke-dasharray="6 12" opacity=".6"/>'
    a["atlanta"] = frame(roads + pins, "Map pins around metro Atlanta")
    bubbles = (f'<rect x="150" y="110" width="340" height="120" rx="24" fill="{NAVY}"/><text x="320" y="190" text-anchor="middle" font-family="Outfit, Inter, Arial" font-size="72" font-weight="700" fill="#fff">?</text>'
               f'<rect x="310" y="270" width="340" height="140" rx="24" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/>'
               + "".join(f'<rect x="340" y="{300+i*30}" width="{260-i*50}" height="12" rx="6" fill="{GREEN if i==0 else LINE}"/>' for i in range(3)))
    a["faq"] = frame(bubbles, "A question and an answer")
    search = (f'<rect x="150" y="120" width="500" height="80" rx="40" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/>'
              f'<circle cx="200" cy="160" r="18" fill="none" stroke="{NAVY}" stroke-width="6"/><line x1="213" y1="173" x2="228" y2="188" stroke="{NAVY}" stroke-width="6" stroke-linecap="round"/>'
              f'<text x="250" y="170" font-family="Inter, Arial" font-size="26" fill="{NAVY}">bookkeeper jobs near me</text>'
              + "".join(f'<rect x="150" y="{240+i*70}" width="500" height="54" rx="14" fill="{PAPER}" stroke="{LINE}" stroke-width="2"/><rect x="175" y="{258+i*70}" width="{220-i*40}" height="16" rx="8" fill="{NAVY if i==0 else LINE}"/><rect x="560" y="{252+i*70}" width="70" height="28" rx="14" fill="{GREEN}"/>' for i in range(3)))
    a["job-seekers"] = frame(search, "A job search box with bookkeeper job results")
    return a


def h1_of(md: Path) -> tuple[str, str, str]:
    text = md.read_text()
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", text.split("---", 2)[1], re.M))
    return meta.get("og", meta["h1"]), meta.get("kicker", "Hire a bookkeeper"), meta["image"]


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    logo()
    save_b64(mark_png(32), STATIC / "favicon.png.b64")
    save_b64(mark_png(180), STATIC / "apple-touch-icon.png.b64")
    save_b64(mark_png(512), IMG / "logo-mark-512.png.b64")
    for name, body in illustrations().items():
        write_svg(f"{name}.svg", body, 800, 520)
    og(IMG / "og-default.png.b64", "Hire a bookkeeper who fits your books", "Temp, Contract, Temp-to-Hire, Direct Hire, Payrolling")
    for md in sorted(PAGES.rglob("*.md")):
        headline, kicker, image = h1_of(md)
        og(IMG / f"og-{Path(image).stem}.png.b64", headline, kicker)
    print("art written to", IMG)


if __name__ == "__main__":
    main()
