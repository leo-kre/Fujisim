import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim/calibration")
exec(open("/Users/leonkreutzer/Downloads/fujisim/calibration/fit_corr.py").read().split("data = {n: samples")[0])
data = {n: samples(n) for n in range(1, 14)}
# Velvia: 2-fold (je 1 Bild trainieren, das andere testen)
vel = [n for n in data if data[n][2] == "Velvia"]
print("Velvia 2-fold:")
for t in vel:
    tr = [n for n in vel if n != t]; g = fit([data[n][0] for n in tr], [data[n][1] for n in tr], lam=8, sigma=0.8)
    x, y, _ = data[t]; print(f"  Bild {t:02d}: dE {dE(x,y).mean():.2f} -> {dE(apply(g,x),y).mean():.2f}   Median {np.median(dE(x,y)):.2f} -> {np.median(dE(apply(g,x),y)):.2f}")
# Endgueltige Gitter
out = {"Classic Chrome": [n for n in data if data[n][2] == "Classic Chrome"], "Velvia": vel}
for sim, ids in out.items():
    g = fit([data[n][0] for n in ids], [data[n][1] for n in ids], lam=8, sigma=0.8)
    slug = sim.lower().replace(" ", "_").replace(".", "")
    np.save(f"/Users/leonkreutzer/Downloads/fujisim/fujisim/data/corr_{slug}.npy", g.astype(np.float32))
    x = np.concatenate([data[n][0] for n in ids]); y = np.concatenate([data[n][1] for n in ids])
    print(f"gespeichert corr_{slug}.npy  (Training {len(ids)} Bilder, Trainingsfehler dE {dE(x,y).mean():.2f} -> {dE(apply(g,x),y).mean():.2f}, max |Korrektur| {np.abs(g).max():.3f})")
