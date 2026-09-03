"""Prune data/art/ so the render archive doesn't grow unbounded forever.

Every render is already dated (data/art/<date>.png), so nothing gets
overwritten day to day -- but with no pruning that archive would just
grow one PNG per day forever. This keeps every render from the last
RECENT_DAYS days, and thins anything older than that down to one
render per ISO week (the oldest render in each week survives, the
rest are deleted) -- so a long-run timelapse stays possible without
unbounded disk growth.
"""
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DIR = ROOT / "data" / "art"

RECENT_DAYS = 90
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.png$")


def main():
    if not ART_DIR.exists():
        return

    dated = []
    for path in ART_DIR.iterdir():
        m = DATE_RE.match(path.name)
        if m:
            dated.append((date.fromisoformat(m.group(1)), path))
    if not dated:
        return

    dated.sort(key=lambda t: t[0])
    newest_day = dated[-1][0]
    cutoff = newest_day - timedelta(days=RECENT_DAYS)

    kept_weeks = set()
    removed = 0
    for day, path in dated:
        if day > cutoff:
            continue  # within the recent window -- always keep
        week_key = day.isocalendar()[:2]  # (iso_year, iso_week)
        if week_key in kept_weeks:
            path.unlink()
            removed += 1
        else:
            kept_weeks.add(week_key)

    if removed:
        print(f"Pruned {removed} archived render(s) older than {RECENT_DAYS} days (thinned to weekly).")
    else:
        print("Archive pruning: nothing to prune yet.")


if __name__ == "__main__":
    main()
