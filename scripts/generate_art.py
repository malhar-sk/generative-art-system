"""Render a decay-weighted recent-history category mix as a geometric
mosaic PNG, laid out on an 8x4 grid of sectors.

Reads data/daily_category_mix.csv and combines it into one snapshot using
exponential recency weighting (see HALF_LIFE_DAYS) rather than a single
day's raw counts -- each prior day contributes, weighted down the further
back it is, so the piece drifts gradually day to day instead of jumping
around on daily noise, while still being dominated by roughly the last
few weeks.

The canvas (the actual primary screen resolution) is divided into a
SECTOR_COLS x SECTOR_ROWS grid of large sectors. Sectors fill in ring
order starting from the top-left corner, expanding outward to adjacent
sectors (Chebyshev/8-directional distance), until however many sectors
the day's data warrants -- not a fixed floor or a forced full screen,
just a smooth, uncapped function of how much browsing happened. Each
active sector gets completely filled with small icon-sized shapes,
inactive sectors stay background. Since sectors are strictly
non-overlapping regions and each one is packed independently with the
same non-overlap-checked placement used before, symbols never overlap,
across sectors or within one.

Within a sector, symbols are drawn in randomly sized groups of icon-sized
cells (mostly pairs and quads, sometimes bigger accent pieces) rather
than one shape per tiny cell, since a single icon-sized shape would be
too small to read. Every group gets the same gutter inset regardless of
its size or color, so the composition reads as evenly spaced -- the
gutter itself is the negative space between pieces -- even though shape
and color choice stay random.

The grid layout itself has memory: each render loads the previous
render's group placement (data/render_state.json) and reuses it at
roughly REUSE_PROBABILITY of positions -- same size, same shape type --
while the rest mutate fresh. Color always reflects today's real data
regardless of whether a group's geometry was inherited or freshly
rolled, so the piece has actual lineage (today's image descends from
yesterday's) instead of being a full recompute each time. Falls back
to a fully fresh layout if the state file is missing, corrupt, or the
screen/icon/sector configuration changed since the last render.
"""
import csv
import ctypes
import hashlib
import json
import math
import random
import sys
import winreg
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DAILY_MIX = ROOT / "data" / "daily_category_mix.csv"
OUT_DIR = ROOT / "data" / "art"
LAYOUT_STATE_PATH = ROOT / "data" / "render_state.json"

BACKGROUND = (0, 0, 0)   # black
# Original palette (#F2E7DB / #C07A4A / #9B5B3A / #4F6B5A / #23312B) was
# designed for a cream background. On black, the two darkest colors would
# nearly vanish, so they are brightened in HSV (value up, slight saturation
# boost; dark green's hue nudged toward teal so it does not collapse into
# sage once both are lighter). Cream and orange were already vivid enough
# to keep as-is. Cream is no longer the background, so it joins the accent
# rotation instead.
ACCENT_COLORS = [
    (242, 231, 218),  # #F2E7DA -- cream, unchanged
    (191, 122, 75),   # #BF7A4B -- orange, unchanged
    (184, 101, 59),   # #B8653B -- rust, brightened from #9B5B3A
    (98, 148, 117),   # #629475 -- sage, brightened from #4F6B5A
    (59, 102, 89),    # #3B6659 -- dark green, brightened from #23312B
]

SECTOR_COLS = 8           # outer grid: sectors across
SECTOR_ROWS = 4           # outer grid: sectors down
COVERAGE_SCALE = 80       # *daily-average* visit count at which coverage reaches ~63% of the sectors
GUTTER_FRACTION = 0.12    # inset applied to every group's box, as a fraction of icon size

HALF_LIFE_DAYS = 8        # a day's weight halves every this many days back
LOOKBACK_DAYS = 90        # days of history considered; beyond this the weight is negligible anyway

REUSE_PROBABILITY = 0.70  # fraction of grid positions that inherit yesterday's group (size + shape type) rather than rolling fresh -- the piece's visual memory
MIN_SECTORS = 1           # always render at least the corner sector, even on the quietest day -- never a fully blank canvas


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


