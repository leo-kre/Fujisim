"""RAFs und JPEGs unabhaengig cachen (1500 px lange Kante), dann per Bildinhalt zuordnen."""
import sys, time
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image, ImageOps
from fujisim import raw_io
from fujisim.effects import resize_ch
D = "/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.%s"
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/%s_%02d.npy"
LONG = 1500
def box(a, w, h): return np.stack([resize_ch(a[..., c].astype(np.float32), w, h, Image.Resampling.BOX) for c in range(3)], -1)
for n in range(1, 14):
    rgb, ratio = raw_io._decode(D % (n, "raf"), half=False)
    H, W = rgb.shape[:2]; oy, ox = (H - 4000) // 2, (W - 6000) // 2
    rgb = rgb[oy:oy + 4000, ox:ox + 6000]                     # 6000x4000 wie die JPEGs, unrotiert
    np.save(C % ("raf", n), np.clip(box(rgb, 1500, 1000), 0, 65535).astype(np.uint16)); np.save(C % ("ratio", n), ratio)
    jpg = ImageOps.exif_transpose(Image.open(D % (n, "jpg"))).convert("RGB"); ja = np.asarray(jpg); h, w = ja.shape[:2]
    k = LONG / max(w, h)
    np.save(C % ("jpg", n), np.clip(box(ja, round(w * k), round(h * k)) + 0.5, 0, 255).astype(np.uint8))
    print(n, "ok", flush=True)
