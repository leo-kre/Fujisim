import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/xt2_%02d_%s.npy"
rows = []
for n in (10, 4, 1):
    lin = np.load(C % (n, "lin")).astype(np.float32) / 65535; ref = np.load(C % (n, "ref"))
    print(n, "raw lin mean/max", lin.mean().round(4), lin.max().round(3), "| ref mean", ref.mean().round(1))
    g = lin.mean() 
    a = (np.clip(lin * (0.18/ max(np.median(lin),1e-4)), 0, 1) ** (1/2.2) * 255).astype(np.uint8)
    rows.append(np.concatenate([a, ref], 1)[::2, ::2])
Image.fromarray(np.concatenate(rows, 0)).save("/Users/leonkreutzer/Downloads/fujisim/calibration/cache/side.jpg", quality=85)