def load_weighted_mix():
    """Combine recent days into one decay-weighted category snapshot instead
    of using a single day's raw counts. Excludes today (always partial --
    the day isn't over) and anchors the decay on the most recent *completed*
    day, matching the daily-9am schedule: each morning renders yesterday
    weighted heavily, with the last few weeks tailing off behind it.

    Returns (anchor_day, weighted_counts, effective_daily_visits) where
    weighted_counts are category shares on an arbitrary relative scale (fine
    for proportional shape/color choice) and effective_daily_visits is the
    weighted counts renormalized back to a single-day scale (the sum divided
    by the total weight applied), so the coverage formula -- tuned against
    single-day visit counts -- still spans quiet-to-busy correctly instead
    of saturating once several weeks are being blended together."""
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
    if not completed:
        sys.exit("No completed days in daily_category_mix.csv -- nothing to render.")

    categories = [c for c in fieldnames if c not in ("date", "total")]
    anchor_day = completed[-1]["date"]
    anchor = date.fromisoformat(anchor_day)
    cutoff = anchor - timedelta(days=LOOKBACK_DAYS)

    weighted_counts = {}
    weight_total = 0.0
    for row in completed:
        day = date.fromisoformat(row["date"])
        if day < cutoff:
            continue
        days_ago = (anchor - day).days
        weight = 0.5 ** (days_ago / HALF_LIFE_DAYS)
        row_total = sum(int(row[c]) for c in categories)
        if row_total == 0:
            continue
        weight_total += weight
        for c in categories:
            n = int(row[c])
            if n:
                weighted_counts[c] = weighted_counts.get(c, 0.0) + n * weight

    if not weighted_counts:
        sys.exit("No visits within the lookback window -- nothing to render.")

    effective_daily_visits = sum(weighted_counts.values()) / weight_total if weight_total else 0.0
    return anchor_day, weighted_counts, effective_daily_visits


def stable_color(category):
    """Hash-derived pick from the fixed accent palette, so a given domain
    gets a consistent color across different days' pieces."""
    digest = hashlib.md5(category.encode()).hexdigest()
    return ACCENT_COLORS[int(digest[:8], 16) % len(ACCENT_COLORS)]


def shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


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
    draw.ellipse([x0, y0, x1, y1], fill=color)


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
    draw.rectangle(box, fill=color)


SHAPE_DRAWERS = [draw_triangle, draw_fan, draw_circle, draw_semicircle, draw_stripes, draw_square]
SHAPE_BY_NAME = {fn.__name__: fn for fn in SHAPE_DRAWERS}


def load_prior_layout(screen_w, screen_h, icon):
    """Returns {(srow, scol, col, row): (w, h, shape_name)} for the previous
    render's group placement, keyed by sector + each group's origin cell
    within that sector. Empty dict (fresh layout, no bias) if the state
    file is missing, corrupt, or the screen/icon/sector configuration
    changed since the last render (makes the old positions meaningless)."""
    try:
        with LAYOUT_STATE_PATH.open(encoding="utf-8") as f:
            state = json.load(f)
        grid = state["grid"]
        expected = (SECTOR_COLS, SECTOR_ROWS, icon, screen_w, screen_h)
        actual = (grid["sector_cols"], grid["sector_rows"], grid["icon"], grid["screen_w"], grid["screen_h"])
        if expected != actual:
            return {}
        return {
            (g["srow"], g["scol"], g["col"], g["row"]): (g["w"], g["h"], g["shape"])
            for g in state["groups"]
        }
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
        return {}


def save_layout(day, screen_w, screen_h, icon, placed_groups):
    LAYOUT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "date": day,
        "grid": {
            "sector_cols": SECTOR_COLS, "sector_rows": SECTOR_ROWS,
            "icon": icon, "screen_w": screen_w, "screen_h": screen_h,
        },
        "groups": [
            {"srow": srow, "scol": scol, "col": col, "row": row, "w": w, "h": h, "shape": shape_name}
            for srow, scol, col, row, w, h, shape_name in placed_groups
        ],
    }
    with LAYOUT_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f)


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


def sector_bounds(index, count, total_px):
    """Pixel span [start, end) for sector `index` of `count` along an axis
    of length total_px -- linear interpolation so the sectors always cover
    the full screen exactly (any remainder lands in the last sector) rather
    than a fixed-width sector leaving a gap at the edge."""
    return (index * total_px) // count, ((index + 1) * total_px) // count


