"""RAF (libraw, ProPhoto linear) und Kamera-JPEG auf gleiche Groesse bringen und als .npy cachen."""
import sys, time
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image, ImageOps
from fujisim import raw_io
from fujisim.engine import _down2
from fujisim.effects import resize_ch

D = "/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.%s"
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/xt2_%02d_%s.npy"
LONG = 1500
for n in range(1, 14):
    t = time.time()
    rgb, ratio = raw_io._decode(D % (n, "raf"), half=False)
    jpg = ImageOps.exif_transpose(Image.open(D % (n, "jpg"))).convert("RGB")
    jw, jh = jpg.size
    if jw < jh:                                   # Hochformat: RAW (landscape) um 90 Grad drehen
        rgb = np.rot90(rgb, k=-1)
    H, W = rgb.shape[:2]
    oy, ox = (H - jh) // 2, (W - jw) // 2         # RAF hat einen Rand -> mittig auf JPEG-Groesse beschneiden
    rgb = rgb[oy:oy + jh, ox:ox + jw]
    H, W = jh, jw
    k = LONG / max(W, H); nw, nh = round(W * k), round(H * k)
    lin = np.stack([resize_ch(rgb[..., c].astype(np.float32), nw, nh, Image.Resampling.BOX) for c in range(3)], -1)
    lin = np.clip(lin, 0, 65535).astype(np.uint16)
    ja = np.asarray(jpg)
    ref = np.stack([resize_ch(ja[..., c].astype(np.float32), nw, nh, Image.Resampling.BOX) for c in range(3)], -1)
    np.save(C % (n, "lin"), lin); np.save(C % (n, "ref"), np.clip(ref + 0.5, 0, 255).astype(np.uint8))
    np.save(C % (n, "ratio"), ratio)
    print(f"{n:02d} RAF {W}x{H}  JPEG {jw}x{jh}  -> {nw}x{nh}  ({time.time()-t:.1f}s)  icc={'icc_profile' in jpg.info}", flush=True)
