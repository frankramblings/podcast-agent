# Non-circular: measure the FINISHED master's audio against each source, to see
# what the render actually did (vs the model). Tim one-shot window = clip #2.
import numpy as np, subprocess
from chunks import pcm, gcc_phat, SR
import render_full as rf
from render_ep import discover
FEEDS="/home/frank/.openclaw/workspace/media/wistia-feeds/44njfqvjjv"
comp,tim,frank=discover(FEEDS); rf.COMP=comp; rf.TIM=tim
total=rf.dur(comp); rf.CHUNKS=[{"start":0,"end":total,"path":frank,"off":None}]
toff_fn,tf=rf.tim_fit(total)
MASTER=f"{FEEDS}/master_566.mp4"
PREPEND=5.81  # cold-open intro length from render log
# clip #2 master window
mt=1612.0; span=12.0
compt=mt-PREPEND                       # composite time of this window
S_used=compt+toff_fn(compt)            # Tim-cam seek the render used for video
print(f"master-time {mt}  -> composite-time {compt:.2f}")
print(f"toff(compt)={toff_fn(compt):+.3f}  => render seeked Tim video to {S_used:.2f}")
# 1) master audio vs composite at compt: should be ~0 (master audio IS composite bed)
ma=pcm(MASTER, mt, span); ca=pcm(comp, compt, span)
n=min(len(ma),len(ca)); lag_c,sh_c=gcc_phat(ma[:n],ca[:n],10)
print(f"[master-audio vs composite@{compt:.1f}]  lag={lag_c:+.3f}s sh={sh_c:.0f}  (expect ~0)")
# 2) master audio vs Tim-CAMERA audio at the seek we used: ~0 means audio placed right
ta=pcm(tim, S_used, span); n=min(len(ma),len(ta)); lag_t,sh_t=gcc_phat(ma[:n],ta[:n],12)
print(f"[master-audio vs Tim-cam@seek {S_used:.1f}] lag={lag_t:+.3f}s sh={sh_t:.0f}  (~0 => audio ok; lip error would then be A/V skew ~1.03s)")
