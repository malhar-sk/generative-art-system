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
  `categorize.py` doesn’t hardcode categories like "stocks" or "video
  games" — it looks at whatever’s actually in your history, ranks
  domains by visit count, and turns the most-visited ones into their
  own categories automatically (named after the domain, e.g.
  `youtube.com`, `claude.ai`, `github.com`). Everything outside the top
  domains folds into `other`. This means the category set self-adjusts
  as browsing habits change — nothing to manually re-tune.
- **Category membership is stabilized with hysteresis**, not
  recomputed fresh every run: a domain only gets promoted into its own
  category once it clears the strict top-`TOP_N_DOMAINS` cutoff, but
  only gets demoted once it falls past a wider buffer
  (`TOP_N_DOMAINS + DEMOTE_BUFFER`). State lives in
  `data/category_membership.json` (gitignored, falls back to a fresh
  selection if missing/corrupt). Without this, a domain hovering right
  at the cutoff could flicker in and out of its own category — and
  therefore its own color — from one run to the next, which would read
  as a glitch, not evolution.
- The category mix feeding a render isn’t a single day’s snapshot —
  see "How it works" below for how recent days are blended together,
  and how that mix drives the piece.
- **The grid layout itself persists across renders**
  (`data/render_state.json`, gitignored) — each render inherits
  roughly 70% of the previous render's shape positions/sizes/types,
  mutating the rest, so today's piece has actual lineage from
  yesterday's rather than being a full recompute each time. Falls
  back to a fresh layout if the state file is missing, corrupt, or
  the screen/icon size changed.

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
4. **`generate_art.py`** — combines recent days into one snapshot with
   **exponential recency weighting** instead of using a single day's raw
   counts: each prior day's visits count `0.5 ** (days_ago / HALF_LIFE_DAYS)`
   toward the mix (half-life 8 days, ~90-day lookback beyond which the
   weight is negligible). That means today's render is dominated by
   roughly the last few weeks, but shifts gradually day to day rather
   than jumping around on single-day noise or lurching once every 3
   weeks. The weighted mix is renormalized back to a single-day scale
   (`effective_visits`) specifically so the coverage formula below
   still spans quiet-to-busy correctly instead of saturating once
   several weeks are blended together. Renders `data/art/<date>.png`
   (dated by the most recent *completed* day, the anchor of the decay)
   as a geometric mosaic sized to your actual screen resolution
   (detected via the Win32 API at render time, physical pixels not
   DPI-scaled logical ones, so the wallpaper is sharp). The canvas is
   divided into a fine grid of icon-sized cells (matches your
   configured Windows shell icon size, read from the registry). Symbols
   are drawn in randomly sized groups of those cells — mostly pairs and
   quads, sometimes bigger accent pieces — each one a random shape
   (triangle / quarter-circle fan / circle / semicircle / stripes /
   square) colored by a category chosen with probability proportional
   to that category's weighted share. Every group gets the same gutter
   inset regardless of size or color, so the piece reads as evenly
   spaced rather than a jumbled collage — the gutter is the negative
   space between pieces. Groups pack **column by column starting from
   the left**; how much of the screen fills is not a fixed floor or a
   forced 100%, but a smooth, uncapped function of `effective_visits`
   (`1 - e^(-effective_visits / COVERAGE_SCALE)`), so the piece visibly
   grows or shrinks day to day. Past the filled budget, a few columns
   **fade out toward the background** instead of stopping abruptly.
   Background is black; the 5-color accent palette (`ACCENT_COLORS` in
   generate_art.py) is cream `#F2E7DA`, orange `#BF7A4B`, rust
   `#B8653B`, sage `#629475`, and dark green `#3B6659` — brightened
   versions of an original cream-background palette (`#F2E7DB` /
   `#C07A4A` / `#9B5B3A` / `#4F6B5A` / `#23312B`), since the two
   darkest colors would have nearly vanished against true black. Each
   category hashes to one of the five accents, so the same domain gets
   a consistent-ish color across different days' pieces.
5. **`set_wallpaper.ps1`** — sets the newest PNG in `data/art/` as the
   Windows desktop wallpaper (Fill style), so the piece is the delivery
   surface — nothing to open manually.
6. **`prune_archive.py`** — every render is dated
   (`data/art/<date>.png`), so nothing gets overwritten day to day —
   but left alone that archive grows one PNG forever. This keeps every
   render from the last 90 days, and thins anything older down to one
   per ISO week (oldest render in each week survives), so a long-run
   timelapse stays possible without unbounded disk growth.
