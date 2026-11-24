import sys, io, glob, os
sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np, rawpy
from PIL import Image
from fujisim import raw_io
from fujisim.engine import ImageSession
from fujisim.settings import EditSettings
L = np.array([.2126, .7152, .0722], np.float32)
print("camera_gain Fuji-RAFs:", [f"{raw_io.camera_gain('/Users/leonkreutzer/Downloads/fujisim/refs/xt2/fujifilm_x_t2_%02d.raf' % n)[0]:.2f}" for n in (1, 4, 7)], "(ISO200 -> 2^1.12=2.17, ISO100 -> 1.09)")
files = [f for f in sorted(glob.glob(os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Fotos/**/*.ARW"), recursive=True)) if not raw_io.is_dataless(f)][::25][:16]
old, new = [], []
for f in files:
    with rawpy.imread(f) as raw: t = raw.extract_thumb()
    ref = np.asarray(Image.open(io.BytesIO(t.data)).convert("RGB")); yref = np.median(ref @ L)
    sess = ImageSession.open_fast(f)
    z = 0.25 * 2  # halbe Aufloesung genuegt
    W, H = sess.W, sess.H; zz = 800 / max(W, H); cw, ch = round(W * zz), round(H * zz)
    s_new = EditSettings(sim="Provia")                                   # Kamera-Belichtung
    y_new = np.median(sess.render(s_new, zz, 0, 0, cw, ch).astype(np.float32) @ L)
    # alter Ansatz: Auto-Gain nach Bildhelligkeit
    sess.gain = raw_io.auto_gain(sess.levels[1][::2, ::2])
    y_old = np.median(sess.render(s_new, zz, 0, 0, cw, ch).astype(np.float32) @ L)
    old.append(y_old - yref); new.append(y_new - yref)
    print(f"{os.path.basename(f):14s} Sony-JPEG Y {yref:5.1f} | alt (Auto-Gain) {y_old:5.1f} ({y_old-yref:+5.1f}) | neu (Kamera-fest) {y_new:5.1f} ({y_new-yref:+5.1f})")
old, new = np.array(old), np.array(new)
print(f"\nmittlere |Abweichung der Median-Helligkeit zum Sony-JPEG|: alt {np.abs(old).mean():.1f}  ->  neu {np.abs(new).mean():.1f}  (Skala 0-255)")
