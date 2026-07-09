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

- `render_ep.py`    — current entry point: feed discovery + episode render driver.
- `assemble.py`     — full/windowed render core: sync model, gap handling,
                      frame-exact assembly. `--a/--b` window, `--b 0` = full episode.
- `twoshot.py`      — dynamic-two-shot Director layer (drives assemble).
- `shot_grammar.py` — shot-grammar + base assembler.
- `chunks.py`       — chunk resolver + per-chunk offset probe (GCC-PHAT).
- `gate.py`         — competitive gating detector.
- `syncfit.py`      — robust offset-model fitting (the sync core).
- `vidsync.py` / `vidsync_map.py` — video-side sync mapping.
- `verify_video.py` — the lip-sync verification gate (EBU R37 tolerance, 0.12 s).
- `legacy/`         — the archaeology that led here; kept for reference, not runnable
                      in place (see legacy/README.md).

Coverage note: `render_ep.py` always models Frank as ONE continuous chunk
(camera backup preferred), so that's the path `bwg test` regresses. The
multi-chunk machinery (`parse_chunks`, per-chunk offsets, gap regions) is
dormant — nothing builds a multi-entry `CHUNKS` list since the historical
`real/chunks/` layout went away. It goes live (and needs a chunk-boundary
test window) the day an episode arrives with a dropped camera and no
continuous backup.

## Run

    # full episode via the current entry point
    python3 render_ep.py --feeds <feeds_dir> --out master.mp4 --a 0 --b 0

    # or through the orchestrator (adds the verify gate):
    ../bin/bwg render <feeds_dir> --full

## Known next steps

- ~~Auto-pull intake from Wistia~~ — done; see `../bin/wistia-pull-feeds.py` and `bwg pull`.
- Content-edit conform: after audio edit in Audition, ripple the single switched
  track to the edited timeline.
- Optional: tune shot balance (currently Tim-heavy on this episode).
