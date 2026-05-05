"""
Styled numerology map generator using Playwright → PNG/PDF.
Produces a beautiful designed map matching the women/men PDF style.
"""
from __future__ import annotations

import asyncio
import base64
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).parent
IMAGE_DIR = SCRIPT_DIR / "image"
FONT_PATH = IMAGE_DIR / "fonts" / "Heebo-VariableFont_wght.ttf"


def _s(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val)


def _font_base64() -> str:
    """Embed Heebo font as base64 for offline rendering."""
    if FONT_PATH.exists():
        return base64.b64encode(FONT_PATH.read_bytes()).decode()
    return ""


def _hidden_year_display(shana_nisteret: Any, destiny: Any) -> str:
    s = _s(shana_nisteret)
    if not s:
        return ""
    if "_" in s:
        parts = s.split("_")
        return f"{parts[1]}/{destiny}" if len(parts) > 1 else s.replace("_", "/")
    return s.replace("_", "/")


def _age_range(start: Any, end_excl: Any) -> str:
    s, e = _s(start), _s(end_excl)
    if not s or not e:
        return ""
    try:
        return f"{int(s)} – {int(e) - 1}"
    except ValueError:
        return f"{s} – {e}"


def _build_pytha_table(day: int, month: int, year: int) -> str:
    """Build the 3×3 Pythagorean square HTML."""
    bd = f"{day:02d}{month:02d}{year}"
    counts: dict[int, int] = {}
    if len(bd) == 8 and bd.isdigit():
        for c in bd:
            d = int(c)
            if d != 0:
                counts[d] = counts.get(d, 0) + 1

    def cell(n: int) -> str:
        v = _s(counts.get(n, ""))
        val = str(n) * counts[n] if n in counts else ""
        return f'<td class="pytha-cell">{val}</td>'

    rows = [
        [7, 8, 9],
        [4, 5, 6],
        [1, 2, 3],
    ]
    html_rows = ""
    for row in rows:
        html_rows += "<tr>" + "".join(cell(n) for n in row) + "</tr>"
    return html_rows


def _get_interp(calc: Any, category: str, number: Any, gender_key: str, max_chars: int = 400) -> str:
    """Safely retrieve interpretation text, truncated to max_chars."""
    try:
        text = calc.get_interpretation(category, str(number), gender_key)
        if not text:
            return ""
        text = text.strip()
        if len(text) > max_chars:
            text = text[:max_chars].rsplit("\n", 1)[0] + "…"
        return text
    except Exception:
        return ""


def _br(text: str) -> str:
    """Convert newlines to HTML <br> tags and escape HTML."""
    import html as _html
    escaped = _html.escape(str(text))
    return escaped.replace("\n", "<br>")


def _build_interp_html(
    destiny: str,
    birth_day_val: str,
    personal_year_val: str,
    interp_destiny: str,
    interp_birth_day: str,
    interp_personal_year: str,
    interp_peak1: str,
    peak1_val: Any,
    accent: str,
    accent_light: str,
    frame_color: str,
) -> str:
    parts = []

    if interp_destiny:
        parts.append(
            f'<div class="section-title" style="color:{frame_color}">✧ ייעוד · מספר {destiny}</div>'
            f'<div class="interp-box" style="background:{accent_light};border:1px solid {frame_color}44;'
            f'border-radius:10px;padding:12px 14px;font-size:11px;line-height:1.8;'
            f'color:#2d1b4e;margin-bottom:8px;white-space:pre-wrap">'
            f'{_br(interp_destiny)}</div>'
        )

    if interp_birth_day or interp_personal_year:
        grid_parts = []
        if interp_birth_day:
            grid_parts.append(
                f'<div style="flex:1;min-width:180px;background:{accent_light};border:1px solid {accent}33;'
                f'border-radius:10px;padding:10px 12px">'
                f'<div style="font-size:10px;font-weight:700;color:{frame_color};'
                f'margin-bottom:6px">יום לידה · {birth_day_val}</div>'
                f'<div style="font-size:10.5px;line-height:1.7;color:#2d1b4e;white-space:pre-wrap">'
                f'{_br(interp_birth_day)}</div></div>'
            )
        if interp_personal_year:
            grid_parts.append(
                f'<div style="flex:1;min-width:180px;background:{accent_light};border:1px solid {accent}33;'
                f'border-radius:10px;padding:10px 12px">'
                f'<div style="font-size:10px;font-weight:700;color:{frame_color};'
                f'margin-bottom:6px">שנה אישית · {personal_year_val}</div>'
                f'<div style="font-size:10.5px;line-height:1.7;color:#2d1b4e;white-space:pre-wrap">'
                f'{_br(interp_personal_year)}</div></div>'
            )
        parts.append(
            f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">'
            + "".join(grid_parts)
            + "</div>"
        )

    if interp_peak1:
        parts.append(
            f'<div style="background:{accent_light};border:1px solid {accent}33;'
            f'border-radius:10px;padding:10px 12px;margin-bottom:8px">'
            f'<div style="font-size:10px;font-weight:700;color:{frame_color};'
            f'margin-bottom:6px">פסגה ראשונה · {peak1_val}</div>'
            f'<div style="font-size:10.5px;line-height:1.7;color:#2d1b4e;white-space:pre-wrap">'
            f'{_br(interp_peak1)}</div></div>'
        )

    return "\n".join(parts)


