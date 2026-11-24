import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
from compare import *
from scipy.ndimage import gaussian_filter
from PIL import Image
ISO = {1:200,2:200,3:200,4:100,5:100,6:100,7:100,8:100,9:200,10:200,11:200,12:200,13:200}
SIM = {1:"Provia", 7:"Velvia", 8:"Velvia"}
N = 17

def small(a, f=2): return a[:a.shape[0]//f*f, :a.shape[1]//f*f].reshape(a.shape[0]//f, f, a.shape[1]//f, f, 3).mean((1, 3))

def samples(n):
    sim = SIM.get(n, "Classic Chrome"); ev = 1.12 + np.log2(min(1, ISO[n] / 200))
    lin = np.load(C % ("raf", n)); ref = np.load(C % ("emb", n))
    if ref.shape[:2] != lin.shape[:2]: ref = np.array(Image.fromarray(ref).resize((lin.shape[1], lin.shape[0]), Image.Resampling.BOX))
    o = render(lin, sim, ev)
    from scipy.ndimage import gaussian_filter as gf
    blur = lambda a: np.stack([gf(a[..., c].astype(np.float32), 4.0) for c in range(3)], -1)
    x = blur(o)[50:-50:4, 60:-60:4] / 255; y = blur(ref)[50:-50:4, 60:-60:4] / 255
    ok = ((x > 0.01) & (x < 0.99) & (y > 0.01) & (y < 0.99)).all(-1)      # Clipping ausschliessen
    return x[ok], y[ok], sim

def splat(x, r):
    """Trilineares Splatting der Residuen r an den Stellen x auf ein NxNxN-Gitter."""
    p = np.clip(x, 0, 1) * (N - 1); i0 = np.minimum(p.astype(int), N - 2); f = p - i0
    num = np.zeros((N, N, N, 3)); den = np.zeros((N, N, N))
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2])
                idx = (i0[:, 0] + dr, i0[:, 1] + dg, i0[:, 2] + db)
                np.add.at(den, idx, w)
                for c in range(3): np.add.at(num[..., c], idx, w * r[:, c])
    return num, den

def fit(xs, ys, lam=20.0, sigma=0.8):
    x = np.concatenate(xs); y = np.concatenate(ys)
    num, den = splat(x, y - x)
    num = np.stack([gaussian_filter(num[..., c], sigma) for c in range(3)], -1); den = gaussian_filter(den, sigma)
    return num / (den[..., None] + lam)          # Grid der Korrektur (rgb, additiv)

def apply(grid, x):
    p = np.clip(x, 0, 1) * (N - 1); i0 = np.minimum(p.astype(int), N - 2); f = p - i0
    out = np.zeros_like(x)
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = (f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2])
                out += w[:, None] * grid[i0[:, 0] + dr, i0[:, 1] + dg, i0[:, 2] + db]
    return np.clip(x + out, 0, 1)

def dE(a, b): return de((a * 255).astype(np.uint8)[None], (b * 255).astype(np.uint8)[None])[0]

data = {n: samples(n) for n in range(1, 14)}
cc = [n for n in data if data[n][2] == "Classic Chrome"]
print("Leave-one-out fuer Classic Chrome (Trainieren auf 9, Testen auf 1 Bild):")
tot0 = []; tot1 = []
for t in cc:
    tr = [n for n in cc if n != t]
    g = fit([data[n][0] for n in tr], [data[n][1] for n in tr])
    x, y, _ = data[t]; d0 = dE(x, y); d1 = dE(apply(g, x), y)
    tot0.append(d0.mean()); tot1.append(d1.mean())
    print(f"  Bild {t:02d}: dE mittel {d0.mean():5.2f} -> {d1.mean():5.2f}   Median {np.median(d0):5.2f} -> {np.median(d1):5.2f}   P95 {np.percentile(d0,95):5.1f} -> {np.percentile(d1,95):5.1f}")
print(f"  Durchschnitt: {np.mean(tot0):.2f} -> {np.mean(tot1):.2f}")
