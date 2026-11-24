import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter
L = np.array([.2126, .7152, .0722], np.float32)
D = "/Users/leonkreutzer/Downloads/fujisim/refs/grain/xt30_%s_%s.jpg"
def noise_stats(path, sigma=3.0):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32); y = a @ L
    hp = y - gaussian_filter(y, sigma); base = gaussian_filter(y, 3)
    g = np.hypot(*np.gradient(gaussian_filter(y, 1.5))); win = 24
    quiet = uniform_filter(g, win) < np.percentile(uniform_filter(g, win), 35)     # strukturarme Bereiche (Himmel)
    m = quiet & (base > 40) & (base < 240)
    res = np.sqrt(np.median(uniform_filter(hp ** 2, win)[m])); ymean = base[m].mean()
    chroma = a - a.mean(2, keepdims=True); chp = chroma - np.stack([gaussian_filter(chroma[..., c], sigma) for c in range(3)], -1)
    # ACF
    ys, xs = np.where(m[::24, ::24]); acs = []
    for i, j in zip(ys[:150], xs[:150]):
        p = hp[i*24:i*24+48, j*24:j*24+48]
        if p.shape != (48, 48): continue
        p = p - p.mean(); f = np.fft.fft2(p); ac = np.fft.ifft2(f * np.conj(f)).real; ac /= ac[0, 0]; acs.append(0.5 * (ac[0, 1:4] + ac[1:4, 0]))
    return res, ymean, np.sqrt((chp[:, :, :][m] ** 2).mean()), np.median(acs, axis=0), m.sum()
for s in ("a", "b"):
    out = {}
    for g in ("off", "weak", "strong"):
        out[g] = noise_stats(D % (s, g))
        print(f"Crop {s} Grain {g:6s}: Luma-Std {out[g][0]:5.2f} (Y~{out[g][1]:5.1f}) Chroma-Std {out[g][2]:4.2f}  ACF lag1-3 {np.round(out[g][3], 2)}  n={out[g][4]}")
    o = out["off"][0]
    for g in ("weak", "strong"):
        print(f"   -> reiner Korn-Anteil {g}: sqrt({out[g][0]:.2f}^2 - {o:.2f}^2) = {np.sqrt(max(out[g][0]**2 - o**2, 0)):.2f} Stufen")
