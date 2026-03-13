"""
Generate a shareable weekly progress card (PNG) using Pillow.
No external APIs — only system fonts + PIL drawing primitives.
"""
import io
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

from database.models import DailyLog, User, WeightLog
from heroes.data import get_hero
from services.analytics_service import AnalyticsService

# ── Canvas size (portrait — fits Stories 9:16 with space) ─────────────────────
W, H = 1080, 1350

# ── Color palettes per hero category ──────────────────────────────────────────
_PALETTE: dict[str, dict] = {
    "chill":  {"bg": (28, 78, 50),   "card": (38, 100, 65),  "accent": (90, 195, 125),  "text": (235, 255, 240)},
    "funny":  {"bg": (85, 48, 12),   "card": (110, 65, 22),  "accent": (245, 170, 55),  "text": (255, 245, 215)},
    "cute":   {"bg": (105, 30, 65),  "card": (135, 45, 88),  "accent": (240, 105, 165), "text": (255, 220, 238)},
    "energy": {"bg": (100, 18, 18),  "card": (128, 32, 32),  "accent": (235, 75, 65),   "text": (255, 222, 218)},
    "smart":  {"bg": (18, 48, 100),  "card": (28, 65, 132),  "accent": (85, 155, 245),  "text": (212, 232, 255)},
}
_DEFAULT_PALETTE = {"bg": (32, 32, 52), "card": (48, 48, 72), "accent": (115, 115, 215), "text": (222, 222, 255)}

# ── Font loading ───────────────────────────────────────────────────────────────
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
_FONT_BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = _FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _centered_text(draw: ImageDraw.ImageDraw, y: int, text: str, font, color, width: int = W) -> None:
    bbox = font.getbbox(text)
    x = (width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=color)


