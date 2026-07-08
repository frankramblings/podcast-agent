"""Chunk-based Frank source resolver + per-chunk fine-sync probe.

Frank's camera dropped/reconnected 3x, so his feed exists as 4 native chunks,
each a clean continuous recording. The filename timecodes are TRUE composite-
timeline positions (verified: durations match spans to <0.5s). So we place each
chunk at its named start and measure one clean residual offset per chunk via
GCC-PHAT against the composite audio -- no stitched-backup seams to fight.
"""
import subprocess, numpy as np, os, re, glob

R = "real"
COMP = f"{R}/composite.mp4"
CHUNK_DIR = f"{R}/chunks"
SR = 8000


def parse_chunks():
    out = []
    for p in sorted(glob.glob(f"{CHUNK_DIR}/*.mp4")):
        m = re.search(r'(\d+)h(\d+)m(\d+)s to (\d+)h(\d+)m(\d+)s', os.path.basename(p))
        h1, m1, s1, h2, m2, s2 = map(int, m.groups())
        out.append({"path": p,
                    "start": h1*3600+m1*60+s1,
                    "end": h2*3600+m2*60+s2})
    out.sort(key=lambda c: c["start"])
    return out


def pcm(path, at, span):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-t", str(span),
                        "-i", path, "-ac", "1", "-ar", str(SR),
                        "-af", "highpass=f=85", "-f", "f32le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def gcc_phat(sig, ref, max_lag):
    n = 1
    while n < len(sig)+len(ref):
        n *= 2
    SIG = np.fft.rfft(sig, n); REF = np.fft.rfft(ref, n)
    Rr = SIG*np.conj(REF); Rr /= np.abs(Rr)+1e-9
    cc = np.fft.irfft(Rr, n)
    ml = int(max_lag*SR)
    cc = np.concatenate((cc[-ml:], cc[:ml+1]))
    peak = np.argmax(np.abs(cc))
    sharp = np.abs(cc[peak])/(np.mean(np.abs(cc))+1e-9)
    return (peak-ml)/SR, sharp


def chunk_residual(ch, local_t, span=120, maxlag=10):
    """Offset to ADD to chunk-local time so it matches the composite clock.
    Probes chunk at local_t vs composite at (chunk.start + local_t)."""
    comp_t = ch["start"] + local_t
    fr = pcm(ch["path"], local_t, span)
    cp = pcm(COMP, comp_t, span)
    n = min(len(fr), len(cp))
    if n < SR*5:
        return None, 0.0
    lag, sharp = gcc_phat(fr[:n], cp[:n], maxlag)
    return lag, sharp


if __name__ == "__main__":
    chunks = parse_chunks()
    print(f"{len(chunks)} chunks\n")
    for i, ch in enumerate(chunks):
        dur = ch["end"] - ch["start"]
        print(f"--- chunk {i}: comp {ch['start']}s-{ch['end']}s ({dur}s)  {os.path.basename(ch['path'])[:40]}")
        # probe ~5 interior points; skip first/last 10s
        pts = [p for p in np.linspace(10, dur-10, 5)] if dur > 40 else [dur/2]
        vals = []
        for lt in pts:
            res, sh = chunk_residual(ch, lt)
            if res is not None:
                vals.append(res)
                print(f"    local {lt:7.1f}s (comp {ch['start']+lt:7.1f}s)  residual {res:+.3f}s  sharp {sh:6.1f}")
        if len(vals) > 1:
            print(f"    => spread {max(vals)-min(vals):+.3f}s  mean {np.mean(vals):+.3f}s")
        print()