def build_map_html(
    calc: Any,
    first_name: str,
    last_name: str,
    day: int,
    month: int,
    year: int,
    gender: str = "female",
    brand_name: str = "מראה לנשמה · Soul Vision",
    logo_text: str = "✧",
) -> str:
    """Build the full HTML for the styled numerology map."""
    is_female = gender.lower() in {"female", "women", "woman", "f", "נקבה"}
    gender_label = "נקבה" if is_female else "זכר"
    gender_key = "women" if is_female else "men"

    # Interpretations
    destiny = _s(getattr(calc, "final_number_destiny", ""))
    birth_day_val = _s(getattr(calc, "p_day", ""))
    personal_year_val = _s(getattr(calc, "shana_ishit", ""))

    interp_destiny = _get_interp(calc, "destiny", destiny, gender_key, max_chars=500)
    interp_birth_day = _get_interp(calc, "birth_day", birth_day_val, gender_key, max_chars=350)
    interp_personal_year = _get_interp(calc, "personal_year", personal_year_val, gender_key, max_chars=350)
    interp_peak1 = _get_interp(calc, "peaks", _s(getattr(calc, "peak1_reduced", "")), gender_key, max_chars=250)

    # Colors
    if is_female:
        bg_grad = "linear-gradient(160deg, #e8d5f5 0%, #d4a8e8 20%, #f0e6fa 50%, #fce4ec 80%, #f9f0ff 100%)"
        accent = "#9b59b6"
        accent_light = "rgba(155,89,182,0.15)"
        frame_color = "#c9a227"
        title_color = "#6a1b9a"
        number_color = "#7b1fa2"
        tag_bg = "rgba(155,89,182,0.12)"
    else:
        bg_grad = "linear-gradient(160deg, #b3cde8 0%, #cfe2f3 30%, #e8f4fd 60%, #fffde7 100%)"
        accent = "#1565c0"
        accent_light = "rgba(21,101,192,0.12)"
        frame_color = "#b8860b"
        title_color = "#0d3b6e"
        number_color = "#1a237e"
        tag_bg = "rgba(21,101,192,0.10)"

    font_b64 = _font_base64()
    font_face = f"""
    @font-face {{
        font-family: 'Heebo';
        src: url('data:font/truetype;base64,{font_b64}') format('truetype');
    }}""" if font_b64 else ""

    # Data
    full_date_short = _s(getattr(calc, "full_date_short", ""))
    personal_year = _s(getattr(calc, "shana_ishit", ""))
    hidden_year = _hidden_year_display(getattr(calc, "shana_nisteret", ""), destiny)
    p_day = _s(getattr(calc, "p_day", ""))
    p_month = _s(getattr(calc, "p_month", ""))
    p_year_r = _s(getattr(calc, "p_year", ""))
    first_name_val = _s(getattr(calc, "first_name_val", ""))
    full_name_val = _s(getattr(calc, "full_name_val", ""))
    itzurim_val = _s(getattr(calc, "itzurim_val", ""))
    aiv_val = _s(getattr(calc, "aiv_val", ""))
    age = _s(getattr(calc, "age", ""))
    tzimtzum_age = _s(getattr(calc, "tzimtzum_age", ""))

    peak1 = _s(getattr(calc, "peak1_reduced", ""))
    peak2 = _s(getattr(calc, "peak2_reduced", ""))
    peak3 = _s(getattr(calc, "peak3_reduced", ""))
    peak4 = _s(getattr(calc, "peak4_reduced", ""))
    ch1 = _s(getattr(calc, "challenge1_reduced", ""))
    ch2 = _s(getattr(calc, "challenge2_reduced", ""))
    ch3 = _s(getattr(calc, "challenge3_reduced", ""))
    ch4 = _s(getattr(calc, "challenge4_reduced", ""))

    fp = getattr(calc, "first_pick_start", 0) or 0
    sp = getattr(calc, "second_pick_start", 0) or 0
    tp = getattr(calc, "third_pick_start", 0) or 0
    fop = getattr(calc, "forth_pick_start", 0) or 0

    ar1 = f"{fp} – {sp - 1}" if sp else ""
    ar2 = f"{sp} – {tp - 1}" if tp else ""
    ar3 = f"{tp} – {fop - 1}" if fop else ""
    ar4 = f"{fop}+" if fop else ""

    q1 = _s(getattr(calc, "first_quarter_reduced", ""))
    q2 = _s(getattr(calc, "second_quarter_reduced", ""))
    q3 = _s(getattr(calc, "third_quarter_reduced", ""))
    q4 = _s(getattr(calc, "forth_quarter_reduced", ""))

    pytha_rows = _build_pytha_table(day, month, year)

    full_name = f"{first_name} {last_name}".strip()
    birthdate_str = f"{day:02d}/{month:02d}/{year}"

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>מפה נומרולוגית – {full_name}</title>
<style>
{font_face}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
    width: 794px;
    min-height: 1123px;
    font-family: 'Heebo', 'Arial', sans-serif;
    direction: rtl;
    text-align: right;
    background: {bg_grad};
    color: #2d1b4e;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}
