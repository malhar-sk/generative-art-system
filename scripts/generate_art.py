"""Render the day's category mix as a screen-filling geometric mosaic PNG.

Reads the most recent completed day's category counts from
data/daily_category_mix.csv. The canvas is sized to the actual primary
screen resolution, divided into a fine grid of icon-sized cells (using
the configured Windows shell icon size). Symbols are drawn in randomly
sized groups of those fine cells (mostly pairs and quads, sometimes
bigger accent pieces) rather than one shape per tiny cell, since a
single icon-sized shape would be too small to read.

Groups are packed column by column starting from the left, colored by
a category chosen with probability proportional to that category's
share of the day. Coverage always fills at least a quarter of the
screen -- there is plenty of history to justify it -- scaling up
further on busier days; past the data budget, a couple of columns fade
toward the background instead of stopping abruptly.
"""
import colorsys
import csv
import ctypes
import hashlib
import random
import sys
import winreg
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DAILY_MIX = ROOT / "data" / "daily_category_mix.csv"
OUT_DIR = ROOT / "data" / "art"

BACKGROUND = (245, 242, 235)
OTHER_COLOR = (176, 172, 164)

FADE_COLUMNS = 3.0
MIN_COVERAGE = 0.25
MAX_EXTRA_COVERAGE = 0.65
REFERENCE_VISITS = 400


def detect_screen_size():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def detect_icon_size():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics") as key:
            value, _ = winreg.QueryValueEx(key, "Shell Icon Size")
            return int(value)
    except (FileNotFoundError, OSError, ValueError):
        return 32


def load_latest_mix():
    if not DAILY_MIX.exists():
        sys.exit(f"No categorized data found at {DAILY_MIX}. Run categorize.py first.")
    with DAILY_MIX.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows:
        sys.exit("daily_category_mix.csv is empty -- nothing to render.")

    today = date.today().isoformat()
    completed = [r for r in rows if r["date"] < today] or rows
    categories = [c for c in fieldnames if c not in ("date", "total")]
    latest = completed[-1]
    day = latest["date"]
    counts = {c: int(latest[c]) for c in categories if int(latest[c]) > 0}
    return day, counts


def stable_color(category):
    if category == "other":
        return OTHER_COLOR
    digest = hashlib.md5(category.encode()).hexdigest()
    hue = (int(digest[:8], 16) % 1000) / 1000
    sat = 0.55 + (int(digest[8:10], 16) % 30) / 100
    val = 0.65 + (int(digest[10:12], 16) % 25) / 100
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))


def shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def blend(color, alpha):
    return tuple(int(bg * (1 - alpha) + c * alpha) for bg, c in zip(BACKGROUND, color))


def draw_triangle(draw, box, color, rng):
    x0, y0, x1, y1 = box
    corner = rng.choice(["tl", "tr", "bl", "br"])
    pts = {
        "tl": [(x0, y0), (x1, y0), (x0, y1)],
        "tr": [(x0, y0), (x1, y0), (x1, y1)],
        "bl": [(x0, y1), (x1, y1), (x0, y0)],
        "br": [(x1, y0), (x1, y1), (x0, y1)],
    }[corner]
    draw.polygon(pts, fill=color)


def draw_fan(draw, box, color, rng):
    x0, y0, x1, y1 = box
    corner = rng.choice(["tl", "tr", "br", "bl"])
    cx, cy, start = {
        "tl": (x0, y0, 0),
        "tr": (x1, y0, 90),
        "br": (x1, y1, 180),
        "bl": (x0, y1, 270),
    }[corner]
    r = x1 - x0
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], start, start + 90, fill=color)


def draw_circle(draw, box, color, rng):
    x0, y0, x1, y1 = box
    pad = (x1 - x0) * 0.1
    draw.ellipse([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=color)


def draw_semicircle(draw, box, color, rng):
    x0, y0, x1, y1 = box
    orient = rng.choice([0, 90, 180, 270])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = (x1 - x0) / 2
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], orient, orient + 180, fill=color)


def draw_stripes(draw, box, color, rng):
    x0, y0, x1, y1 = box
    n = rng.choice([3, 5])
    vertical = rng.random() < 0.5
    if vertical:
        w = (x1 - x0) / n
        for i in range(0, n, 2):
            draw.rectangle([x0 + i * w, y0, x0 + (i + 1) * w, y1], fill=color)
    else:
        h = (y1 - y0) / n
        for i in range(0, n, 2):
            draw.rectangle([x0, y0 + i * h, x1, y0 + (i + 1) * h], fill=color)


