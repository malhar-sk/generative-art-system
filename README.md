# Generative Art System

Turn everyday data (weather, stock prices, text messages, etc.) into
generated visual art, so novelty-seeking gets satisfied by *creation*
instead of scrolling.

## Status

**QUEUED LAST, OPTIONAL — do not start real implementation until the
first 3 projects are built and sticking as habits.**

## Where this sits in the build queue

Build order across the four "replace doomscrolling" projects, per the
LLM Council's decision:

1. Doomscrolling Tracker (building now)
2. System Detective
3. Personal API
4. **Generative Art System** (this project — last)

### Why it's last, and why it's cuttable

The council explicitly flagged this as the weakest of the four projects
for the stated goal, for one core reason: **it has no forcing
function.** A tracker or a monitor breaks visibly, or goes silently
unattended, if it's neglected — someone notices. This project has no
equivalent: nobody notices if it doesn't run. There's no unattended
state to fail out of, so there's nothing pulling it back into use once
novelty wears off.

Given that, the council's instructions were direct:

- Treat this as **optional/cuttable, not a core deliverable**.
- Build it last, and only if the first three projects are actually
  sticking as habits — not just built, but *used*.
- **Ship nothing else beyond the Doomscrolling Tracker until it has run
  unattended for 7 consecutive days with zero intervention.** This
  project should not get real scaffold code before that bar is cleared.

## Architecture decision (applies if/when this project's turn comes)

- **No shared backend. No Neon Postgres for this project.**
- Even the standardized `(timestamp, source, value, tags)` shape used
  by the other three projects is, at most, a natural *input* this
  system could render — it is not something this system needs to write
  to. This stays a standalone, read-only consumer of data, not another
  writer into shared infra.

## Brainstormed stack / rendering options (not decided — pick when work starts)

A few realistic directions to evaluate once this project is actually
picked up:

1. **Python + Pillow, rendering to static images.** Pull data (e.g. a
   weather API), map fields to visual parameters (color, shape,
   density), render a PNG. Simple, scriptable, easy to cron and dump
   to a folder or wallpaper slot. Weakest on interactivity.
2. **HTML canvas / SVG page (client-side JS).** A single static page
   that fetches data and draws with Canvas or SVG. Easy to make
   interactive or animated, easy to view in a browser, no server
   needed if data can be fetched client-side or pre-baked into a JSON
   file.
3. **p5.js sketch (creative-coding-native).** Purpose-built for exactly
   this kind of data-to-visual mapping, large ecosystem of examples,
   runs in-browser like option 2 but with a much richer drawing/animation
   vocabulary out of the box. Worth a look before defaulting to raw canvas.

## Design note: determinism vs. novelty

The council flagged a specific blind spot that any implementation needs
to design around: if the data-to-visual transform is purely
deterministic, quiet/flat data days (e.g. unremarkable weather, a flat
stock, no texts) will produce flat, boring art. That directly
undermines the "novelty" payoff the whole idea depends on — the point
was to satisfy novelty-seeking, and a deterministic mapping starves
that on exactly the days it's needed most.

Mitigation to design in from the start, not bolt on later: layer
**controlled procedural variation** on top of the real-data mapping —
for example, seed a noise/variation function by the date (or another
stable-but-changing key) so every day's piece has some guaranteed
visual movement, independent of how eventful the underlying data was.
Real data should still visibly steer the output; the seeded variation
is there to guarantee the output is never flat, not to drown the data
signal out.

## When you pick this back up (if ever)

- [ ] Confirm Doomscrolling Tracker has run unattended for 7+
      consecutive days with zero intervention.
- [ ] Confirm System Detective and Personal API are both built *and*
      being used as habits, not just sitting installed.
- [ ] Re-run this idea through the council (or at least sanity-check
      it solo) — has anything changed about whether it's worth
      building at all?
- [ ] Pick a data source and a rendering stack from the brainstormed
      options above (or a better one found in the meantime).
- [ ] Design the seeded-variation layer *before* writing the
      deterministic data mapping, so novelty isn't an afterthought.
- [ ] Decide on an output/delivery surface (wallpaper? local gallery
      folder? a page you open manually?) — remember there's no forcing
      function here, so the delivery surface is doing all the work of
      getting this seen at all.
