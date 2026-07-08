# Podcast Director — audio-first multicam auto-switcher

Turns a set of pre-synced podcast camera feeds into a single angle-switched
master, driven by who's talking. Inspired by the "Conformist" tool from the
Upgrade/ATP-style workflow, but built around **Frank's** 3-stream Wistia setup
(Tim one-shot, Frank one-shot, composite two-shot) and edited audio-first.

No ML, no NLE in the cut path — just ffmpeg + Python stdlib + numpy. Two-shot ==
composite, which is always in sync, so dynamism costs zero sync risk.

## Pipeline

1. **Source** — 3 feeds pulled from Wistia (per-participant camera + composite).
   Frank's camera dropped/reconnected mid-record, so his feed arrives as **4
   native chunks**; the stitched "backup" file smears them together and must NOT
   be used (its paste seams cause non-linear sync drift).
2. **Sync** (GCC-PHAT against the composite audio clock, applied as +offset seek):
   - Frank: each of the 4 chunks placed at its filename composite-timecode, each
     with its **own constant offset** (chunk offsets ~4.98 / 5.11 / 5.35s).
   - Tim: one continuous feed, **linear offset fit** across the episode.
   - Composite: the shared clock + audio bed.
3. **Gate** — competitive RMS gating per 50 ms frame: loudest-by-margin wins a
   one-shot; both close = two-shot; both quiet = safe wide. Robust to mic bleed.
   In camera-drop gaps Frank is forced silent, so it falls to Tim/composite.
4. **Grammar** — hangover, min-shot (1.2s), frame-snap, plus the **dynamic
   two-shot** layer (see below).
5. **Assemble** — each segment sourced from the correct original via input-seek
   (fast + frame-accurate). **Frame-exact**: every segment gets an integer frame
   count on one global grid so parts sum to exactly the audio length — zero
   cumulative sync drift over a long render.

## Dynamic two-shot (tasteful, not metronomic)

Three motivated sources, layered:
- **overlap** — both genuinely talking within `--overlap` dB.
- **reaction** — the listener audibly reacts during the other's solo.
- **breather** — eligible only after `--min-gap` s since the last two-shot, then
  FIRES at the next natural pause (a breath); hard backstop for true monologues.
  Spacing is therefore irregular and always lands on a beat.

Locked-in taste setting: `--min-gap 12 --two-len 1.6` → ~10% two-shot.

## Files

- `chunks.py`      — chunk resolver + per-chunk offset probe (GCC-PHAT).
- `offset.py`      — envelope cross-correlation sync finder.
- `gate.py`        — competitive gating detector.
- `render_real.py` — shot-grammar + (base) assembler.
- `render_full.py` — full/windowed render: sync model, gap handling, frame-exact
                     assembly. `--a/--b` window, `--b 0` = full episode.
- `render_full2.py`— dynamic-two-shot Director (imports render_full). Main entry
                     for the current deliverable.

## Run

    # full episode, locked settings
    python3 render_full2.py --a 0 --b 0 --min-gap 12 --two-len 1.6 --out master.mp4

## Known next steps

- Auto-pull intake from Wistia (reverse-engineer the per-feed zip download).
- Content-edit conform: after audio edit in Audition, ripple the single switched
  track to the edited timeline.
- Optional: tune shot balance (currently Tim-heavy on this episode).
