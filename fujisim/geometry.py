"""Geometrie: Spiegeln, Drehen (90 Grad + beliebig), Zuschneiden.

Koordinatenketten (y zeigt nach unten, Winkel positiv = im Uhrzeigersinn):
    Quelle --(flip_h/flip_v)--> --(rot90 mal 90 Grad)--> Arbeitsflaeche W' x H'
    --(angle um die Mitte)--> gedrehte Arbeitsflaeche --(Zuschnitt)--> Ausgabe.
Der Zuschnitt (crop_*) liegt in der gedrehten Arbeitsflaeche, normiert auf W' x H'.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import affine_transform

from .settings import EditSettings

ASPECTS = {"Original": None, "Frei": 0.0, "1:1": 1.0, "4:5": 4 / 5, "5:4": 5 / 4, "3:2": 3 / 2, "2:3": 2 / 3,
           "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4, "65:24 (Panorama)": 65 / 24}


def canvas_size(s: EditSettings, W: float, H: float) -> tuple[float, float]:
    return (H, W) if s.rot90 % 2 else (W, H)


def is_identity(s: EditSettings) -> bool:
    return (s.angle == 0 and s.rot90 % 4 == 0 and not s.flip_h and not s.flip_v
            and s.crop_x == 0 and s.crop_y == 0 and s.crop_w == 1 and s.crop_h == 1)


def out_size(s: EditSettings, W: int, H: int) -> tuple[int, int]:
    """Groesse des Ergebnisses bei Zoom 1 (Pixel)."""
    cw, ch = canvas_size(s, W, H)
    return max(1, int(round(s.crop_w * cw))), max(1, int(round(s.crop_h * ch)))


def inside_fraction(s: EditSettings, W: int, H: int, rect=None) -> float:
    """Wie weit muss der Zuschnitt (um seine Mitte) geschrumpft werden, damit er im gedrehten Bild liegt? (<= 1)"""
    cw, ch = canvas_size(s, W, H)
    x0, y0, w, h = rect or (s.crop_x, s.crop_y, s.crop_w, s.crop_h)
    x0, y0, w, h = x0 * cw, y0 * ch, w * cw, h * ch
    th = math.radians(s.angle)
    c, sn = math.cos(th), math.sin(th)
    mx, my = x0 + w / 2, y0 + h / 2

    def ok(f):
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            qx, qy = mx + dx * w * f / 2 - cw / 2, my + dy * h * f / 2 - ch / 2
            px = c * qx + sn * qy + cw / 2          # R(-theta)
            py = -sn * qx + c * qy + ch / 2
            if px < -1e-6 or py < -1e-6 or px > cw + 1e-6 or py > ch + 1e-6:
                return False
        return True
    if ok(1.0):
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def fit_crop(s: EditSettings, W: int, H: int) -> None:
    """Zuschnitt in-place so anpassen, dass keine leeren Raender entstehen (schrumpft um die Mitte)."""
    f = inside_fraction(s, W, H)
    if f < 1.0:
        mx, my = s.crop_x + s.crop_w / 2, s.crop_y + s.crop_h / 2
        s.crop_w *= f
        s.crop_h *= f
        s.crop_x, s.crop_y = mx - s.crop_w / 2, my - s.crop_h / 2


def aspect_crop(s: EditSettings, W: int, H: int, ratio: float) -> None:
    """Groesstes Rechteck mit Seitenverhaeltnis `ratio` (B/H) um die Mitte des aktuellen Zuschnitts, das im Bild liegt."""
    cw, ch = canvas_size(s, W, H)
    mx, my = s.crop_x + s.crop_w / 2, s.crop_y + s.crop_h / 2
    w = s.crop_w * cw
    h = w / ratio
    if h > s.crop_h * ch:
        h = s.crop_h * ch
        w = h * ratio
    s.crop_w, s.crop_h = w / cw, h / ch
    s.crop_x, s.crop_y = mx - s.crop_w / 2, my - s.crop_h / 2
    fit_crop(s, W, H)
    s.crop_x = min(max(s.crop_x, 0.0), 1 - s.crop_w)
    s.crop_y = min(max(s.crop_y, 0.0), 1 - s.crop_h)


def _src_to_canvas(s: EditSettings, Wz: float, Hz: float) -> np.ndarray:
    """3x3 (x,y,1): Quelle (Groesse Wz x Hz) -> Arbeitsflaeche."""
    M = np.eye(3)
    if s.flip_h:
        M = np.array([[-1, 0, Wz], [0, 1, 0], [0, 0, 1]], float) @ M
    if s.flip_v:
        M = np.array([[1, 0, 0], [0, -1, Hz], [0, 0, 1]], float) @ M
    w, h = Wz, Hz
    for _ in range(s.rot90 % 4):                 # 90 Grad im Uhrzeigersinn: (x,y) -> (h - y, x)
        M = np.array([[0, -1, h], [1, 0, 0], [0, 0, 1]], float) @ M
        w, h = h, w
    return M


def out_to_src(s: EditSettings, Wz: float, Hz: float, z: float) -> np.ndarray:
    """3x3: Ausgabepixel-Koordinate (Gitter bei Zoom z, y/x in Pixelkanten) -> Quelle (Koordinaten im z-skalierten Bild Wz x Hz)."""
    cw, ch = canvas_size(s, Wz, Hz)
    th = math.radians(s.angle)
    c, sn = math.cos(th), math.sin(th)
    T_crop = np.array([[1, 0, s.crop_x * cw], [0, 1, s.crop_y * ch], [0, 0, 1]], float)   # Ausgabe -> gedrehte Flaeche
    C = np.array([[1, 0, cw / 2], [0, 1, ch / 2], [0, 0, 1]], float)
    Cm = np.array([[1, 0, -cw / 2], [0, 1, -ch / 2], [0, 0, 1]], float)
    R = np.array([[c, sn, 0], [-sn, c, 0], [0, 0, 1]], float)                               # R(-theta)
    return np.linalg.inv(_src_to_canvas(s, Wz, Hz)) @ C @ R @ Cm @ T_crop


def source_bbox(s: EditSettings, Wz: float, Hz: float, z: float, x0, y0, w, h, pad=2):
    """Achsparalleles Quellrechteck (z-skaliert, ganzzahlig, auf das Bild begrenzt), das den Ausgabeausschnitt abdeckt."""
    M = out_to_src(s, Wz, Hz, z)
    pts = np.array([[x0, y0, 1], [x0 + w, y0, 1], [x0, y0 + h, 1], [x0 + w, y0 + h, 1]], float) @ M.T
    xa = max(0, int(math.floor(pts[:, 0].min())) - pad)
    ya = max(0, int(math.floor(pts[:, 1].min())) - pad)
    xb = min(int(round(Wz)), int(math.ceil(pts[:, 0].max())) + pad)
    yb = min(int(round(Hz)), int(math.ceil(pts[:, 1].max())) + pad)
    return xa, ya, max(1, xb - xa), max(1, yb - ya)


def warp(src: np.ndarray, s: EditSettings, Wz: float, Hz: float, z: float, bbox, x0, y0, w, h) -> np.ndarray:
    """src: float32 (bh,bw,3) = Quellrechteck `bbox` (z-skaliert). -> (h,w,3) Ausgabeausschnitt ab Ausgabepixel (x0,y0)."""
    M = out_to_src(s, Wz, Hz, z)
    xa, ya = bbox[0], bbox[1]
    # Indexraum: Pixelmitte = Index + 0.5
    P = np.array([[1, 0, x0 + 0.5], [0, 1, y0 + 0.5], [0, 0, 1]], float)
    Q = np.array([[1, 0, -xa - 0.5], [0, 1, -ya - 0.5], [0, 0, 1]], float)
    A = Q @ M @ P                                    # Ausgabe-Index (x,y) -> Quell-Index (x,y)
    mat = np.array([[A[1, 1], A[1, 0]], [A[0, 1], A[0, 0]]])       # (row, col)
    off = np.array([A[1, 2], A[0, 2]])
    out = np.empty((h, w, 3), np.float32)
    # Volle Arbeitsflaeche gedreht (Zuschneiden-Ansicht): Flaechen ausserhalb des Bildes schwarz zeigen
    full = s.angle != 0 and s.crop_x <= 1e-4 and s.crop_y <= 1e-4 and s.crop_w >= 0.9999 and s.crop_h >= 0.9999
    for ch in range(3):
        out[..., ch] = affine_transform(src[..., ch], mat, offset=off, output_shape=(h, w), order=1,
                                        mode="constant" if full else "nearest", cval=0.0)
    return out
