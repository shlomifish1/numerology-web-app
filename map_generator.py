"""PIL-based numerology map generator for web use."""
from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional, Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise ImportError("Pillow is required: pip install Pillow")

SCRIPT_DIR = Path(__file__).parent
IMAGE_DIR = SCRIPT_DIR / "image"
FONT_PATH = IMAGE_DIR / "fonts" / "Heebo-VariableFont_wght.ttf"

FILL_WHITE = (255, 255, 255, 255)
FILL_YELLOW = (255, 215, 0, 255)


def _rtl(text: str) -> str:
    """Convert Hebrew string to visual display order for PIL."""
    try:
        from bidi.algorithm import get_display
        return get_display(str(text))
    except ImportError:
        t = str(text)
        # Simple reversal for Hebrew-only strings
        if any('\u0590' <= c <= '\u05FF' for c in t):
            return t[::-1]
        return t


def _get_font(size: int) -> "ImageFont.FreeTypeFont":
    if FONT_PATH.exists():
        try:
            return ImageFont.truetype(str(FONT_PATH), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _s(val: Any) -> str:
    """Safe string conversion."""
    if val is None:
        return ""
    return str(val)


def generate_map_png(
    calc: Any,
    first_name: str,
    last_name: str,
    day: int,
    month: int,
    year: int,
    gender: str = "female",
) -> bytes:
    """
    Generate the numerology map as PNG bytes.
    Uses second_page.png as the template (1000×600).
    Coordinates match the Tkinter desktop app exactly.
    """
    template_path = IMAGE_DIR / "second_page.png"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_info = _get_font(20)
    font_title = _get_font(25)

    # ── Header ──────────────────────────────────────────────────
    full_name = f"{first_name} {last_name}".strip()
    birthdate_str = f"{day:02d}{month:02d}{year}"

    draw.text((800, 40), _rtl(full_name), fill=FILL_YELLOW, font=font_title, anchor="mm")
    draw.text((580, 40), birthdate_str, fill=FILL_YELLOW, font=font_title, anchor="mm")

    # Date details: p_day / p_month / p_year
    p_day = _s(getattr(calc, "p_day", ""))
    p_month = _s(getattr(calc, "p_month", ""))
    p_year = _s(getattr(calc, "p_year", ""))
    date_details = f"{p_day} / {p_month} / {p_year}"
    draw.text((580, 100), date_details, fill=FILL_WHITE, font=font_info, anchor="mm")

    # Destiny / full_date_short
    destiny = getattr(calc, "final_number_destiny", "")
    full_date_short = getattr(calc, "full_date_short", "")
    destiny_text = f"{destiny} / {full_date_short}" if full_date_short else _s(destiny)
    draw.text((790, 150), destiny_text, fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Name / Gematria values ───────────────────────────────────
    draw.text((800, 209), _s(getattr(calc, "first_name_val", "")), fill=FILL_WHITE, font=font_info, anchor="mm")
    draw.text((635, 265), _s(getattr(calc, "full_name_val", "")), fill=FILL_WHITE, font=font_info, anchor="mm")
    draw.text((825, 320), _s(getattr(calc, "itzurim_val", "")), fill=FILL_WHITE, font=font_info, anchor="mm")
    draw.text((870, 375), _s(getattr(calc, "aiv_val", "")), fill=FILL_WHITE, font=font_info, anchor="mm")

    # Personal year
    draw.text((790, 425), _s(getattr(calc, "shana_ishit", "")), fill=FILL_WHITE, font=font_info, anchor="mm")

    # Hidden year: "X/Y" where X = hidden part, Y = destiny
    shana_nisteret = getattr(calc, "shana_nisteret", None)
    if shana_nisteret and "_" in _s(shana_nisteret):
        parts = _s(shana_nisteret).split("_")
        nisteret_text = f"{parts[1]}/{destiny}" if len(parts) > 1 else _s(shana_nisteret)
    elif shana_nisteret:
        nisteret_text = _s(shana_nisteret).replace("_", "/")
    else:
        nisteret_text = ""
    draw.text((790, 479), nisteret_text, fill=FILL_WHITE, font=font_info, anchor="mm")

    # Age
    age = getattr(calc, "age", "")
    tzimtzum_age = getattr(calc, "tzimtzum_age", "")
    shana_ishit = getattr(calc, "shana_ishit", "")
    draw.text((795, 525), _s(age), fill=FILL_WHITE, font=font_info, anchor="mm")

    # Year code display: age + tzimtzum + personal year
    if age:
        year_code = f"{age}{tzimtzum_age}{shana_ishit}"
    else:
        year_code = ""
    draw.text((795, 565), year_code, fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Peaks ────────────────────────────────────────────────────
    peaks_x = 90
    for i, attr in enumerate(["peak1_reduced", "peak2_reduced", "peak3_reduced", "peak4_reduced"]):
        y = 135 + i * 50
        draw.text((peaks_x, y), _s(getattr(calc, attr, "")), fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Challenges ───────────────────────────────────────────────
    challenges_x = 230
    for i, attr in enumerate(["challenge1_reduced", "challenge2_reduced", "challenge3_reduced", "challenge4_reduced"]):
        y = 135 + i * 50
        draw.text((challenges_x, y), _s(getattr(calc, attr, "")), fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Age ranges ───────────────────────────────────────────────
    ages_x = 370
    first_pick = getattr(calc, "first_pick_start", 0) or 0
    second_pick = getattr(calc, "second_pick_start", 0) or 0
    third_pick = getattr(calc, "third_pick_start", 0) or 0
    forth_pick = getattr(calc, "forth_pick_start", 0) or 0

    age_ranges = [
        f"{first_pick} - {second_pick - 1}" if second_pick else "",
        f"{second_pick} - {third_pick - 1}" if third_pick else "",
        f"{third_pick} - {forth_pick - 1}" if forth_pick else "",
        f"{forth_pick} - {forth_pick + 8}" if forth_pick else "",
    ]
    for i, text in enumerate(age_ranges):
        y = 135 + i * 50
        draw.text((ages_x, y), text, fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Quarters ─────────────────────────────────────────────────
    quarters_x = 370
    for i, attr in enumerate(["first_quarter_reduced", "second_quarter_reduced", "third_quarter_reduced", "forth_quarter_reduced"]):
        y_positions = [375, 420, 465, 505]
        draw.text((quarters_x, y_positions[i]), _s(getattr(calc, attr, "")), fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Pythagoras square ────────────────────────────────────────
    pytha_x = {1: 530, 2: 540, 3: 542, 4: 625, 5: 626, 6: 627, 7: 705, 8: 706, 9: 707}
    pytha_y = {1: 375, 4: 376, 7: 378, 2: 420, 5: 420, 8: 420, 3: 463, 6: 460, 9: 464}

    bd = f"{day:02d}{month:02d}{year}"
    if len(bd) == 8 and bd.isdigit():
        counts: dict[int, int] = {}
        for c in bd:
            d_int = int(c)
            if d_int != 0:
                counts[d_int] = counts.get(d_int, 0) + 1
        for d_int, count in counts.items():
            px = pytha_x.get(d_int)
            py = pytha_y.get(d_int)
            if px and py:
                draw.text((px, py), str(d_int) * count, fill=FILL_WHITE, font=font_info, anchor="mm")

    # ── Export ───────────────────────────────────────────────────
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
