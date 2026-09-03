"""Categorize Brave history visits by domain -- fully data-driven, no fixed
category list. The most-visited domains in your history each become their
own category (named after the domain); everything else falls into "other".
Categories adapt automatically as your browsing changes, no manual rules
to maintain.

Domain-to-category membership uses hysteresis (see DEMOTE_BUFFER below) so
a domain hovering right at the rank cutoff doesn't flicker in and out of
its own category -- and therefore its own color -- from one run to the
next. Promotion into a category is immediate (a new domain crossing the
strict cutoff just adds a color); demotion is delayed until a domain falls
well past the cutoff, since losing an established color identity is the
jarring case, not gaining a new one.

Reads the SQLite copy made by export_brave_history.ps1. Writes:
  data/categorized_visits.csv     -- every visit tagged with a category
  data/daily_category_mix.csv     -- visit counts per category per day
  data/category_membership.json   -- hysteresis state (which domains are
                                      confirmed categories right now)
"""
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "brave_history" / "History.sqlite"
VISITS_OUT = ROOT / "data" / "categorized_visits.csv"
DAILY_OUT = ROOT / "data" / "daily_category_mix.csv"
CATEGORY_STATE_PATH = ROOT / "data" / "category_membership.json"

WEBKIT_EPOCH = datetime(1601, 1, 1)

# How many domains clear the strict cutoff to be promoted into their own
# category; the rest fold into "other".
TOP_N_DOMAINS = 14
# A previously confirmed category only demotes once its rank falls past
# TOP_N_DOMAINS + DEMOTE_BUFFER, not the moment it dips below TOP_N_DOMAINS.
DEMOTE_BUFFER = 5


def registrable_domain(url: str) -> str:
    """Simple last-two-labels heuristic (youtube.com from www.youtube.com,
    openai.com from chat.openai.com). Not accurate for multi-part TLDs like
    co.uk, but good enough for a signal that's meant to be varied, not precise."""
    netloc = urlparse(url).netloc.lower().split(":")[0]
    if not netloc:
        return "other"
    parts = netloc.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else netloc


def webkit_to_datetime(webkit_ts: int) -> datetime:
    return WEBKIT_EPOCH + timedelta(microseconds=webkit_ts)


def load_confirmed_domains() -> set:
    try:
        with CATEGORY_STATE_PATH.open(encoding="utf-8") as f:
            return set(json.load(f).get("confirmed_domains", []))
    except (FileNotFoundError, OSError, ValueError):
        return set()  # missing or corrupt state -> safe fallback, not a crash


def save_confirmed_domains(domains: set) -> None:
    CATEGORY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CATEGORY_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump({"confirmed_domains": sorted(domains)}, f, indent=2)


def select_categories(domain_counts: Counter) -> set:
    ranked = [domain for domain, _ in domain_counts.most_common()]
    promote_zone = set(ranked[:TOP_N_DOMAINS])
    keep_zone = set(ranked[:TOP_N_DOMAINS + DEMOTE_BUFFER])

    previously_confirmed = load_confirmed_domains()
    confirmed = (previously_confirmed & keep_zone) | promote_zone
    if len(confirmed) > TOP_N_DOMAINS + DEMOTE_BUFFER:
        confirmed = set(ranked[:TOP_N_DOMAINS + DEMOTE_BUFFER])  # defensive cap

    save_confirmed_domains(confirmed)
    return confirmed


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"No exported history found at {DB_PATH}. Run export_brave_history.ps1 first.")

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT urls.url, urls.title, visits.visit_time
        FROM visits
        JOIN urls ON visits.url = urls.id
        ORDER BY visits.visit_time DESC
    """).fetchall()
    con.close()

    domain_counts = Counter(
        registrable_domain(url) for url, _, visit_time in rows if visit_time
    )
    domain_counts.pop("other", None)  # empty-netloc visits never claim a category slot
    top_domains = select_categories(domain_counts)

    def categorize(url: str) -> str:
        domain = registrable_domain(url)
        return domain if domain in top_domains else "other"

    daily_counts = defaultdict(lambda: defaultdict(int))

    VISITS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with VISITS_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "visit_time", "category"])
        for url, title, visit_time in rows:
            if not visit_time:
                continue
            when = webkit_to_datetime(visit_time)
            category = categorize(url)
            writer.writerow([url, title, when, category])
            daily_counts[when.date().isoformat()][category] += 1

    all_categories = sorted({c for day in daily_counts.values() for c in day} | {"other"})
    with DAILY_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date"] + all_categories + ["total"])
        for day in sorted(daily_counts):
            counts = daily_counts[day]
            total = sum(counts.values())
            writer.writerow([day] + [counts.get(c, 0) for c in all_categories] + [total])

    print(f"Categorized {len(rows)} visits across {len(top_domains)} domain-categories -> {VISITS_OUT}")
    print(f"Daily category mix -> {DAILY_OUT}")


if __name__ == "__main__":
    main()
