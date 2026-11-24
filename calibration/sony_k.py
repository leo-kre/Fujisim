import sys, io, glob, os
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim"); sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
import numpy as np, rawpy
from PIL import Image
from fujisim import raw_io, flog
from fujisim.pipeline import process_region, Ctx
from fujisim.settings import EditSettings
from fujisim.effects import resize_ch
L = np.array([.2126, .7152, .0722], np.float32)
files = [f for f in sorted(glob.glob(os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Fotos/**/*.ARW"), recursive=True)) if not raw_io.is_dataless(f)]
files += ["/Users/leonkreutzer/Downloads/DSC04602.ARW"]
print(len(files), "lokale ARW-Dateien")
rows = []
for f in files[:24]:
    try:
        with rawpy.imread(f) as raw: t = raw.extract_thumb()
        im = Image.open(io.BytesIO(t.data)); ex = im.getexif().get_ifd(0x8769); iso = ex.get(0x8827); mk = im.getexif().get(0x010F)
        jpg = np.asarray(im.convert("RGB")); h, w = jpg.shape[:2]
        rgb, _ = raw_io._decode(f, half=True); H, W = rgb.shape[:2]
        lin = np.stack([resize_ch(rgb[..., c].astype(np.float32), w // 2, h // 2, Image.Resampling.BOX) for c in range(3)], -1) / 65535
        ref = np.stack([resize_ch(jpg[..., c].astype(np.float32), w // 2, h // 2, Image.Resampling.BOX) for c in range(3)], -1)
        yref = np.median(ref @ L)
        def med(ev):
            s = EditSettings(sim="Provia", auto_exposure=False, exposure=ev, sharpness=-1.6)
            o = process_region(lin, s, Ctx((w // 2) / W / 2 if False else 0.25, w // 2, h // 2, 0, 0, 1, 1.0, None), flog.official_lut("Provia"))
            return np.median(o.astype(np.float32) @ L)
        lo, hi = -2.0, 4.0
        for _ in range(3):
            g = np.linspace(lo, hi, 13); e = [abs(med(x) - yref) for x in g]; b = g[int(np.argmin(e))]; st = (hi - lo) / 12; lo, hi = b - st, b + st
        rows.append((os.path.basename(f), iso, b, yref)); print(f"{os.path.basename(f):14s} ISO {iso!s:>6}  EV_fit {b:+.2f}   Sony-JPEG Median-Y {yref:5.1f}", flush=True)
    except Exception as exc:
        print(os.path.basename(f), "FEHLER", exc)
ev = np.array([r[2] for r in rows]); print(f"\nEV_fit: Median {np.median(ev):+.2f}, Mittel {ev.mean():+.2f}, Std {ev.std():.2f}, Spanne {ev.min():+.2f}..{ev.max():+.2f}")
isos = np.array([float(r[1]) for r in rows]); 
for lo_, hi_ in ((0, 99), (100, 100), (101, 400), (401, 99999)):
    m = (isos >= lo_) & (isos <= hi_)
    if m.sum(): print(f"  ISO {lo_}-{hi_}: n={m.sum()}, EV_fit Median {np.median(ev[m]):+.2f}")