.page {{
    width: 794px;
    min-height: 1123px;
    padding: 32px 36px;
    position: relative;
    overflow: hidden;
}}
/* Gold frame */
.page::before {{
    content: '';
    position: absolute;
    inset: 18px;
    border: 2.5px solid {frame_color};
    border-radius: 12px;
    pointer-events: none;
}}
/* Decorative corner ornaments */
.corner {{ position: absolute; font-size: 22px; color: {frame_color}; opacity: 0.7; }}
.corner.tl {{ top: 12px; right: 12px; }}
.corner.tr {{ top: 12px; left: 12px; transform: scaleX(-1); }}
.corner.bl {{ bottom: 12px; right: 12px; transform: scaleY(-1); }}
.corner.br {{ bottom: 12px; left: 12px; transform: scale(-1); }}

/* Header */
.header {{
    text-align: center;
    margin-bottom: 20px;
    padding-top: 8px;
}}
.brand {{
    font-size: 11px;
    letter-spacing: 3px;
    color: {frame_color};
    text-transform: uppercase;
    margin-bottom: 4px;
    opacity: 0.8;
}}
.title {{
    font-size: 30px;
    font-weight: 800;
    color: {title_color};
    line-height: 1.2;
}}
.title span {{ color: {frame_color}; }}
.subtitle {{
    font-size: 13px;
    color: {accent};
    margin-top: 4px;
    opacity: 0.85;
}}
.divider {{
    width: 80px;
    height: 2px;
    background: linear-gradient(90deg, transparent, {frame_color}, transparent);
    margin: 8px auto;
    border-radius: 2px;
}}
.client-info {{
    font-size: 16px;
    font-weight: 700;
    color: {title_color};
    text-align: center;
    margin-bottom: 4px;
}}
.client-date {{
    font-size: 12px;
    text-align: center;
    color: {accent};
    opacity: 0.8;
    margin-bottom: 16px;
}}

/* Sections */
.section-title {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {frame_color};
    text-transform: uppercase;
    margin: 14px 0 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, {frame_color}44, transparent);
}}

/* Core numbers grid */
.numbers-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 4px;
}}
.num-card {{
    background: {accent_light};
    border: 1px solid {frame_color}44;
    border-radius: 10px;
    padding: 10px 6px;
    text-align: center;
}}
.num-val {{
    font-size: 28px;
    font-weight: 800;
    color: {number_color};
    line-height: 1;
    margin-bottom: 3px;
}}
.num-val.large {{ font-size: 34px; }}
.num-label {{
    font-size: 9.5px;
    color: {accent};
    line-height: 1.3;
    font-weight: 600;
}}

/* Gematria */
.gem-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 4px;
}}
.gem-card {{
    background: {tag_bg};
    border: 1px solid {accent}33;
    border-radius: 8px;
    padding: 8px 6px;
    text-align: center;
}}
.gem-val {{
    font-size: 20px;
    font-weight: 800;
    color: {accent};
}}
.gem-label {{
    font-size: 9px;
    color: {accent};
    opacity: 0.75;
    margin-top: 2px;
}}