def _progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int, y: int, bar_w: int, bar_h: int,
    ratio: float, bg_color: tuple, fill_color: tuple,
    radius: int = 6,
) -> None:
    ratio = max(0.0, min(1.0, ratio))
    draw.rounded_rectangle([x, y, x + bar_w, y + bar_h], radius=radius, fill=bg_color)
    if ratio > 0:
        fill_w = max(radius * 2, int(bar_w * ratio))
        draw.rounded_rectangle([x, y, x + fill_w, y + bar_h], radius=radius, fill=fill_color)


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_progress_card(
    user: User,
    logs: list[DailyLog],
    weight_logs: list[WeightLog],
    analytics: AnalyticsService,
) -> bytes:
    """
    Generate a weekly progress PNG card.
    Returns raw PNG bytes suitable for bot.send_photo(photo=BufferedInputFile(...)).
    """
    hero = get_hero(user.hero_key)
    palette = _PALETTE.get(hero.category, _DEFAULT_PALETTE)

    bg   = palette["bg"]
    card = palette["card"]
    acc  = palette["accent"]
    txt  = palette["text"]
    dim  = tuple(max(0, c - 60) for c in txt)  # dimmed text

    img  = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # ── Fonts ──────────────────────────────────────────────────────────────────
    f_hero   = _font(52, bold=True)
    f_week   = _font(34)
    f_index  = _font(160, bold=True)
    f_label  = _font(32)
    f_stat   = _font(38, bold=True)
    f_stat_l = _font(30)
    f_brand  = _font(28)

    pad = 70

    # ── Header: hero name + week range ────────────────────────────────────────
    today = date.today()
    week_start = today - timedelta(days=6)
    week_str = f"{week_start.strftime('%d.%m')} — {today.strftime('%d.%m.%Y')}"

    _centered_text(draw, 55, f"{hero.emoji}  {hero.name}", f_hero, acc)
    _centered_text(draw, 120, week_str, f_week, dim)

    # Separator
    draw.line([(pad, 178), (W - pad, 178)], fill=card, width=2)

    # ── Big index ─────────────────────────────────────────────────────────────
    indices = [l.day_index for l in logs if l.day_index is not None]
    avg_index = round(sum(indices) / len(indices), 1) if indices else 0.0

    _centered_text(draw, 195, f"{avg_index}", f_index, acc)
    _centered_text(draw, 370, "средний индекс недели", f_label, dim)
    _centered_text(draw, 408, "из 10", f_label, dim)

    # Stars under index
    stars = int(round(avg_index / 2))
    stars_txt = "★" * stars + "☆" * (5 - stars)
    _centered_text(draw, 445, stars_txt, _font(44), acc)

    # Separator
    draw.line([(pad, 510), (W - pad, 510)], fill=card, width=2)

    # ── Stats grid (2 columns) ────────────────────────────────────────────────
    col1_x, col2_x = pad, W // 2 + 20
    row_h = 110
    stat_y = 530

    def stat_block(x: int, y: int, label: str, value: str, bar_ratio: float | None = None) -> None:
        draw.text((x, y), label, font=f_stat_l, fill=dim)
        draw.text((x, y + 34), value, font=f_stat, fill=txt)
        if bar_ratio is not None:
            _progress_bar(draw, x, y + 80, 420, 10, bar_ratio, card, acc)

    row = 0

    # Steps
    if "steps" in user.selected_habits:
        total_steps = sum(l.steps for l in logs if l.steps is not None)
        target_steps = user.steps_target * max(len(logs), 1)
        ratio = total_steps / target_steps if target_steps else 0
        x = col1_x if row % 2 == 0 else col2_x
        y = stat_y + (row // 2) * row_h
        stat_block(x, y, "👟 Шаги за неделю", f"{total_steps:,}", ratio)
        row += 1

    # Sleep
    if "sleep" in user.selected_habits:
        vals = [l.sleep_hours for l in logs if l.sleep_hours is not None]
        if vals:
            avg_sleep = sum(vals) / len(vals)
            x = col1_x if row % 2 == 0 else col2_x
            y = stat_y + (row // 2) * row_h
            stat_block(x, y, "😴 Сон в среднем", f"{avg_sleep:.1f} ч", avg_sleep / 8)
            row += 1

    # Alcohol-free days
    if "alcohol" in user.selected_habits:
        clean = sum(1 for l in logs if l.alcohol is not None and not l.alcohol)
        x = col1_x if row % 2 == 0 else col2_x
        y = stat_y + (row // 2) * row_h
        stat_block(x, y, "🍷 Без алкоголя", f"{clean} из {len(logs)} дн.", clean / max(len(logs), 1))
        row += 1

    # No-sugar days
    if "no_sugar" in user.selected_habits:
        clean = sum(1 for l in logs if l.no_sugar is not None and not l.no_sugar)
        x = col1_x if row % 2 == 0 else col2_x
        y = stat_y + (row // 2) * row_h
        stat_block(x, y, "🍬 Без сахара", f"{clean} из {len(logs)} дн.", clean / max(len(logs), 1))
        row += 1

    # Energy avg
    if "energy" in user.selected_habits:
        vals = [l.energy_level for l in logs if l.energy_level is not None]
        if vals:
            avg_e = sum(vals) / len(vals)
            x = col1_x if row % 2 == 0 else col2_x
            y = stat_y + (row // 2) * row_h
            stat_block(x, y, "⚡ Энергия", f"{avg_e:.1f} / 5", avg_e / 5)
            row += 1

    # Stress avg
    if "stress" in user.selected_habits:
        vals = [l.stress_level for l in logs if l.stress_level is not None]
        if vals:
            avg_s = sum(vals) / len(vals)
            x = col1_x if row % 2 == 0 else col2_x
            y = stat_y + (row // 2) * row_h
            stat_block(x, y, "🧘 Стресс", f"{avg_s:.1f} / 5", 1 - avg_s / 5)
            row += 1

    # Weight delta
    if weight_logs and len(weight_logs) >= 2:
        delta = weight_logs[-1].weight - weight_logs[0].weight
        sign = "+" if delta > 0 else ""
        x = col1_x if row % 2 == 0 else col2_x
        y = stat_y + (row // 2) * row_h
        draw.text((x, y), "⚖️ Изменение веса", font=f_stat_l, fill=dim)
        draw.text((x, y + 34), f"{sign}{delta:.1f} кг", font=f_stat, fill=txt)
        row += 1

    # ── Streaks ────────────────────────────────────────────────────────────────
    streak_y = stat_y + ((row + 1) // 2) * row_h + 20
    draw.line([(pad, streak_y), (W - pad, streak_y)], fill=card, width=2)
    streak_y += 24

    streaks = analytics.get_streaks(logs, user)
    streak_parts = [
        f"🔥 {v} {AnalyticsService._days_word(v)} подряд"
        for k, v in streaks.items() if v >= 2
    ]
    if streak_parts:
        streak_text = "   ".join(streak_parts[:3])
        _centered_text(draw, streak_y, streak_text, _font(30), acc)
        streak_y += 46

    # ── Hero phrase ────────────────────────────────────────────────────────────
    draw.line([(pad, H - 145), (W - pad, H - 145)], fill=card, width=2)
    phrase = hero.phrase("report")
    # Truncate if too long for one line
    if len(phrase) > 55:
        phrase = phrase[:52] + "…"
    _centered_text(draw, H - 128, phrase, _font(28), dim)
    _centered_text(draw, H - 82, f"@Privykai_bot  •  Habit Tracker", f_brand, acc)

    # ── Corner accent dots ────────────────────────────────────────────────────
    r = 18
    for cx, cy in [(r + 10, r + 10), (W - r - 10, r + 10), (r + 10, H - r - 10), (W - r - 10, H - r - 10)]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc)

    # ── Serialize to bytes ────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
