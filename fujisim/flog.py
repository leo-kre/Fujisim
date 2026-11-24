"""F-Log2C-Konvertierung (laut Fujifilm F-Log2 C Data Sheet Ver.1.0) und LUT-Verwaltung.

Pipeline fuer die offiziellen Fuji-LUTs (F-Log2C / F-Gamut C -> Rec.709 + Film-Look):
Kamera-RAW (ProPhoto, linear) -> F-Gamut C (linear) -> F-Log2 -> LUT.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from . import lut as lutmod

# --- F-Log2 (identisch fuer F-Log2 C) ---
_A, _B, _C, _D = 5.555556, 0.064829, 0.245281, 0.384316
_E, _F, _CUT1 = 8.799461, 0.092864, 0.000889


def flog2_encode(x: np.ndarray) -> np.ndarray:
    """Szenen-linear (Reflexion, 0.18 = 18% Grau) -> F-Log2 (0..1)."""
    x = np.maximum(x, 0)
    out = np.where(x >= _CUT1, _C * np.log10(_A * x + _B) + _D, _E * x + _F)
    return np.clip(out, 0, 1).astype(np.float32)


# --- Farbraeume ---
D65 = (0.3127, 0.3290)
D50 = (0.3457, 0.3585)
SRGB_PRIM = [(0.64, 0.33), (0.30, 0.60), (0.15, 0.06)]
PROPHOTO_PRIM = [(0.7347, 0.2653), (0.1596, 0.8404), (0.0366, 0.0001)]
FGAMUTC_PRIM = [(0.7347, 0.2653), (0.0263, 0.9737), (0.1173, -0.0224)]  # Data Sheet


def _xyz(x, y):
    return np.array([x / y, 1.0, (1 - x - y) / y])


def rgb_to_xyz(prim, white) -> np.ndarray:
    m = np.stack([_xyz(*p) for p in prim], axis=1)
    s = np.linalg.solve(m, _xyz(*white))
    return m * s


_BRADFORD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])


def adaptation(src_white, dst_white) -> np.ndarray:
    ls = _BRADFORD @ _xyz(*src_white)
    ld = _BRADFORD @ _xyz(*dst_white)
    return np.linalg.inv(_BRADFORD) @ np.diag(ld / ls) @ _BRADFORD


_PRO_XYZ = adaptation(D50, D65) @ rgb_to_xyz(PROPHOTO_PRIM, D50)
_SRGB_XYZ = rgb_to_xyz(SRGB_PRIM, D65)
_FGC_XYZ = rgb_to_xyz(FGAMUTC_PRIM, D65)

# libraw liefert ProPhoto mit weissgleicher Normierung -> Neutral bleibt neutral
PRO_TO_FGC = (np.linalg.inv(_FGC_XYZ) @ _PRO_XYZ).astype(np.float32)
PRO_TO_SRGB = (np.linalg.inv(_SRGB_XYZ) @ _PRO_XYZ).astype(np.float32)
SRGB_TO_XYZ = _SRGB_XYZ
LUMA_SRGB = _SRGB_XYZ[1].astype(np.float32)
LUMA_FGC = _FGC_XYZ[1].astype(np.float32)


# --- Weissabgleich ueber Farbtemperatur ---
def kelvin_to_xy(t: float):
    t = float(np.clip(t, 1700, 24000))
    if t <= 4000:
        x = -0.2661239e9 / t ** 3 - 0.2343589e6 / t ** 2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t ** 3 + 2.1070379e6 / t ** 2 + 0.2226347e3 / t + 0.240390
    if t <= 2222:
        y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    elif t <= 4000:
        y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483
    return x, y


def kelvin_gains(kelvin: float, ref: float = 5500.0) -> np.ndarray:
    """RGB-Gains (Grün=1), die Licht der Farbtemperatur `kelvin` neutral machen,
    ausgehend von tageslichtbalancierten Daten."""
    def white(k):
        return np.linalg.solve(_SRGB_XYZ, _xyz(*kelvin_to_xy(k)))
    g = white(ref) / white(kelvin)
    return (g / g[1]).astype(np.float32)


# --- Offizielle Fuji-LUTs ---
# Simulation -> moegliche Dateinamen (ohne Beachtung der Gross-/Kleinschreibung)
LUT_FILES = {
    "Provia": ["PROVIA.cube"],
    "Velvia": ["VELVIA.cube"],
    "Astia": ["ASTIA.cube"],
    "Classic Chrome": ["CLASSIC-CHROME.cube"],
    "Pro Neg. Std": ["PRO-Neg.Std.cube"],
    "Classic Neg.": ["CLASSIC-NEGATIVE.cube"],
    "Eterna": ["ETERNA.cube"],
    "Eterna Bleach Bypass": ["ETERNA-BB.cube"],
    "Reala Ace": ["REALA-ACE.cube"],
    "Acros": ["ACROS.cube"],
}

# Looks ohne eigene LUT: Basis-LUT + gelernte Korrektur (aus der 20-Sims-Vergleichsgrafik, siehe calibration/RESULTS.md)
DERIVED = {"Pro Neg. Hi": "Pro Neg. Std", "Nostalgic Neg.": "Reala Ace"}

_CONFIG = Path.home() / ".fujisim.json"
_cache: dict[str, lutmod.Lut] = {}


def lut_dir() -> Path:
    env = os.environ.get("FUJISIM_LUT_DIR")
    if env:
        return Path(env)
    try:
        d = json.loads(_CONFIG.read_text()).get("lut_dir")
        if d:
            return Path(d)
    except Exception:  # noqa: BLE001
        pass
    return Path(__file__).resolve().parent.parent / "luts"


def set_lut_dir(path: str) -> None:
    try:
        cfg = json.loads(_CONFIG.read_text())
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg["lut_dir"] = path
    _CONFIG.write_text(json.dumps(cfg))
    _cache.clear()


def official_lut(sim: str):
    """Liefert die offizielle Fuji-LUT fuer `sim` oder None."""
    sim = DERIVED.get(sim, sim)
    d = lut_dir()
    for name in LUT_FILES.get(sim, []):
        p = d / name
        if not p.exists() and d.exists():
            matches = [q for q in d.iterdir() if q.name.lower() == name.lower()]
            p = matches[0] if matches else p
        if p.exists():
            key = str(p)
            if key not in _cache:
                _cache[key] = lutmod.load_cube(key)
            return _cache[key]
    return None


def available_sims() -> list[str]:
    return [s for s in LUT_FILES if official_lut(s) is not None]


# --- Gelernte Korrekturen LUT -> Kamera-JPEG (aus Fuji-RAF/JPEG-Paaren, siehe calibration/) ---
_corr_cache: dict = {}


def official_correction(sim: str):
    """3D-Korrekturgitter (17^3 x 3, additiv in Display-RGB) oder None, wenn fuer den Look keine
    belastbaren Referenzbilder vorliegen."""
    if sim not in _corr_cache:
        slug = sim.lower().replace(" ", "_").replace(".", "")
        f = Path(__file__).resolve().parent / "data" / f"corr_{slug}.npy"
        _corr_cache[sim] = np.load(f).astype(np.float32) if f.exists() else None
    return _corr_cache[sim]