/* Periods table */
.periods-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 11px;
    margin-bottom: 4px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid {frame_color}44;
}}
.periods-table th {{
    background: {accent_light};
    color: {frame_color};
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 7px 10px;
    text-align: center;
    border-bottom: 1px solid {frame_color}44;
}}
.periods-table td {{
    padding: 6px 10px;
    text-align: center;
    border-bottom: 1px solid {accent}18;
    font-weight: 700;
    font-size: 14px;
    color: {number_color};
}}
.periods-table td.period-label {{
    font-size: 10px;
    font-weight: 600;
    color: {accent};
    text-align: right;
}}
.periods-table tr:last-child td {{ border-bottom: none; }}
.periods-table tr:nth-child(even) {{ background: {accent_light}; }}

/* Bottom grid: quarters + pytha */
.bottom-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 4px;
}}
.quarter-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}}
.q-card {{
    background: {accent_light};
    border: 1px solid {frame_color}44;
    border-radius: 8px;
    padding: 8px;
    text-align: center;
}}
.q-num {{ font-size: 22px; font-weight: 800; color: {accent}; }}
.q-label {{ font-size: 9px; color: {accent}; opacity: 0.7; }}

/* Pythagorean square */
.pytha-wrap {{
    background: {accent_light};
    border: 1px solid {frame_color}44;
    border-radius: 8px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}}
.pytha-table {{
    border-collapse: collapse;
    font-family: 'Heebo', Arial, sans-serif;
}}
.pytha-cell {{
    width: 46px;
    height: 38px;
    border: 1.5px solid {frame_color}55;
    text-align: center;
    font-size: 13px;
    font-weight: 700;
    color: {number_color};
    vertical-align: middle;
}}

/* Age + year code bar */
.info-bar {{
    display: flex;
    gap: 10px;
    background: {accent_light};
    border: 1px solid {frame_color}44;
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}}
.info-item {{
    flex: 1;
    text-align: center;
    min-width: 60px;
}}
.info-val {{ font-size: 16px; font-weight: 800; color: {number_color}; }}
.info-label {{ font-size: 9px; color: {accent}; opacity: 0.75; }}