def draw_square(draw, box, color, rng):
    x0, y0, x1, y1 = box
    pad_x = (x1 - x0) * rng.uniform(0.1, 0.2)
    pad_y = (y1 - y0) * rng.uniform(0.1, 0.2)
    draw.rectangle([x0 + pad_x, y0 + pad_y, x1 - pad_x, y1 - pad_y], fill=color)


SHAPE_DRAWERS = [draw_triangle, draw_fan, draw_circle, draw_semicircle, draw_stripes, draw_square]


def choose_group_size(rng):
    r = rng.random()
    if r < 0.40:
        return 2, 2
    if r < 0.65:
        return rng.choice([(1, 2), (2, 1)])
    if r < 0.85:
        return rng.choice([(2, 3), (3, 2)])
    if r < 0.95:
        return 3, 3
    return 1, 1


def fits_free(used, col, row, w, h, cols, rows):
    if col + w > cols or row + h > rows:
        return False
    return not any(used[col + dx][row + dy] for dx in range(w) for dy in range(h))


def render(day, counts):
    screen_w, screen_h = detect_screen_size()
    icon = detect_icon_size()

    cols = screen_w // icon
    rows = screen_h // icon
    total_cells = cols * rows

    total_visits = sum(counts.values())
    categories = list(counts.keys()) or ["other"]
    weights = [counts.get(c, 1) for c in categories]
    palette = {c: stable_color(c) for c in categories}

    seed_int = int(hashlib.sha256(day.encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    extra = min(MAX_EXTRA_COVERAGE, total_visits / REFERENCE_VISITS * MAX_EXTRA_COVERAGE)
    budget_cells = round((MIN_COVERAGE + extra) * total_cells)
    boundary_col = budget_cells / rows if rows else 0

    img = Image.new("RGB", (cols * icon, rows * icon), BACKGROUND)
    draw = ImageDraw.Draw(img)
    used = [[False] * rows for _ in range(cols)]

    filled_cells = 0
    symbol_count = 0
    for col in range(cols):
        row = 0
        while row < rows:
            if used[col][row]:
                row += 1
                continue

            w, h = choose_group_size(rng)
            while (w > 1 or h > 1) and not fits_free(used, col, row, w, h, cols, rows):
                if w >= h and w > 1:
                    w -= 1
                elif h > 1:
                    h -= 1
                else:
                    break

            for dx in range(w):
                for dy in range(h):
                    used[col + dx][row + dy] = True

            box = (col * icon, row * icon, (col + w) * icon, (row + h) * icon)
            shape_fn = SHAPE_DRAWERS[rng.randrange(len(SHAPE_DRAWERS))]

            if filled_cells < budget_cells:
                category = rng.choices(categories, weights=weights)[0]
                color = shade(palette[category], rng.uniform(0.85, 1.1))
                shape_fn(draw, box, color, rng)
                symbol_count += 1
            else:
                fade_alpha = max(0.0, min(1.0, 1 - (col - boundary_col) / FADE_COLUMNS))
                if fade_alpha > 0.04:
                    category = rng.choices(categories, weights=weights)[0]
                    color = blend(palette[category], fade_alpha)
                    shape_fn(draw, box, color, rng)
                    symbol_count += 1

            filled_cells += w * h
            row += h

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{day}.png"
    img.save(out_path)
    return out_path, symbol_count, budget_cells, total_cells, (screen_w, screen_h), icon


def main():
    day, counts = load_latest_mix()
    out_path, symbol_count, budget_cells, total_cells, screen, icon = render(day, counts)
    total = sum(counts.values())
    mix_summary = ", ".join(f"{c}={n}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    grid_cols = screen[0] // icon
    grid_rows = screen[1] // icon
    print(f"Screen {screen[0]}x{screen[1]}, icon size {icon}px -> grid {grid_cols}x{grid_rows} ({total_cells} cells)")
    print(f"{day}: {total} visits across {len(counts)} categories ({mix_summary})")
    print(f"Drew {symbol_count} symbols covering {budget_cells}/{total_cells} cells ({budget_cells/total_cells:.0%})")
    print(f"Rendered {out_path}")


if __name__ == "__main__":
    main()
