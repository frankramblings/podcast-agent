import subprocess, numpy as np, os
os.chdir("/home/frank/.openclaw/workspace/.tmp/openclaw-spikes/podcast-director")
R="real"; COMP=f"{R}/composite.mp4"; FRK=f"{R}/frank_cam.mp4"
SR=8000
def pcm(path,at,span):
    r=subprocess.run(["ffmpeg","-v","error","-ss",str(at),"-t",str(span),"-i",path,
        "-ac","1","-ar",str(SR),"-af","highpass=f=85","-f","f32le","-"],capture_output=True)
    return np.frombuffer(r.stdout,dtype=np.float32).copy()
def gcc_phat(sig,ref,max_lag,sr=SR):
    n=1
    while n<len(sig)+len(ref): n*=2
    R_=np.fft.rfft(sig,n)*np.conj(np.fft.rfft(ref,n)); R_/=np.abs(R_)+1e-9
    cc=np.fft.irfft(R_,n); ml=int(max_lag*sr)
    cc=np.concatenate((cc[-ml:],cc[:ml+1])); peak=int(np.argmax(np.abs(cc)))
    return (peak-ml)/sr, float(np.abs(cc[peak])/(np.mean(np.abs(cc))+1e-9))
print("t(s)  FRK_off  sharp")
for t in range(960,1860,60):
    cp=pcm(COMP,t-10,60); fr=pcm(FRK,t-10,60); n=min(len(cp),len(fr))
    off,s=gcc_phat(fr[:n],cp[:n],10)
    print(f"{t:5d}  {off:+6.2f}  {s:6.1f}")
