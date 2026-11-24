import sys; sys.path.insert(0, "/Users/leonkreutzer/Downloads/fujisim")
import numpy as np
from fujisim import flog
from fujisim.pipeline import process_region, Ctx
from fujisim.settings import EditSettings
C = "/Users/leonkreutzer/Downloads/fujisim/calibration/cache/%s_%02d.npy"
LUMA = np.array([.2126, .7152, .0722], np.float32)

def srgb2lab(u8):
    c = u8.astype(np.float32) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = lin @ M.T / np.array([0.9505, 1, 1.089], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)

def de(a_u8, b_u8):
    return np.sqrt(((srgb2lab(a_u8) - srgb2lab(b_u8)) ** 2).sum(-1))

def render(lin16, sim, ev, **kw):
    s = EditSettings(sim=sim, auto_exposure=False, exposure=ev, sharpness=-1.6, **kw)
    h, w = lin16.shape[:2]
    ctx = Ctx(w / 6000, w, h, 0, 0, 1, 1.0, None)
    return process_region(lin16.astype(np.float32) / 65535, s, ctx, flog.official_lut(sim))

def fit_ev(lin16, ref, sim, lo=-3.0, hi=3.0, **kw):
    """EV mit kleinstem mittleren Luma-Fehler (Mitte des Bildes)."""
    sl = (slice(60, -60), slice(80, -80))
    yr = ref[sl].astype(np.float32) @ LUMA
    def err(ev):
        o = render(lin16, sim, ev, **kw)
        return np.abs(o[sl].astype(np.float32) @ LUMA - yr).mean()
    for _ in range(3):
        grid = np.linspace(lo, hi, 13); errs = [err(g) for g in grid]; b = grid[int(np.argmin(errs))]
        step = (hi - lo) / 12; lo, hi = b - step, b + step
    return b, min(errs)
