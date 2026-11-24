import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from compare import *
from PIL import Image
emb = np.load(C % ("emb", 1)); full = np.load(C % ("jpg", 10))
print("Formen", emb.shape, full.shape)
h, w = min(emb.shape[0], full.shape[0]), min(emb.shape[1], full.shape[1])
a = emb[:h, :w]; b = full[:h, :w]
d = de(a[40:-40, 40:-40], b[40:-40, 40:-40])
print(f"eingebettet vs. volles JPEG: mittleres dE {d.mean():.2f}, Median {np.median(d):.2f}, P95 {np.percentile(d,95):.2f}  (dE<2: kaum sichtbar)")
sims = {1: "Provia", 7: "Velvia", 8: "Velvia"}
print("\nRAF  Sim             gefittetes EV   mittl. dE   Median dE   P95 dE")
for n in range(1, 14):
    lin = np.load(C % ("raf", n)); ref = np.load(C % ("emb", n))
    if ref.shape[:2] != lin.shape[:2]:
        ref = np.array(Image.fromarray(ref).resize((lin.shape[1], lin.shape[0]), Image.Resampling.BOX))
    sim = sims.get(n, "Classic Chrome")
    ev, e = fit_ev(lin, ref, sim)
    o = render(lin, sim, ev); dd = de(o[60:-60, 80:-80], ref[60:-60, 80:-80])
    print(f"{n:02d}   {sim:15s} {ev:+6.2f}          {dd.mean():5.2f}      {np.median(dd):5.2f}     {np.percentile(dd,95):5.2f}")