/* Footer */
.footer {{
    position: absolute;
    bottom: 28px;
    left: 0; right: 0;
    text-align: center;
    font-size: 9px;
    color: {accent};
    opacity: 0.55;
    letter-spacing: 1px;
}}
</style>
</head>
<body>
<div class="page">
  <!-- Corner ornaments -->
  <div class="corner tl">✦</div>
  <div class="corner tr">✦</div>
  <div class="corner bl">✦</div>
  <div class="corner br">✦</div>

  <!-- Header -->
  <div class="header">
    <div class="brand">{brand_name}</div>
    <div class="title">מ<span>פ</span>ה נו<span>מ</span>רולוגית</div>
    <div class="divider"></div>
    <div class="client-info">{full_name} · {gender_label}</div>
    <div class="client-date">תאריך לידה: {birthdate_str} · {p_day}/{p_month}/{p_year_r}</div>
  </div>

  <!-- Core Numbers -->
  <div class="section-title">✧ מספרי ליבה</div>
  <div class="numbers-grid">
    <div class="num-card">
      <div class="num-val large">{destiny}</div>
      <div class="num-label">מספר ייעוד<br>(שביל גורל)</div>
    </div>
    <div class="num-card">
      <div class="num-val">{personal_year}</div>
      <div class="num-label">שנה אישית<br>נוכחית</div>
    </div>
    <div class="num-card">
      <div class="num-val">{hidden_year}</div>
      <div class="num-label">שנה נסתרת</div>
    </div>
    <div class="num-card">
      <div class="num-val">{full_date_short}</div>
      <div class="num-label">סכום תאריך<br>(מקורי)</div>
    </div>
  </div>

  <!-- Info bar: age + year code -->
  <div class="info-bar">
    <div class="info-item">
      <div class="info-val">{age}</div>
      <div class="info-label">גיל נוכחי</div>
    </div>
    <div class="info-item">
      <div class="info-val">{tzimtzum_age}</div>
      <div class="info-label">גיל מצומצם</div>
    </div>
    <div class="info-item">
      <div class="info-val">{p_day}</div>
      <div class="info-label">יום לידה מצומצם</div>
    </div>
    <div class="info-item">
      <div class="info-val">{p_month}</div>
      <div class="info-label">חודש לידה מצומצם</div>
    </div>
    <div class="info-item">
      <div class="info-val">{p_year_r}</div>
      <div class="info-label">שנת לידה מצומצמת</div>
    </div>
  </div>

  <!-- Gematria -->
  <div class="section-title">✧ מספרי שם וגימטריה</div>
  <div class="gem-grid">
    <div class="gem-card">
      <div class="gem-val">{first_name_val}</div>
      <div class="gem-label">שם פרטי (ביטוי)</div>
    </div>
    <div class="gem-card">
      <div class="gem-val">{full_name_val}</div>
      <div class="gem-label">שם מלא (ביטוי)</div>
    </div>
    <div class="gem-card">
      <div class="gem-val">{itzurim_val}</div>
      <div class="gem-label">עיצורים (חיצוני)</div>
    </div>
    <div class="gem-card">
      <div class="gem-val">{aiv_val}</div>
      <div class="gem-label">תנועות (נשמה)</div>
    </div>
  </div>

  <!-- Peaks & Challenges -->
  <div class="section-title">✧ פסגות ואתגרים לפי תקופה</div>
  <table class="periods-table">
    <thead>
      <tr>
        <th>תקופה</th>
        <th>גילאים</th>
        <th>פסגה</th>
        <th>אתגר</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="period-label">תקופה ראשונה</td>
        <td>{ar1}</td>
        <td>{peak1}</td>
        <td>{ch1}</td>
      </tr>
      <tr>
        <td class="period-label">תקופה שנייה</td>
        <td>{ar2}</td>
        <td>{peak2}</td>
        <td>{ch2}</td>
      </tr>
      <tr>
        <td class="period-label">תקופה שלישית</td>
        <td>{ar3}</td>
        <td>{peak3}</td>
        <td>{ch3}</td>
      </tr>
      <tr>
        <td class="period-label">תקופה רביעית</td>
        <td>{ar4}</td>
        <td>{peak4}</td>
        <td>{ch4}</td>
      </tr>
    </tbody>
  </table>

  <!-- Quarters + Pythagoras -->
  <div class="section-title">✧ רבעונים ומרובע פיתגורס</div>
  <div class="bottom-grid">
    <div>
      <div class="quarter-grid">
        <div class="q-card"><div class="q-num">{q1}</div><div class="q-label">רבעון 1</div></div>
        <div class="q-card"><div class="q-num">{q2}</div><div class="q-label">רבעון 2</div></div>
        <div class="q-card"><div class="q-num">{q3}</div><div class="q-label">רבעון 3</div></div>
        <div class="q-card"><div class="q-num">{q4}</div><div class="q-label">רבעון 4</div></div>
      </div>
    </div>
    <div class="pytha-wrap">
      <table class="pytha-table">
        <tbody>{pytha_rows}</tbody>
      </table>
      <div style="font-size:9px;color:{accent};opacity:0.6;margin-top:5px">מרובע פיתגורס</div>
    </div>
  </div>

  <!-- Interpretations -->
  {_build_interp_html(destiny, birth_day_val, personal_year_val, interp_destiny, interp_birth_day, interp_personal_year, interp_peak1, getattr(calc,"peak1_reduced",""), accent, accent_light, frame_color)}

  <!-- Footer -->
  <div class="footer">{brand_name} · {birthdate_str} · נוצר אוטומטית</div>
</div>
</body>
</html>"""

    return html


async def _render_html_to_png(html: str, width: int = 794, height: int = 1123) -> bytes:
    """Use Playwright to render HTML to PNG."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(500)
        png_bytes = await page.screenshot(
            full_page=True,
            type="png",
        )
        await browser.close()
    return png_bytes


async def _render_html_to_pdf(html: str) -> bytes:
    """Use Playwright to render HTML to PDF (A4)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(500)
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        await browser.close()
    return pdf_bytes


def generate_styled_map_png(
    calc: Any,
    first_name: str,
    last_name: str,
    day: int,
    month: int,
    year: int,
    gender: str = "female",
) -> bytes:
    """Synchronous wrapper: generate styled map as PNG."""
    html = build_map_html(calc, first_name, last_name, day, month, year, gender)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _render_html_to_png(html))
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(_render_html_to_png(html))
    except Exception:
        return asyncio.run(_render_html_to_png(html))


def generate_styled_map_pdf(
    calc: Any,
    first_name: str,
    last_name: str,
    day: int,
    month: int,
    year: int,
    gender: str = "female",
) -> bytes:
    """Synchronous wrapper: generate styled map as PDF."""
    html = build_map_html(calc, first_name, last_name, day, month, year, gender)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _render_html_to_pdf(html))
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(_render_html_to_pdf(html))
    except Exception:
        return asyncio.run(_render_html_to_pdf(html))
