import subprocess, numpy as np
R="real"; COMP=f"{R}/composite.mp4"; FRK=f"{R}/frank_cam.mp4"; TIM=f"{R}/tim_cam.mp4"
SR=8000
def pcm(path,at,span):
    r=subprocess.run(["ffmpeg","-v","error","-ss",str(at),"-t",str(span),"-i",path,
        "-ac","1","-ar",str(SR),"-af","highpass=f=85","-f","f32le","-"],capture_output=True)
    return np.frombuffer(r.stdout,dtype=np.float32).copy()
def gcc_phat(sig,ref,max_lag):
    n=1
    while n<len(sig)+len(ref): n*=2
    SIG=np.fft.rfft(sig,n); REF=np.fft.rfft(ref,n)
    R_=SIG*np.conj(REF); R_/=np.abs(R_)+1e-9
    cc=np.fft.irfft(R_,n)
    ml=int(max_lag*SR)
    cc=np.concatenate((cc[-ml:],cc[:ml+1]))
    peak=np.argmax(np.abs(cc))
    lag=peak-ml
    sharp=np.abs(cc[peak])/(np.mean(np.abs(cc))+1e-9)
    return lag/SR, sharp
print("t(s)   FRK_off  sharp     TIM_off  sharp")
for t in range(120,2401,240):
    cp=pcm(COMP,t-15,120)
    fr=pcm(FRK,t-15,120); tm=pcm(TIM,t-15,120)
    nf=min(len(cp),len(fr)); foff,fs=gcc_phat(fr[:nf],cp[:nf],8)
    nt=min(len(cp),len(tm)); toff,ts=gcc_phat(tm[:nt],cp[:nt],8)
    print(f"{t:5d}  {foff:+6.2f}  {fs:6.1f}    {toff:+6.2f}  {ts:6.1f}")