def sector_fill_order(rng):
    """Sector (row, col) coordinates ordered starting from the top-left
    corner, expanding outward ring by ring to adjacent sectors (Chebyshev
    distance -- diagonal neighbors count as adjacent, giving square rings
    growing from the corner). Each ring's internal order is shuffled with
    the day's seed for variety, without disturbing the ring-by-ring
    outward growth itself."""
    coords = [(r, c) for r in range(SECTOR_ROWS) for c in range(SECTOR_COLS)]
    coords.sort(key=lambda rc: max(rc[0], rc[1]))
    ordered = []
    for _, ring in groupby(coords, key=lambda rc: max(rc[0], rc[1])):
        ring = list(ring)
        rng.shuffle(ring)
        ordered.extend(ring)
    return ordered


def render(day, counts, effective_visits):
    screen_w, screen_h = detect_screen_size()
    icon = detect_icon_size()
    gutter = icon * GUTTER_FRACTION
    total_sectors = SECTOR_COLS * SECTOR_ROWS

    categories = list(counts.keys()) or ["other"]
    weights = [counts.get(c, 1) for c in categories]  # relative shares; scale doesn't matter here
    palette = {c: stable_color(c) for c in categories}

    seed_int = int(hashlib.sha256(day.encode()).hexdigest(), 16)
    rng = random.Random(seed_int)

    # Uncapped, organic coverage -- approaches (never forced to) all 32
    # sectors as visit volume grows, shrinks back down on quiet days.
    # Driven by effective_visits (the decay-weighted window renormalized
    # to a single-day scale), not a raw multi-day sum -- otherwise blending
    # weeks of history together would saturate this every time.
    coverage = 1 - math.exp(-effective_visits / COVERAGE_SCALE)
    budget_sectors = max(MIN_SECTORS, round(coverage * total_sectors))
    active_sectors = sector_fill_order(rng)[:budget_sectors]

    prior_layout = load_prior_layout(screen_w, screen_h, icon)

    img = Image.new("RGB", (screen_w, screen_h), BACKGROUND)
    draw = ImageDraw.Draw(img)

    placed_groups = []
    symbol_count = 0
    for srow, scol in active_sectors:
        sx0, sx1 = sector_bounds(scol, SECTOR_COLS, screen_w)
        sy0, sy1 = sector_bounds(srow, SECTOR_ROWS, screen_h)
        cols = max(1, (sx1 - sx0) // icon)
        rows = max(1, (sy1 - sy0) // icon)
        used = [[False] * rows for _ in range(cols)]

        for col in range(cols):
            row = 0
            while row < rows:
                if used[col][row]:
                    row += 1
                    continue

                prior = prior_layout.get((srow, scol, col, row))
                if prior is not None and rng.random() < REUSE_PROBABILITY:
                    w, h, shape_name = prior
                    shape_fn = SHAPE_BY_NAME.get(shape_name) or SHAPE_DRAWERS[rng.randrange(len(SHAPE_DRAWERS))]
                else:
                    w, h = choose_group_size(rng)
                    shape_fn = SHAPE_DRAWERS[rng.randrange(len(SHAPE_DRAWERS))]

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
                placed_groups.append((srow, scol, col, row, w, h, shape_fn.__name__))

                outer = (sx0 + col * icon, sy0 + row * icon, sx0 + (col + w) * icon, sy0 + (row + h) * icon)
                box = (outer[0] + gutter, outer[1] + gutter, outer[2] - gutter, outer[3] - gutter)

                category = rng.choices(categories, weights=weights)[0]
                color = shade(palette[category], rng.uniform(0.85, 1.1))
                shape_fn(draw, box, color, rng)
                symbol_count += 1

                row += h

    save_layout(day, screen_w, screen_h, icon, placed_groups)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{day}.png"
    img.save(out_path)
    return out_path, symbol_count, len(active_sectors), total_sectors, (screen_w, screen_h), icon


def main():
    day, counts, effective_visits = load_weighted_mix()
    out_path, symbol_count, filled_sectors, total_sectors, screen, icon = render(day, counts, effective_visits)
    mix_summary = ", ".join(
        f"{c}={n:.0f}" for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    print(f"Screen {screen[0]}x{screen[1]}, icon size {icon}px -> {SECTOR_COLS}x{SECTOR_ROWS} sector grid ({total_sectors} sectors)")
    print(f"As of {day} (decay-weighted, half-life {HALF_LIFE_DAYS}d): ~{effective_visits:.1f} effective visits/day across {len(counts)} categories ({mix_summary})")
    print(f"Drew {symbol_count} symbols across {filled_sectors}/{total_sectors} sectors ({filled_sectors/total_sectors:.0%})")
    print(f"Rendered {out_path}")


if __name__ == "__main__":
    main()
