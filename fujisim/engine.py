"""Kern: haelt genau EIN Bild (ImageSession), rendert beliebige Ausschnitte in Zielaufloesung.

* Pyramide aus linearen uint16-Stufen (1/1, 1/2, 1/4, ...): je nach Zoom wird die passende
  Stufe verwendet -> Vorschauqualitaet haengt vom sichtbaren Bereich ab.
* render() liefert nur den sichtbaren Ausschnitt (Groesse ~ Bildschirmpixel), egal wie gross das Foto ist.
* Export arbeitet kachelweise (geringer Speicherbedarf).
"""
from __future__ import annotations

import math
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from . import flog, lut as lutmod, raw_io
from .pipeline import Ctx, margin_px, process_region
from .settings import EditSettings

_lut_cache: dict[str, lutmod.Lut] = {}
_pool = ThreadPoolExecutor(3)
BILINEAR = Image.Resampling.BILINEAR


def get_lut(path: str):
    if not path:
        return None
    if path not in _lut_cache:
        _lut_cache[path] = lutmod.load_cube(path)
    return _lut_cache[path]


def seed_for(path: str) -> int:
    return zlib.crc32(path.encode()) & 0x7FFFFFFF


def _down2(a: np.ndarray) -> np.ndarray:
    h2, w2 = a.shape[0] // 2, a.shape[1] // 2
    b = a[: h2 * 2, : w2 * 2].astype(np.uint32)
    return ((b[0::2, 0::2] + b[1::2, 0::2] + b[0::2, 1::2] + b[1::2, 1::2] + 2) >> 2).astype(np.uint16)


class ImageSession:
    """Das aktuell bearbeitete Bild. Alles andere wird nicht im Speicher gehalten."""

    def __init__(self, path: str):
        self.path = path
        self.levels: dict[int, np.ndarray] = {}
        self.W = self.H = 0
        self.gain = 1.0
        self.ratio = None
        self.seed = seed_for(path)
        self.gain_info = ""

    # ---- Laden ----
    @staticmethod
    def open_fast(path: str) -> "ImageSession":
        """Halbe Aufloesung (ohne Demosaicing-Aufwand): sofort editierbar."""
        s = ImageSession(path)
        rgb, s.ratio = raw_io._decode(path, half=True)
        s.levels[1] = rgb
        s.W, s.H = rgb.shape[1] * 2, rgb.shape[0] * 2
        cg, s.gain_info = raw_io.camera_gain(path)
        s.gain = cg if cg else raw_io.auto_gain(rgb[::2, ::2])
        if not cg:
            s.gain_info = "Auto (Kamera unbekannt)"
        s._build(1)
        return s

    def load_full(self) -> None:
        """Volle Aufloesung nachladen (laeuft im Hintergrund)."""
        rgb, ratio = raw_io._decode(self.path, half=False)
        self.W, self.H = rgb.shape[1], rgb.shape[0]
        lv = {0: rgb}
        a = rgb
        for k in range(1, 7):
            if min(a.shape[:2]) < 400:
                break
            a = _down2(a)
            lv[k] = a
        self.levels = lv  # atomar ersetzen
        self.ratio = ratio

    @property
    def has_full(self) -> bool:
        return 0 in self.levels

    def _build(self, start: int) -> None:
        a = self.levels[start]
        for k in range(start + 1, 7):
            if min(a.shape[:2]) < 400:
                break
            a = _down2(a)
            self.levels[k] = a

    # ---- Ausschnitt in Ausgabeaufloesung holen ----
    def _extract(self, z: float, xa: int, ya: int, w: int, h: int) -> np.ndarray:
        levels = self.levels
        want = max(0, int(math.floor(math.log2(1.0 / z)))) if z < 1 else 0
        keys = sorted(levels)
        L = next((k for k in keys if k >= want), keys[-1])
        arr = levels[L]
        Hl, Wl = arr.shape[:2]
        f = z * (2 ** L)  # Ausgabepixel pro Level-Pixel
        lx0, lx1 = xa / f, (xa + w) / f
        ly0, ly1 = ya / f, (ya + h) / f
        ix0, iy0 = max(0, int(math.floor(lx0)) - 1), max(0, int(math.floor(ly0)) - 1)
        ix1, iy1 = min(Wl, int(math.ceil(lx1)) + 1), min(Hl, int(math.ceil(ly1)) + 1)
        crop = arr[iy0:iy1, ix0:ix1]
        cw, chh = crop.shape[1], crop.shape[0]
        box = (min(max(lx0 - ix0, 0.0), cw - 1e-3), min(max(ly0 - iy0, 0.0), chh - 1e-3),
               min(max(lx1 - ix0, 1e-3), cw), min(max(ly1 - iy0, 1e-3), chh))

        def one(c):
            im = Image.fromarray(crop[..., c].astype(np.float32))
            return np.array(im.resize((w, h), BILINEAR, box=box))

        chans = list(_pool.map(one, range(3)))
        out = np.stack(chans, -1)
        out *= np.float32(1.0 / 65535.0)
        return out

    # ---- Rendern ----
    def render(self, s: EditSettings, z: float, X0: int, Y0: int, cw: int, ch: int) -> np.ndarray:
        """Ausschnitt [X0,X0+cw) x [Y0,Y0+ch) im Ausgabegitter (Gesamtbild = W*z x H*z)."""
        Wz, Hz = self.W * z, self.H * z
        iw, ih = max(1, int(round(Wz))), max(1, int(round(Hz)))
        X0, Y0 = max(0, X0), max(0, Y0)
        cw, ch = min(cw, iw - X0), min(ch, ih - Y0)
        m = margin_px(s, max(Wz, Hz))
        xa, ya = max(0, X0 - m), max(0, Y0 - m)
        xb, yb = min(iw, X0 + cw + m), min(ih, Y0 + ch + m)
        ctx = Ctx(z, Wz, Hz, xa, ya, self.seed, self.gain, self.ratio)
        lin = self._extract(z, xa, ya, xb - xa, yb - ya)
        out = process_region(lin, s, ctx, flog.official_lut(s.sim), get_lut(s.lut_path))
        return out[Y0 - ya: Y0 - ya + ch, X0 - xa: X0 - xa + cw]


def export_file(path: str, s: EditSettings, out_path: str, quality: int = 95, max_edge: int = 0,
                tile: int = 1024) -> None:
    """Voller Export, kachelweise. Haelt nur dieses eine Bild."""
    sess = ImageSession(path)
    rgb, sess.ratio = raw_io._decode(path, half=False)
    sess.W, sess.H = rgb.shape[1], rgb.shape[0]
    cg, _ = raw_io.camera_gain(path)
    sess.gain = cg if cg else raw_io.auto_gain(rgb[::4, ::4])
    sess.levels = {0: rgb}
    z = 1.0
    if max_edge and max(sess.W, sess.H) > max_edge:
        z = max_edge / max(sess.W, sess.H)
        sess._build(0)
    iw, ih = int(round(sess.W * z)), int(round(sess.H * z))
    out = np.empty((ih, iw, 3), np.uint8)
    for y in range(0, ih, tile):
        th = min(tile, ih - y)
        out[y:y + th] = sess.render(s, z, 0, y, iw, th)
    del sess, rgb
    img = Image.fromarray(out)
    if out_path.lower().endswith((".jpg", ".jpeg")):
        exif = raw_io.read_exif(path)
        kw = {"quality": quality, "subsampling": 0, "optimize": True}
        if exif:
            kw["exif"] = exif
        img.save(out_path, "JPEG", **kw)
    else:
        img.save(out_path)
