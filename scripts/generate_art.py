"""Render the day's category mix as a geometric mosaic PNG.

Reads the most recent *completed* day's category counts from
data/daily_category_mix.csv. The canvas is a grid of cells filled
column-by-column starting from the left; each filled cell gets a random
geometric shape (triangle/fan/circle/semicircle/stripes/square) colored
by its category, chosen with probability proportional to that
category's share of the day. How many cells get filled scales with how
much browsing happened that day -- a quiet day fills fewer columns, and
the boundary between filled and empty fades out over a couple of
columns instead of stopping abruptly.
"""
import colorsys
import csv
import hashlib
import math
import random
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DAILY_MIX = ROOT / "data" / "daily_category_mix.csv"
OUT_DIR = ROOT / "data" / "art"

COLS, ROWS = 6, 10
CELL = 150
WIDTH, HEIGHT = COLS * CELL, ROWS * CELL
BACKGROUND = (245, 242, 235)
OTHER_COLOR = (176, 172, 164)

FADE_COLUMNS = 2.0  # width, in columns, of the fade-to-background zone
SHAPES_PER_VISIT = 0.5  # tunes how much of the grid a typical day fills
MIN_SHAPES = 6


def load_latest_mix():
    """Use the most recent *completed* day, not today-so-far -- today's row
    is always partial, so rendering it would misrepresent the day. Matches
    the daily-9am schedule: render yesterday's full day when you wake up."""
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


def stable_color(category: str) -> tuple:
    """Hash-derived hue so a given domain gets a consistent-ish color across
    different days' pieces, rather than a color that depends on rank/order."""
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
    pad = (x1 - x0) * 0.12
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
    w = (x1 - x0) / n
    vertical = rng.random() < 0.5
    for i in range(0, n, 2):
        if vertical:
            draw.rectangle([x0 + i * w, y0, x0 + (i + 1) * w, y1], fill=color)
        else:
            draw.rectangle([x0, y0 + i * w, x1, y0 + (i + 1) * w], fill=color)


def draw_square(draw, box, color, rng):
    x0, y0, x1, y1 = box
    pad = (x1 - x0) * rng.uniform(0.12, 0.22)
    draw.rectangle([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=color)


SHAPE_DRAWERS = [draw_triangle, draw_fan, draw_circle, draw_semicircle, draw_stripes, draw_square]


def build_ticket_list(counts: dict, budget: int, rng: random.Random) -> list:
    """Category names repeated proportionally to their share of the day,
    shuffled so the fill order looks random cell-to-cell while still
    reflecting the real proportions overall."""
    total = sum(counts.values()) or 1
    tickets = []
    for category, n in counts.items():
        tickets += [category] * max(1, round(n / total * budget))
    rng.shuffle(tickets)
    if not tickets:
        tickets = ["other"]
    while len(tickets) < budget:
        tickets.append(rng.choice(tickets))
    return tickets[:budget]


def render(day: str, counts: dict) -> Path:
    total = sum(counts.values())
    categories = list(counts.keys()) or ["other"]
    palette = {c: stable_color(c) for c in categories}

    seed_int = int(hashlib.sha256(day.encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    total_cells = COLS * ROWS
    budget = min(total_cells, max(MIN_SHAPES, round(total * SHAPES_PER_VISIT)))
    tickets = build_ticket_list(counts, budget, rng)
    boundary_col = budget / ROWS

    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)

    idx = 0
    for col in range(COLS):
        for row in range(ROWS):
            box = (col * CELL, row * CELL, (col + 1) * CELL, (row + 1) * CELL)
            shape_fn = SHAPE_DRAWERS[rng.randrange(len(SHAPE_DRAWERS))]
            if idx < budget:
                color = shade(palette[tickets[idx]], rng.uniform(0.85, 1.1))
                shape_fn(draw, box, color, rng)
            else:
                fade_alpha = max(0.0, min(1.0, 1 - (col - boundary_col) / FADE_COLUMNS))
                if fade_alpha > 0.04:
                    color = blend(palette[rng.choice(categories)], fade_alpha)
                    shape_fn(draw, box, color, rng)
            idx += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{day}.png"
    img.save(out_path)
    return out_path, budget, total_cells


def main():
    day, counts = load_latest_mix()
    out_path, budget, total_cells = render(day, counts)
    total = sum(counts.values())
    mix_summary = ", ".join(f"{c}={n}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f"{day}: {total} visits across {len(counts)} categories ({mix_summary})")
    print(f"Filled {budget}/{total_cells} cells")
    print(f"Rendered {out_path}")


if __name__ == "__main__":
    main()
