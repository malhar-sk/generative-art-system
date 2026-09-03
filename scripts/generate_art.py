"""Render the day's category mix as a wavy ring PNG.

Reads the most recent row of data/daily_category_mix.csv (written by
categorize.py). Each category's share of the day becomes an arc of the
ring, colored consistently; the ring's radius is offset by a handful of
sine harmonics seeded from the date string, so the edge always
undulates -- real data steers the color composition, seeded noise
guarantees the shape is never flat even on a quiet data day.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from categorize import CATEGORY_RULES  # single source of truth for category order

ROOT = Path(__file__).resolve().parent.parent
DAILY_MIX = ROOT / "data" / "daily_category_mix.csv"
OUT_DIR = ROOT / "data" / "art"

SIZE = 1000
CENTER = SIZE // 2
BASE_RADIUS = SIZE * 0.28
NOISE_AMPLITUDE = SIZE * 0.12
SLICES = 720

CATEGORY_ORDER = [name for name, _ in CATEGORY_RULES] + ["other"]
OTHER_COLOR = (149, 165, 166)


def build_palette(categories):
    """Evenly spaced hues around the color wheel, one per non-'other' category,
    so the palette stays distinct no matter how many rules get added later."""
    named = [c for c in categories if c != "other"]
    palette = {"other": OTHER_COLOR}
    for i, category in enumerate(named):
        hue = i / max(len(named), 1)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.85)
        palette[category] = (int(r * 255), int(g * 255), int(b * 255))
    return palette


CATEGORY_COLORS = build_palette(CATEGORY_ORDER)


def load_latest_mix():
    """Use the most recent *completed* day, not today-so-far -- today's
    row is always partial (the day isn't over yet), so rendering it
    would produce a misleadingly sparse piece. This also matches the
    daily-9am schedule: render yesterday's full day when you wake up."""
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
    counts = {c: int(latest[c]) for c in categories}
    total = sum(counts.values()) or 1
    proportions = {c: counts[c] / total for c in categories}
    return day, proportions


def seeded_noise_fn(seed_str: str):
    """A handful of seeded sine harmonics -- guarantees every day's piece
    has visible shape variation, independent of how eventful the
    underlying data was."""
    rng = random.Random(int(hashlib.sha256(seed_str.encode()).hexdigest(), 16))
    harmonics = [
        (rng.randint(2, 7), rng.uniform(0, math.tau), rng.uniform(0.3, 1.0))
        for _ in range(4)
    ]

    def radius_offset(theta: float) -> float:
        return sum(
            weight * math.sin(freq * theta + phase) for freq, phase, weight in harmonics
        ) / len(harmonics)

    return radius_offset


def render(day: str, proportions: dict) -> Path:
    img = Image.new("RGB", (SIZE, SIZE), (18, 18, 22))
    draw = ImageDraw.Draw(img)
    noise = seeded_noise_fn(day)

    ordered = [c for c in CATEGORY_ORDER if proportions.get(c, 0) > 0] or CATEGORY_ORDER
    boundaries = []
    acc = 0.0
    for c in ordered:
        acc += proportions.get(c, 0)
        boundaries.append((c, acc))
    boundaries[-1] = (boundaries[-1][0], 1.0)  # absorb float rounding

    prev_point = None
    for i in range(SLICES + 1):
        theta = math.tau * i / SLICES
        frac = i / SLICES
        category = next(c for c, b in boundaries if frac <= b + 1e-9)
        radius = BASE_RADIUS + NOISE_AMPLITUDE * noise(theta)
        point = (CENTER + radius * math.cos(theta), CENTER + radius * math.sin(theta))
        if prev_point is not None:
            color = CATEGORY_COLORS.get(category, OTHER_COLOR)
            draw.polygon([(CENTER, CENTER), prev_point, point], fill=color)
        prev_point = point

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{day}.png"
    img.save(out_path)
    return out_path


def main():
    day, proportions = load_latest_mix()
    out_path = render(day, proportions)
    mix_summary = ", ".join(f"{c}={p:.0%}" for c, p in proportions.items() if p > 0)
    print(f"Category mix for {day}: {mix_summary}")
    print(f"Rendered {out_path}")


if __name__ == "__main__":
    main()
