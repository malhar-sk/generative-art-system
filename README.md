# Generative Art System

Turn everyday data (starting with Brave browsing history) into
generated visual art, so novelty-seeking gets satisfied by *creation*
instead of scrolling.

## Status

Actively being built. (Previously queued behind other projects in the
"replace doomscrolling" lineup per an earlier LLM Council pass — that
ordering is no longer a hard gate; build order is whatever's useful.)

## Architecture decision

- **No shared backend. No Neon Postgres for this project.**
- Even the standardized `(timestamp, source, value, tags)` shape used
  by other projects in this lineup is, at most, a natural *input* this
  system could render — it is not something this system needs to write
  to. This stays a standalone, read-only consumer of data, not another
  writer into shared infra.

## Stack (decided)

**Python + Pillow**, rendering to static PNGs. Simple, scriptable, easy
to run on a schedule and dump output to a local folder.

## Data source (decided)

- **Source: Brave browsing/search history**, auto-exported locally on a
  schedule (see `scripts/`).
- **Categorization: simple keyword/domain rules**, sorting visits into
  topic buckets (stocks, video games, food, photos, stationary,
  minecraft, and an `other` catch-all). Deliberately not using an LLM
  classifier for this — misclassified or mixed-bucket entries are fine.
  The goal is *variety* in the category mix driving the visuals, not
  classification precision.
- The category mix (which buckets dominate a given day, how the mix
  shifts over time) is the real-data signal behind the piece — category
  → color, proportion → how much of the ring that color claims. See
  "How it works" below for the actual rendering approach.

## How it works

Pipeline, in order, all under `scripts/`:

1. **`export_brave_history.ps1`** — copies Brave's `History` SQLite DB
   out of its locked profile folder into `data/brave_history/`. Copying
   (rather than opening it directly) is what lets this run even while
   Brave is open.
2. **`parse_brave_history.py`** — reads that copy, writes a flat
   per-URL summary to `data/history.csv` (url, title, visit_count,
   last_visit).
3. **`categorize.py`** — reads the same SQLite copy's `visits` table
   (one row per visit event, not just per URL), applies the
   keyword/domain rules to each visit, and writes:
   - `data/categorized_visits.csv` — every visit tagged with a category
   - `data/daily_category_mix.csv` — visit counts per category per day
4. **`generate_art.py`** — takes the most recent day's category mix
   from `daily_category_mix.csv` and renders `data/art/<date>.png`: a
   ring built from ~720 thin wedges swept around a center point. Each
   wedge's *color* comes from which category's share of the day it
   falls into (arranged in a fixed order so colors stay legible day to
   day); each wedge's *radius* is offset by a handful of sine
   harmonics seeded from the date string, so the ring's edge is never
   perfectly circular — it undulates. This is the seeded-variation
   layer described below: real data drives the color bands, the seeded
   noise guarantees the edge always has visible movement even on a
   flat/quiet data day.
5. **`run_export.ps1`** — chains all four steps above. This is what a
   daily Windows Scheduled Task (`GenerativeArtSystem-BraveHistoryExport`)
   runs automatically at 9 AM, so the pipeline refreshes without
   manual intervention.

All of `data/` (raw history, CSVs, rendered art) is gitignored — none
of it is committed. Only the scripts that produce it are.

## Design note: determinism vs. novelty

If the data-to-visual transform were purely deterministic, quiet/flat
data days (barely any browsing, or one category dominating) would
produce flat, boring art — undermining the whole point of satisfying
novelty-seeking. That's why `generate_art.py`'s ring radius is offset
by noise harmonics seeded on the date: real data still visibly steers
the color composition, but the seeded variation guarantees the shape
itself is never flat, independent of how eventful the day's browsing
was.

## Next ideas (not built yet)

- Expand/tune the category rules as real gaps show up in
  `categorized_visits.csv` (categories currently: stocks, video_games,
  minecraft, food, photos, stationary, other).
- Multi-day views (a strip or grid of rings across a week/month) to
  make the undulation-over-time more visible than a single day's PNG.
- Decide on a delivery surface (wallpaper? local gallery folder?) —
  there's still no forcing function pulling this back into view, so
  the delivery surface is doing all the work of getting it seen.
