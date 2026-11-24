"""Filmeffekte im linearen Raum: Halation, Bloom, Vignette (alles relativ zur Bildgroesse)."""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

R = Image.Resampling


def resize_ch(a: np.ndarray, w: int, h: int, resample) -> np.ndarray:
    return np.array(Image.fromarray(np.ascontiguousarray(a, np.float32)).resize((w, h), resample))


def resize3(a: np.ndarray, w: int, h: int, resample) -> np.ndarray:
    return np.stack([resize_ch(a[..., c], w, h, resample) for c in range(a.shape[2])], -1)


def reduce_box(a: np.ndarray, f: int) -> np.ndarray:
    """Box-Mittel ueber f x f Bloecke (Rand wird abgeschnitten)."""
    if f <= 1:
        return a
    H, W = a.shape[:2]
    h, w = H // f, W // f
    c = a[: h * f, : w * f]
    return c.reshape(h, f, w, f, *a.shape[2:]).mean((1, 3), dtype=np.float32)


def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Schneller Gauss: bei grossen Radien erst herunterskalieren. (H,W) oder (H,W,3)."""
    if img.ndim == 2:
        return blur(img[..., None], sigma)[..., 0]
    H, W, C = img.shape
    f = max(1, int(sigma / 2.5))
    if f > 1 and min(H, W) // f >= 4:
        w, h = max(2, W // f), max(2, H // f)
        small = resize3(img, w, h, R.BOX)
        s = sigma / f
    else:
        f, small, s = 1, img, sigma
    small = gaussian_filter(small, (s, s, 0), mode="nearest")
    if f > 1:
        small = resize3(small, W, H, R.BILINEAR)
    return small.astype(np.float32)


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def halation_bloom(x: np.ndarray, luma_w: np.ndarray, halation: float, bloom: float, long_px: float):
    """x: linear RGB (h,w,3). Rot-orange Halation + weicher Bloom. Rechnet auf verkleinerter Kopie."""
    H, W, _ = x.shape
    f = max(1, int(0.006 * long_px))
    if min(H, W) // f < 8:
        f = 1
    small = reduce_box(x, f)
    sh, sw = small.shape[:2]
    luma = small @ luma_w
    add = np.zeros_like(small)
    scale = 1.0 / f
    if halation > 0:
        hl = small * smoothstep(luma, 0.45, 1.3)[..., None]
        halo = 0.6 * blur(hl, 0.010 * long_px * scale) + 0.4 * blur(hl, 0.030 * long_px * scale)
        add += halation * 1.3 * halo * np.array([1.0, 0.30, 0.10], np.float32)
    soft = None
    if bloom > 0:
        bl = small * smoothstep(luma, 0.25, 1.0)[..., None]
        glow = 0.65 * blur(bl, 0.015 * long_px * scale) + 0.35 * blur(bl, 0.045 * long_px * scale)
        add += bloom * 0.8 * glow
        soft = blur(small, max(0.4, 0.004 * long_px * scale))
    if f > 1:
        add = resize3(add, W, H, R.BILINEAR)
        if soft is not None:
            soft = resize3(soft, W, H, R.BILINEAR)
    elif soft is not None and soft.shape[:2] != (H, W):
        soft = resize3(soft, W, H, R.BILINEAR)
    x = x + add
    if soft is not None:
        k = np.float32(0.3 * bloom)
        x = x * (1 - k) + soft * k
    return x


def vignette_gain(h: int, w: int, ox: float, oy: float, full_w: float, full_h: float, amount: float):
    """Vignette ueber absolute Koordinaten (Ausschnitt ox,oy im Gesamtbild der Groesse full_w x full_h)."""
    long = max(full_w, full_h)
    dx = (((np.arange(w, dtype=np.float32) + ox + 0.5) / full_w) - 0.5) * (full_w / long)
    dy = (((np.arange(h, dtype=np.float32) + oy + 0.5) / full_h) - 0.5) * (full_h / long)
    corner = np.sqrt((full_w / long) ** 2 + (full_h / long) ** 2) / 2
    r = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2) / corner
    stops = -2.6 * amount * smoothstep(r, 0.25, 1.05)
    return np.exp2(stops).astype(np.float32)[..., None]
