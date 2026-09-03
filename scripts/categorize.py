"""Categorize Brave history visits into topic buckets via simple keyword/domain rules.

Deliberately crude: substring matching against domain + title, first rule
that matches wins. Misclassification and category mixing are fine here --
the generative art system wants variety in the category signal, not
classification precision.

Reads the SQLite copy made by export_brave_history.ps1. Writes:
  data/categorized_visits.csv  -- every visit tagged with a category
  data/daily_category_mix.csv  -- visit counts per category per day
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "brave_history" / "History.sqlite"
VISITS_OUT = ROOT / "data" / "categorized_visits.csv"
DAILY_OUT = ROOT / "data" / "daily_category_mix.csv"

WEBKIT_EPOCH = datetime(1601, 1, 1)

# Ordered rules: first category whose domain/keyword list matches wins.
# Order matters where categories could overlap (e.g. minecraft before
# the broader video_games bucket). Add more buckets here as gaps show
# up in categorized_visits.csv -- rules are meant to grow over time.
CATEGORY_RULES = [
    ("minecraft", {
        "domains": ["minecraft.net", "curseforge.com", "modrinth.com", "planetminecraft.com"],
        "keywords": ["minecraft"],
    }),
    ("video_games", {
        "domains": ["steampowered.com", "steamcommunity.com", "epicgames.com", "ign.com",
                    "gamespot.com", "twitch.tv", "playstation.com", "xbox.com", "nintendo.com",
                    "roblox.com", "itch.io"],
        "keywords": ["gameplay", "walkthrough", "speedrun", " ps5", "xbox"],
    }),
    ("stocks", {
        "domains": ["finance.yahoo.com", "marketwatch.com", "bloomberg.com", "cnbc.com",
                    "robinhood.com", "tradingview.com", "nasdaq.com", "investing.com"],
        "keywords": ["stock", "ticker", "dividend", "earnings", "nasdaq", "s&p 500"],
    }),
    ("food", {
        "domains": ["doordash.com", "ubereats.com", "grubhub.com", "allrecipes.com",
                    "food.com", "seriouseats.com"],
        "keywords": ["recipe", "restaurant menu", "food delivery"],
    }),
    ("photos", {
        "domains": ["instagram.com", "flickr.com", "unsplash.com", "500px.com",
                    "photos.google.com"],
        "keywords": ["photography", "lightroom", "camera review"],
    }),
    ("stationary", {
        "domains": ["jetpens.com", "papersource.com"],
        "keywords": ["stationery", "stationary", "fountain pen", "washi tape", "planner"],
    }),
    ("ai_tools", {
        "domains": ["claude.ai", "chatgpt.com", "chat.openai.com", "openai.com",
                    "colab.research.google.com", "notebooklm.google.com", "gamma.app"],
        "keywords": ["chatgpt", "claude ai"],
    }),
    ("video", {
        "domains": ["youtube.com", "moewalls.com"],
        "keywords": ["youtube"],
    }),
    ("coding", {
        "domains": ["github.com", "stackoverflow.com", "localhost", "npmjs.com", "pypi.org"],
        "keywords": ["pull request", "localhost", "commit "],
    }),
    ("productivity", {
        "domains": ["mail.google.com", "accounts.google.com", "drive.google.com",
                    "docs.google.com", "calendar.google.com"],
        "keywords": ["gmail", "google docs", "google drive"],
    }),
    ("learning", {
        "domains": ["coursera.org", "wikipedia.org", "khanacademy.org", "edx.org"],
        "keywords": ["course", "lecture", "wikipedia"],
    }),
    ("search", {
        "domains": ["search.brave.com"],
        "keywords": [],
    }),
    ("social", {
        "domains": ["linkedin.com", "reddit.com", "x.com", "twitter.com"],
        "keywords": [],
    }),
    ("travel", {
        "domains": ["goindigo.in", "makemytrip.com", "airbnb.com", "booking.com"],
        "keywords": ["flight booking", "itinerary"],
    }),
]


def categorize(url: str, title: str) -> str:
    domain = urlparse(url).netloc.lower()
    haystack = f"{domain} {title or ''}".lower()
    for category, rule in CATEGORY_RULES:
        if any(d in domain for d in rule["domains"]):
            return category
        if any(k in haystack for k in rule["keywords"]):
            return category
    return "other"


def webkit_to_datetime(webkit_ts: int) -> datetime:
    return WEBKIT_EPOCH + timedelta(microseconds=webkit_ts)


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

    daily_counts = defaultdict(lambda: defaultdict(int))

    VISITS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with VISITS_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "visit_time", "category"])
        for url, title, visit_time in rows:
            if not visit_time:
                continue
            when = webkit_to_datetime(visit_time)
            category = categorize(url, title)
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

    print(f"Categorized {len(rows)} visits -> {VISITS_OUT}")
    print(f"Daily category mix -> {DAILY_OUT}")


if __name__ == "__main__":
    main()
