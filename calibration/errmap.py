import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from compare import *
from PIL import Image
ISO = {2:200,4:100,10:200,13:200}
rows = []
for n in (2, 4, 10, 13):
    sim = "Classic Chrome"; ev = 1.12 + np.log2(min(1, ISO[n] / 200))
    lin = np.load(C % ("raf", n)); ref = np.load(C % ("emb", n))
    o = render(lin, sim, ev); d = de(o, ref)
    heat = np.clip(d / 30, 0, 1); hm = (np.stack([heat, 1 - np.abs(heat - .5) * 2, 1 - heat], -1) * 255).astype(np.uint8)
    rows.append(np.concatenate([o, ref, hm], 1)[::3, ::3]); print(n, "dE mean", d.mean().round(2))
Image.fromarray(np.concatenate(rows, 0)).save("/Users/leonkreutzer/Downloads/fujisim/calibration/cache/err.jpg", quality=85)
