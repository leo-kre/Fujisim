import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from compare import *
from PIL import Image
ISO = {1:200,2:200,3:200,4:100,5:100,6:100,7:100,8:100,9:200,10:200,11:200,12:200,13:200}
SIM = {1:"Provia", 7:"Velvia", 8:"Velvia"}
K = 1.12
pairs = {}
for n in range(1, 14):
    sim = SIM.get(n, "Classic Chrome"); ev = K + np.log2(min(1, ISO[n] / 200))
    lin = np.load(C % ("raf", n)); ref = np.load(C % ("emb", n))
    if ref.shape[:2] != lin.shape[:2]: ref = np.array(Image.fromarray(ref).resize((lin.shape[1], lin.shape[0]), Image.Resampling.BOX))
    o = render(lin, sim, ev)
    sl = (slice(60, -60), slice(80, -80))
    d = de(o[sl], ref[sl])
    pairs.setdefault(sim, []).append((o[sl][::3, ::3].reshape(-1, 3), ref[sl][::3, ::3].reshape(-1, 3)))
    print(f"{n:02d} {sim:15s} ISO{ISO[n]:4d} EV {ev:+.2f}  dE mittel {d.mean():5.2f} Median {np.median(d):5.2f} P95 {np.percentile(d,95):5.2f}")
for sim, lst in pairs.items():
    mine = np.concatenate([a for a, b in lst]); ref = np.concatenate([b for a, b in lst])
    ym, yr = mine.astype(np.float32) @ LUMA, ref.astype(np.float32) @ LUMA
    print(f"\n== {sim}: Tonkurve (Mittel von Referenz-Y je Bin des eigenen Y), n={len(mine)}")
    for lo in range(0, 256, 32):
        m = (ym >= lo) & (ym < lo + 32)
        if m.sum() > 200: print(f"   mein Y {lo:3d}-{lo+31:3d}: Ref-Y {yr[m].mean():6.1f}  (Diff {yr[m].mean()-ym[m].mean():+5.1f}, n={m.sum()})")
    lm, lr = srgb2lab(mine), srgb2lab(ref)
    cm, cr = np.hypot(lm[:, 1], lm[:, 2]), np.hypot(lr[:, 1], lr[:, 2])
    hm = (np.degrees(np.arctan2(lm[:, 2], lm[:, 1])) % 360)
    print("   Chroma-Verhaeltnis Ref/Mein nach Farbton (nur C*>12):")
    for h0 in range(0, 360, 45):
        m = (hm >= h0) & (hm < h0 + 45) & (cm > 12)
        if m.sum() > 200: print(f"     Hue {h0:3d}-{h0+44:3d}: C*ref/C*mein = {np.median(cr[m]/cm[m]):.2f}   dL(ref-mein)={np.median(lr[m,0]-lm[m,0]):+5.1f}  n={m.sum()}")
