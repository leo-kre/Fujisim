import sys, io, struct
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim"); sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
import numpy as np, rawpy
from PIL import Image, ImageOps
from fuji_exif import describe
from fujisim.effects import resize_ch
D = "/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.raf"
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/%s_%02d.npy"
for n in range(1, 14):
    with rawpy.imread(D % n) as raw:
        t = raw.extract_thumb()
    im = Image.open(io.BytesIO(t.data)); ori = im.getexif().get(0x0112, 1)
    open("/tmp/_emb.jpg", "wb").write(t.data)
    d = describe("/tmp/_emb.jpg")
    im = ImageOps.exif_transpose(im).convert("RGB"); a = np.asarray(im); h, w = a.shape[:2]; k = 1500 / max(w, h)
    emb = np.stack([resize_ch(a[..., c].astype(np.float32), round(w * k), round(h * k), Image.Resampling.BOX) for c in range(3)], -1)
    np.save(C % ("emb", n), np.clip(emb + .5, 0, 255).astype(np.uint8))
    print(f"RAF {n:02d}: eingebettetes JPEG {im.size} orient={ori} {len(t.data)/1e6:.1f} MB | {d['film']}, DR{d['dr']}, hi {d['highlight']}, sh {d['shadow']}, color {d['color']}, sharp {d['sharpness']}, wb {d['wb']}, nr_raw={d['nr']}")