7. **`run_export.ps1`** — chains all six steps above. This is what a
   daily Windows Scheduled Task (`GenerativeArtSystem-BraveHistoryExport`)
   runs automatically at 9 AM, so the pipeline refreshes without
   manual intervention.

All of `data/` (raw history, CSVs, rendered art) is gitignored — none
of it is committed. Only the scripts that produce it are.

## Favoriting a render

**`heart_widget.py`** is a separate, always-running small program (not
part of the daily pipeline) — a borderless heart button pinned to the
top-right corner of the screen. Click it to copy whatever render is
*currently* the wallpaper into a dedicated folder,
`Pictures\GenerativeArtFavorites\` — separate from the automatic
`data/art/` archive, which keeps every render regardless. This folder
only holds what you deliberately hearted.

Hearting is a once-a-day action, not a toggle: after you click it, the
button hides itself for the rest of that day and only reappears once
tomorrow's render becomes current (checked once a minute). If the
process restarts mid-day after you've already hearted that render, it
comes back up already hidden rather than re-showing.

It stays out of the way of other apps without ever being "always on
top": it's an overrideredirect window, so it never shows up in the
taskbar or Alt-Tab (no normal way to bring it forward), and instead of
pinning itself above everything, it periodically re-lowers itself to
the bottom of the window stack (once a second). Any app you open or
click naturally ends up in front of it within about a second. This was
chosen over reparenting into Explorer's `WorkerW` window (the
technique interactive-wallpaper tools use for true desktop-layer
attachment) after testing showed `WorkerW` discovery is unreliable
across Windows sessions -- it depends on Explorer's undocumented
internal window structure, which varies by version/session (confirmed
failing in two different environments during development). Lowering
the window is a plain, fully-supported stacking operation with no such
dependency, so it behaves the same everywhere.

It uses a solid black background matching the wallpaper's own
background color rather than true window transparency — Windows'
`-transparentcolor` trick breaks on anti-aliased text/emoji (a single
chroma key ends up matching some of a glyph's own blended edge pixels,
producing a visible hatched artifact), so this sidesteps that entirely
by just blending in. Works especially well in the top-right corner
specifically, since that's also the last area the mosaic's
left-to-right fill order ever reaches.

Launch it manually whenever you want it active:
```
pythonw scripts\heart_widget.py
```
To have it start automatically every time you log into Windows, run
`scripts\register_heart_widget_task.ps1` yourself. That's a separate,
opt-in step rather than something the pipeline sets up on its own —
logon-triggered auto-start is a more invasive, persistent capability
than a scheduled daily task, worth a deliberate decision on your end.

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

## Design note: evolving over time

Council-reviewed decision (see project history for the full session):
rejected batching to one render every ~3 weeks, since that's a slower
snapshot, not evolution — you'd notice it *less*, not more. Built
instead, in order of the council's recommendation:

1. The daily 9am render reads a decay-weighted recent-history window
   (see "How it works" step 4), so the ~3-week feel comes from a
   smooth, continuously-updating blend rather than an infrequent jump.
2. The coverage formula runs on that window's renormalized average,
   not a raw multi-day sum, so it doesn't saturate near full-screen
   every render.
3. Category-to-color identity is stabilized with hysteresis (see
   "Data source" above) so it can't flicker.
4. The council's strongest point: decay-weighting alone is still a
   fresh recompute from raw history every time, not true persistence.
   A wallpaper only really "evolves" once today's render is a function
   of *yesterday's render*. The grid layout now persists across
   renders for exactly this reason (see "Data source" above) — today's
   piece has actual lineage from yesterday's, not just fresh data
   poured into a fresh recompute.
5. Renders archive instead of overwriting, with weekly thinning past
   90 days (see "How it works" step 6), so a long-run timelapse stays
   possible later without committing to building one now.

## Next ideas (not built yet)

- Something that actually uses the archive — a timelapse/GIF stitched
  from `data/art/`, or a quarterly grid tiling recent renders into one
  "generative memoir" piece.
- Tune `TOP_N_DOMAINS` / `DEMOTE_BUFFER` (categorize.py) and
  `COVERAGE_SCALE` / `HALF_LIFE_DAYS` / `GUTTER_FRACTION` /
  `REUSE_PROBABILITY` (generate_art.py) as real usage patterns become
  clearer.
- Consider a secondary/fallback delivery surface beyond wallpaper (a
  local gallery folder?) — there's still no forcing function pulling
  this back into view otherwise.
