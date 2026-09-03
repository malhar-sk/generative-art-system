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
- **Categorization: adaptive, domain-driven, not a fixed type list.**
  `categorize.py` doesn't hardcode categories like "stocks" or "video
  games" — it looks at whatever's actually in your history, ranks
  domains by visit count, and turns the most-visited ones into their
  own categories automatically (named after the domain, e.g.
  `youtube.com`, `claude.ai`, `github.com`). Everything outside the top
  domains folds into `other`. This means the category set self-adjusts
  as browsing habits change — nothing to manually re-tune.
- The category mix (which domains dominate a given day, how much
  browsing happened at all) is the real-data signal behind the piece —
  category → shape color, volume → how much of the canvas fills up.
  See "How it works" below for the actual rendering approach.

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
   (one row per visit event, not just per URL), ranks domains by visit
   count and picks the top ones as categories (see "Data source"
   above), and writes:
   - `data/categorized_visits.csv` — every visit tagged with a category
   - `data/daily_category_mix.csv` — visit counts per category per day
4. **`generate_art.py`** — takes the most recent *completed* day's
   category counts and renders `data/art/<date>.png` as a geometric
   mosaic sized to your actual screen resolution (detected via the
   Win32 API at render time, physical pixels not DPI-scaled logical
   ones, so the wallpaper is sharp). The canvas is divided into a fine
   grid of icon-sized cells (matches your configured Windows shell icon
   size, read from the registry). Symbols are drawn in randomly sized
   groups of those cells — mostly pairs and quads, sometimes bigger
   accent pieces — each one a random shape (triangle / quarter-circle
   fan / circle / semicircle / stripes / square) colored by a category
   chosen with probability proportional to that category's share of
   the day. Every group gets the same gutter inset regardless of size
   or color, so the piece reads as evenly spaced rather than a jumbled
   collage — the gutter is the negative space between pieces. Groups
   pack **column by column starting from the left**; how much of the
   screen fills is not a fixed floor or a forced 100%, but a smooth,
   uncapped function of how much browsing happened that day (`1 -
   e^(-visits / COVERAGE_SCALE)`), so the piece visibly grows or
   shrinks day to day. Past the filled budget, a few columns **fade out
   toward the background** instead of stopping abruptly. Colors are
   hash-derived per category name, so the same domain gets a
   consistent-ish color across different days' pieces.
5. **`set_wallpaper.ps1`** — sets the newest PNG in `data/art/` as the
   Windows desktop wallpaper (Fill style), so the piece is the delivery
   surface — nothing to open manually.
6. **`run_export.ps1`** — chains all five steps above. This is what a
   daily Windows Scheduled Task (`GenerativeArtSystem-BraveHistoryExport`)
   runs automatically at 9 AM, so the pipeline refreshes without
   manual intervention.

All of `data/` (raw history, CSVs, rendered art) is gitignored — none
of it is committed. Only the scripts that produce it are.

## Design note: determinism vs. novelty

If the data-to-visual transform were purely deterministic, quiet/flat
data days (barely any browsing, or one category dominating) would
produce flat, boring art — undermining the whole point of satisfying
novelty-seeking. `generate_art.py` handles this two ways: shape choice
and fill order within the data-driven budget are seeded per-day random
(not a fixed layout), and on a quiet day the fade-out zone still gives
the piece visible texture at the boundary rather than just stopping
dead. Real data still steers the color composition and how much of the
canvas fills; the seeded randomness guarantees the arrangement is never
the same twice.

## Next ideas (not built yet)

- Tune `TOP_N_DOMAINS` (categorize.py) and `COVERAGE_SCALE` /
  `GUTTER_FRACTION` (generate_art.py) as real usage patterns become
  clearer.
- Multi-day views (a strip or grid of mosaics across a week/month) to
  make change over time more visible than a single day's PNG.
- Consider a secondary/fallback delivery surface beyond wallpaper (a
  local gallery folder?) — there's still no forcing function pulling
  this back into view otherwise.
