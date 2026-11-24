"""Tonkurve (Punktkurve, RGB + Einzelkanaele) und Color Grading (3 Farbraeder + Global) im Display-Raum."""
from __future__ import annotations

import colorsys

import numpy as np
from scipy.interpolate import PchipInterpolator

F32 = np.float32
LUMA = np.array([0.2126, 0.7152, 0.0722], F32)
IDENTITY = [[0.0, 0.0], [1.0, 1.0]]


def curve_is_identity(pts) -> bool:
    return not pts or [list(map(float, p)) for p in pts] == IDENTITY or all(abs(p[0] - p[1]) < 1e-6 for p in pts)


def curve_lut(pts, n: int = 1024) -> np.ndarray:
    """Monotone (PCHIP-)Kurve durch die Punkte -> Tabelle mit n Eintraegen fuer x = 0..1."""
    p = sorted((float(x), float(y)) for x, y in pts)
    xs, ys = [], []
    for x, y in p:                                  # doppelte x-Werte entfernen
        if xs and x <= xs[-1] + 1e-4:
            continue
        xs.append(min(max(x, 0.0), 1.0))
        ys.append(min(max(y, 0.0), 1.0))
    if len(xs) < 2:
        return np.linspace(0, 1, n, dtype=F32)
    f = PchipInterpolator(xs, ys, extrapolate=True)
    x = np.linspace(0, 1, n)
    y = np.where(x < xs[0], ys[0], np.where(x > xs[-1], ys[-1], f(x)))
    return np.clip(y, 0, 1).astype(F32)


def apply_curves(e: np.ndarray, master, red, green, blue) -> np.ndarray:
    """e: (h,w,3) in 0..1. Master-Kurve auf alle Kanaele, danach je Kanal."""
    out = np.clip(e, 0, 1).astype(F32)
    n = 1024
    xs = np.linspace(0, 1, n, dtype=F32)
    if not curve_is_identity(master):
        lut = curve_lut(master, n)
        out = np.interp(out, xs, lut).astype(F32)
    for c, pts in enumerate((red, green, blue)):
        if not curve_is_identity(pts):
            out[..., c] = np.interp(out[..., c], xs, curve_lut(pts, n))
    return out


def _tint(h: float, s: float) -> np.ndarray:
    """Luma-neutraler Farbvektor fuer Farbton h (Grad) und Saettigung s (0..100)."""
    if s <= 0:
        return np.zeros(3, F32)
    r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, 1.0, 1.0)
    v = np.array([r, g, b], F32)
    v = v - float(v @ LUMA)
    return v * F32(s / 100.0)


def has_grading(s) -> bool:
    return any(getattr(s, f"cg_{z}_{k}") for z in ("sh", "mid", "hi", "gl") for k in ("s", "l"))


def color_grade(e: np.ndarray, s) -> np.ndarray:
    """Drei Zonen (Schatten/Mitten/Lichter) mit weichem Uebergang + globales Rad.
    Balance verschiebt die Zonengrenze, Blending die Breite der Uebergaenge."""
    e = np.clip(e, 0, 1).astype(F32)
    y = e @ LUMA
    blend = min(max(s.cg_blend / 100.0, 0.0), 1.0)
    bal = min(max(s.cg_balance / 100.0, -1.0), 1.0)
    c = 0.5 - 0.25 * bal
    wd = 0.10 + 0.50 * blend
    t = np.clip((y - (c - wd)) / (2 * wd), 0.0, 1.0)
    t = t * t * (3 - 2 * t)
    w_sh, w_hi = (1 - t) ** 2, t ** 2
    w_mid = 1.0 - w_sh - w_hi
    out = e
    for w, z in ((w_sh, "sh"), (w_mid, "mid"), (w_hi, "hi"), (None, "gl")):
        hue, sat, lum = getattr(s, f"cg_{z}_h"), getattr(s, f"cg_{z}_s"), getattr(s, f"cg_{z}_l")
        if not sat and not lum:
            continue
        v = _tint(hue, sat) * F32(0.18)
        wz = 1.0 if w is None else w[..., None]
        out = out + wz * (v[None, None, :] + F32(lum / 100.0 * 0.15))
    return np.clip(out, 0, 1).astype(F32)
