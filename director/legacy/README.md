# director/legacy

Historical iterations of the sync + render pipeline. Not the current path —
`director/render_ep.py` is. Kept because these files carry the *reasoning*
behind the working algorithm and shouldn't be lost when the workspace scratch
dir is cleaned up.

## The sync algorithm (why PHAT files matter)

The lip-sync gate in `../verify_video.py` is built on **GCC-PHAT** (Generalized
Cross-Correlation with Phase Transform) — the same technique used in acoustic
source localization. `phat.py` and `finephat.py` are the standalone correlation
math; `probe_offsets.py` is the harness that sweeps offsets to find the sync
point. Without these files, `verify_video.py` still runs, but the math looks
like a black box.

## The render iteration chain

- `render_full.py` — first full-episode chunk-aware render. Docstring
  documents the sync model (GCC-PHAT offsets applied as `+offset` seeks).
- `render_full2.py` — v2. Dynamic multicam: "pepper the two-shot in
  tastefully, AutoPod-style." Real product logic, not throwaway.
- `render_real.py` — an intermediate rev.
- `render_tonight.py` — episode-specific driver for BwG jdcxvxzvdm
  (2026-06-30). Repointed `render_full` / `render_full2` at that night's
  feeds. Shows how the pipeline was actually invoked before `bin/bwg`
  wrapped it.
- `render_chunks.py` — chunk-boundary renderer, precursor to `chunks.py`.
- `director.py` — the historical **root**. `bin/bwg`'s docstring literally
  refers back to this as "used to mean copy-paste-editing render_tonight.py."
  This is where the whole multicam gate concept started.

## Don't run these

They reference paths and feeds that no longer exist. They are for reading and
archaeology only. Current entry points are `../render_ep.py` and `../gate.py`.
