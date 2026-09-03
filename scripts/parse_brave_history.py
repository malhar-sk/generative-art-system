"""Extract visits from the exported Brave History SQLite copy into a CSV.

Run export_brave_history.ps1 first to produce data/brave_history/History.sqlite,
then run this to turn it into data/history.csv (url, title, visit_count,
last_visit as a real timestamp instead of Chromium's WebKit epoch).
"""
import csv
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "brave_history" / "History.sqlite"
OUT_PATH = ROOT / "data" / "history.csv"

WEBKIT_EPOCH = datetime(1601, 1, 1)


def webkit_to_datetime(webkit_ts: int) -> datetime:
    return WEBKIT_EPOCH + timedelta(microseconds=webkit_ts)


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"No exported history found at {DB_PATH}. Run export_brave_history.ps1 first.")

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC"
    ).fetchall()
    con.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "visit_count", "last_visit"])
        for url, title, visit_count, last_visit_time in rows:
            when = webkit_to_datetime(last_visit_time) if last_visit_time else ""
            writer.writerow([url, title, visit_count, when])

    print(f"Wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
