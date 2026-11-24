import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
exec(open("/Users/leonkreutzer/Downloads/fujisim/calibration/fit_corr.py").read().split("data = {n: samples")[0])
data = {n: samples(n) for n in range(1, 14)}
cc = [n for n in data if data[n][2] == "Classic Chrome"]
print("E1: lambda/sigma-Sweep, LOO Classic Chrome (mittleres dE ueber 10 Bilder)")
base = np.mean([dE(data[t][0], data[t][1]).mean() for t in cc]); print(f"  ohne Korrektur: {base:.2f}")
for lam, sig in ((3, 0.6), (8, 0.6), (8, 1.0), (20, 0.8), (20, 1.2), (60, 1.0)):
    r = []
    for t in cc:
        g = fit([data[n][0] for n in cc if n != t], [data[n][1] for n in cc if n != t], lam=lam, sigma=sig)
        r.append(dE(apply(g, data[t][0]), data[t][1]).mean())
    print(f"  lam={lam:3d} sigma={sig:.1f}: {np.mean(r):.2f}  (worst {np.max(r):.1f})")
# E2: allgemeine Luma-Kurve (aus anderen Looks gelernt) auf unbekannten Look anwenden
def luma_curve(xs, ys, bins=17):
    x = np.concatenate(xs); y = np.concatenate(ys)
    yx, yy = x @ LUMA, y @ LUMA; edges = np.linspace(0, 1, bins + 1); c = 0.5 * (edges[1:] + edges[:-1]); d = np.zeros(bins)
    for i in range(bins):
        m = (yx >= edges[i]) & (yx < edges[i + 1])
        d[i] = (yy[m] - yx[m]).mean() if m.sum() > 300 else 0
    return c, d
def apply_luma(c, d, x):
    shift = np.interp(x @ LUMA, c, d); return np.clip(x + shift[:, None], 0, 1)
print("\nE2: Allgemeine Luma-Korrektur, gelernt auf ANDEREN Looks, getestet auf unbekanntem Look")
for test_sim in ("Provia", "Velvia", "Classic Chrome"):
    tr = [n for n in data if data[n][2] != test_sim]; te = [n for n in data if data[n][2] == test_sim]
    c, d = luma_curve([data[n][0] for n in tr], [data[n][1] for n in tr])
    b = np.mean([dE(data[n][0], data[n][1]).mean() for n in te]); a = np.mean([dE(apply_luma(c, d, data[n][0]), data[n][1]).mean() for n in te])
    print(f"  Test {test_sim:15s} (Training: andere Looks): dE {b:.2f} -> {a:.2f}")
