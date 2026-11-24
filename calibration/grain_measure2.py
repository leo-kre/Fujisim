import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter
L = np.array([.2126, .7152, .0722], np.float32)
def analyze(path, label, win=24):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32); y = a @ L
    base = gaussian_filter(y, 3.0); hp = y - base                              # Hochpass
    g = np.hypot(*np.gradient(gaussian_filter(y, 2.0)))                         # Struktur (Kanten/Textur) ausschliessen
    mean = uniform_filter(base, win); var = uniform_filter(hp ** 2, win)
    sel = (uniform_filter(g, win) < np.percentile(uniform_filter(g, win), 40))
    print(f"\n{label}: Korn-Std (Luma-Hochpass, sigma 3) je Helligkeit, nur strukturarme Fenster")
    for lo in range(0, 256, 32):
        m = sel & (mean >= lo) & (mean < lo + 32)
        if m.sum() > 3000: print(f"   Y {lo:3d}-{lo+31:3d}: std {np.sqrt(np.median(var[m])):5.2f}   (n={m.sum()})")
    # ACF bei Lag 1..4 in glatten Patches
    flat = sel & (mean > 40) & (mean < 235)
    ys, xs = np.where(flat[::24, ::24]); acs = []
    for i, j in zip(ys[:200], xs[:200]):
        p = hp[i*24:i*24+48, j*24:j*24+48]
        if p.shape != (48, 48): continue
        p = p - p.mean(); f = np.fft.fft2(p); ac = np.fft.ifft2(f * np.conj(f)).real; ac /= ac[0, 0]; acs.append(0.5 * (ac[0, 1:5] + ac[1:5, 0]))
    print("   Autokorrelation Lag 1,2,3,4:", np.round(np.median(acs, axis=0), 2))
D = "/Users/leonkreutzer/Downloads/fujisim/refs/grain/%s.jpg"
analyze(D % "xt5_weak_small_crop", "X-T5 Grain Weak/Small (100%-Ausschnitt)")
analyze(D % "xt5_strong_large_crop", "X-T5 Grain Strong/Large (100%-Ausschnitt)")
