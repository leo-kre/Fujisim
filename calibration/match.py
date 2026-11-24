import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np, json
from scipy.ndimage import zoom
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/%s_%02d.npy"
L = np.array([0.2126, 0.7152, 0.0722], np.float32)
def small(a): return zoom(a, (150 / max(a.shape), 150 / max(a.shape)), order=1)
raf = {n: small(np.clip((np.load(C % ("raf", n)).astype(np.float32) / 65535) @ L, 0, 1) ** (1 / 2.2)) for n in range(1, 14)}
jpg = {n: small((np.load(C % ("jpg", n)).astype(np.float32) / 255) @ L) for n in range(1, 14)}
def corr(a, b):
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    if abs(a.shape[0]-b.shape[0]) > 3 or abs(a.shape[1]-b.shape[1]) > 3: return -1
    a, b = a[:h, :w], b[:h, :w]; a = a - a.mean(); b = b - b.mean()
    return float((a * b).mean() / (a.std() * b.std() + 1e-9))
res = {}
for j in range(1, 14):
    best = (-1, None, None)
    for r in range(1, 14):
        for k in (0, 1, 2, 3):                       # 0/90/180/270 Grad
            c = corr(np.rot90(raf[r], k), jpg[j])
            if c > best[0]: best = (c, r, k)
    res[j] = best
    print(f"JPEG {j:02d} <- RAF {best[1]:02d} (Drehung {best[2]*90:3d} Grad)  Korrelation {best[0]:.3f}")
json.dump({str(j): {"raf": v[1], "rot": v[2], "corr": v[0]} for j, v in res.items()}, open("/Users/leonkreutzer/Downloads/fujisim/calibration/pairs.json", "w"), indent=1)
