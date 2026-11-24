import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from scipy.ndimage import gaussian_filter
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/xt2_%02d_%s.npy"
L = np.array([0.2126, 0.7152, 0.0722], np.float32)
for n in range(1, 14):
    lin = np.load(C % (n, "lin")).astype(np.float32) / 65535; ref = np.load(C % (n, "ref")).astype(np.float32) / 255
    a = np.clip(lin @ L, 0, 1) ** (1/2.2); b = ref @ L
    best = None
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            x = a[20+dy:-20+dy or None, 20+dx:-20+dx or None]; y = b[20:-20, 20:-20]
            hx = x[::2, ::2] - x[::2, ::2].mean(); hy = y[::2, ::2] - y[::2, ::2].mean()
            c = (hx*hy).mean() / (hx.std()*hy.std() + 1e-9)
            if best is None or c > best[0]: best = (c, dx, dy)
    print(f"{n:02d} Form {lin.shape[:2]} == {ref.shape[:2]}  beste Korrelation {best[0]:.3f} bei Versatz dx={best[1]} dy={best[2]}")
