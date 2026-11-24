import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter
D = "/Users/leonkreutzer/Downloads/fujisim/refs/grain/%s.jpg"
L = np.array([.2126, .7152, .0722], np.float32)

def flat_patches(y, size=48, n=12):
    """Positionen der n glattesten size x size Bloecke (kleinster Gradient), ohne Clipping."""
    gx = np.abs(np.diff(gaussian_filter(y, 1.5), axis=1))[:-1]; gy = np.abs(np.diff(gaussian_filter(y, 1.5), axis=0))[:, :-1]
    g = (gx + gy)[:y.shape[0]-1, :y.shape[1]-1]
    m = uniform_filter(g, size)[size//2::size//2, size//2::size//2]
    ys, xs = np.unravel_index(np.argsort(m, axis=None), m.shape)
    out = []
    for i, j in zip(ys, xs):
        cy, cx = (i + 1) * size // 2, (j + 1) * size // 2
        if cy + size > y.shape[0] or cx + size > y.shape[1]: continue
        p = y[cy:cy+size, cx:cx+size]
        if p.mean() < 25 or p.mean() > 235: continue
        if all(abs(cy-a) > size or abs(cx-b) > size for a, b in out): out.append((cy, cx))
        if len(out) >= n: break
    return out

def stats(name):
    a = np.asarray(Image.open(D % name).convert("RGB")).astype(np.float32); y = a @ L
    res = []
    for cy, cx in flat_patches(y):
        p = y[cy:cy+48, cx:cx+48]; hp = p - gaussian_filter(p, 4)          # Hochpass (entfernt Verlaeufe)
        pc = a[cy:cy+48, cx:cx+48]; chroma = pc - pc.mean(2, keepdims=True); chp = chroma - np.stack([gaussian_filter(chroma[..., c], 4) for c in range(3)], -1)
        # Autokorrelation des Hochpass -> Korngroesse (Halbwertsbreite)
        f = np.fft.fft2(hp - hp.mean()); ac = np.fft.ifft2(f * np.conj(f)).real; ac /= ac[0, 0]
        prof = 0.5 * (ac[0, :24] + ac[:24, 0]); half = int(np.argmax(prof < 0.5)) if (prof < 0.5).any() else 24
        res.append((p.mean(), hp.std(), chp.std(), half))
    r = np.array(res)
    return r
for n in ("xt5_weak_small_crop", "xt5_strong_large_crop", "xt5_weak_small_bigcrop", "xt5_strong_large_bigcrop"):
    r = stats(n)
    print(f"{n:28s} glatte Patches {len(r):2d}: Y-Mittel {r[:,0].mean():5.1f} | Luma-Korn-Std (Hochpass) Median {np.median(r[:,1]):4.2f} (min {r[:,1].min():.2f}, max {r[:,1].max():.2f}) | Chroma-Std {np.median(r[:,2]):4.2f} | Korn-Halbwertsbreite {np.median(r[:,3]):.1f} px")
