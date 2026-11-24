import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, shift as ndshift
D = "/Users/leonkreutzer/Downloads/fujisim/refs/cce/%s.jpg"
L = np.array([.2126, .7152, .0722], np.float32)
def load(n): return np.asarray(Image.open(D % n).convert("RGB")).astype(np.float32) / 255
def blur(a, s=2.0): return np.stack([gaussian_filter(a[..., c], s) for c in range(3)], -1)
def align(ref, img):
    yr, yi = gaussian_filter(ref @ L, 2), gaussian_filter(img @ L, 2); best = (1e9, 0, 0)
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            e = np.abs(yr[20:-20, 20:-20] - np.roll(np.roll(yi, dy, 0), dx, 1)[20:-20, 20:-20]).mean()
            if e < best[0]: best = (e, dy, dx)
    return np.roll(np.roll(img, best[1], 0), best[2], 1), best
def hsv(a):
    mx = a.max(-1); mn = a.min(-1); d = mx - mn; s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]; dz = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / dz) % 6, np.where(mx == g, (b - r) / dz + 2, (r - g) / dz + 4)) * 60
    return h, s, mx
def analyze(off, other, label, hue_sel=None):
    o, other_al, (e, dy, dx) = load(off), None, (0, 0, 0)
    t = load(other); t, (e, dy, dx) = align(o, t)
    ob, tb = blur(o, 3), blur(t, 3)
    h, s, v = hsv(ob); h2, s2, v2 = hsv(tb)
    ratio_v = v2 / np.maximum(v, 1e-3); ys = ob @ L; yt = tb @ L
    ok = (v > 0.15) & (v < 0.97) & (v2 < 0.99)
    if hue_sel is not None: ok &= hue_sel(h)
    print(f"\n{label}: Ausrichtung dy={dy} dx={dx} (Rest-Abweichung Y {e*255:.1f}/255)")
    print("   Saettigung(Off, HSV) | V-Verhaeltnis (Effekt/Off)  | Y-Verhaeltnis | S-Verhaeltnis |  n")
    for lo in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        m = ok & (s >= lo) & (s < lo + 0.1)
        if m.sum() > 400: print(f"      {lo:.1f}-{lo+0.1:.1f}       |   {np.median(ratio_v[m]):.3f}                     |  {np.median((yt / np.maximum(ys, 1e-3))[m]):.3f}        |  {np.median((s2 / np.maximum(s, 1e-3))[m]):.3f}        | {m.sum()}")
analyze("cce_off", "cce_weak", "Color Chrome Effect WEAK vs Off (X-T30)")
analyze("cce_off", "cce_strong", "Color Chrome Effect STRONG vs Off (X-T30)")
blue = lambda h: (np.abs(((h - 230 + 180) % 360) - 180) < 40)
analyze("blue_off", "blue_weak", "FX Blue WEAK vs Off (X100V), nur Blau-Toene", blue)
analyze("blue_off", "blue_strong", "FX Blue STRONG vs Off (X100V), nur Blau-Toene", blue)

print("\n\n=== Farbton-Abhaengigkeit (nur Saettigung > 0.30; V-Verhaeltnis Strong/Off) ===")
def by_hue(off, other, label):
    o = load(off); t, _ = align(o, load(other)); h, s, v = hsv(blur(o, 3)); h2, s2, v2 = hsv(blur(t, 3))
    ok = (s > 0.30) & (v > 0.15) & (v < 0.97) & (v2 < 0.99); r = v2 / np.maximum(v, 1e-3); sr = s2 / np.maximum(s, 1e-3)
    print(label)
    for lo in range(0, 360, 30):
        m = ok & (h >= lo) & (h < lo + 30)
        if m.sum() > 800: print(f"   Hue {lo:3d}-{lo+29:3d}: V-Verh. {np.median(r[m]):.3f}  S-Verh. {np.median(sr[m]):.3f}  mittl. S {s[m].mean():.2f}  n={m.sum()}")
by_hue("cce_off", "cce_strong", "Color Chrome STRONG (X-T30)")
by_hue("blue_off", "blue_strong", "FX Blue STRONG (X100V)")

print("\n\n=== Wirkt Color Chrome (Weak) auch auf Blau? Vergleich: FX Blue Strong  vs  FX Blue Strong + CCE Weak ===")
o = load("blue_strong"); t, _ = align(o, load("blue_strong_cce_weak")); h, s, v = hsv(blur(o, 3)); h2, s2, v2 = hsv(blur(t, 3))
ok = (s > 0.20) & (v > 0.15) & (v < 0.97) & (v2 < 0.99); r = v2 / np.maximum(v, 1e-3)
for lo in range(0, 360, 30):
    m = ok & (h >= lo) & (h < lo + 30)
    if m.sum() > 800: print(f"   Hue {lo:3d}-{lo+29:3d}: V-Verh. {np.median(r[m]):.3f}  mittl. S {s[m].mean():.2f}  n={m.sum()}")
