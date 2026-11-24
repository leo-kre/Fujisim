"""RAW-Decoding (Sony ARW u.a.) ueber libraw/rawpy."""
from __future__ import annotations

import io
import os

import numpy as np
import rawpy
from PIL import Image

RAW_EXT = {".arw", ".srf", ".sr2", ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf", ".rw2"}
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def _wb_ratio(raw) -> np.ndarray:
    """Verhaeltnis Tageslicht-/Kamera-Weissabgleich (RGB, Gruen=1) als Naeherung."""
    try:
        cam = np.array(raw.camera_whitebalance[:3], np.float64)
        day = np.array(raw.daylight_whitebalance[:3], np.float64)
        if cam.min() > 0 and day.min() > 0:
            r = day / cam
            return (r / r[1]).astype(np.float32)
    except Exception:  # noqa: BLE001
        pass
    return np.ones(3, np.float32)


def _decode(path: str, half: bool):
    with rawpy.imread(path) as raw:
        ratio = _wb_ratio(raw)
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=16,
            gamma=(1, 1),
            output_color=rawpy.ColorSpace.ProPhoto,
            half_size=half,
        )
    return rgb, ratio


def _resize_u16(rgb: np.ndarray, long_edge: int) -> np.ndarray:
    h, w, _ = rgb.shape
    if max(h, w) <= long_edge:
        return rgb
    k = long_edge / max(h, w)
    nw, nh = max(2, round(w * k)), max(2, round(h * k))
    chans = []
    for c in range(3):
        im = Image.fromarray(rgb[..., c].astype(np.float32))
        chans.append(np.asarray(im.resize((nw, nh), Image.Resampling.BOX)))
    return np.clip(np.stack(chans, -1), 0, 65535).astype(np.uint16)


def auto_gain(lin: np.ndarray, target: float = 0.13) -> float:
    """Einfache Auto-Belichtung: Median der Luminanz auf ~target (linear)."""
    sub = lin[::4, ::4].astype(np.float32) / 65535.0
    y = sub @ LUMA
    med = float(np.percentile(y, 50))
    p995 = float(np.percentile(y, 99.5))
    gain = target / max(med, 1e-4)
    gain = min(gain, 2.2 / max(p995, 1e-4))  # Lichter nicht komplett wegbrennen
    return float(np.clip(gain, 0.6, 6.0))


def load_preview(path: str, long_edge: int = 1800):
    """-> (linear ProPhoto uint16 RGB, auto gain, wb_ratio). half_size beschleunigt das Decoding."""
    rgb, ratio = _decode(path, half=True)
    rgb = _resize_u16(rgb, long_edge)
    return rgb, auto_gain(rgb), ratio


def load_full(path: str):
    rgb, ratio = _decode(path, half=False)
    gain = auto_gain(rgb[::2, ::2])
    return rgb.astype(np.float32) / 65535.0, gain, ratio


def read_exif(path: str):
    """EXIF aus dem eingebetteten JPEG, Orientation auf 1 gesetzt."""
    try:
        with rawpy.imread(path) as raw:
            thumb = raw.extract_thumb()
        if thumb.format != rawpy.ThumbFormat.JPEG:
            return None
        exif = Image.open(io.BytesIO(thumb.data)).getexif()
        exif[0x0112] = 1
        return exif.tobytes()
    except Exception:
        return None


def thumb_bytes(path: str):
    """Eingebettetes JPEG der RAW (schnell, fuer den Filmstreifen) oder None."""
    try:
        with rawpy.imread(path) as raw:
            t = raw.extract_thumb()
        return t.data if t.format == rawpy.ThumbFormat.JPEG else None
    except Exception:  # noqa: BLE001
        return None


def is_dataless(path: str) -> bool:
    """macOS/iCloud: Datei ist nur ein Platzhalter (Lesen loest einen Download aus)."""
    try:
        return bool(os.stat(path).st_flags & 0x40000000)   # SF_DATALESS
    except (AttributeError, OSError):
        return False


# Feste Skalierung RAW -> Szene (wie die Kamera-Engine, kein Bild-Auto-Gain).
# Gemessen: Fuji X-T2 (13 RAF mit eingebettetem Kamera-JPEG): +1.12 EV, Streuung 0.04;
#           Sony A7 III (24 ARW gegen Sony-JPEG, Median-Abgleich): +1.04 EV, Streuung 0.15.
# Unterhalb des Basis-ISO (erweiterter ISO) skaliert die Kamera um die fehlenden Blenden herunter.
CAMERA_K = {"FUJIFILM": (1.12, 200), "SONY": (1.04, 100)}


def camera_gain(path: str):
    """-> (gain, Beschreibung) oder (None, '') wenn Kamera/ISO unbekannt (dann Auto-Gain)."""
    try:
        with rawpy.imread(path) as raw:
            t = raw.extract_thumb()
        if t.format != rawpy.ThumbFormat.JPEG:
            return None, ""
        ex = Image.open(io.BytesIO(t.data)).getexif()
        make = str(ex.get(0x010F, "")).upper()
        iso = ex.get_ifd(0x8769).get(0x8827)
        for name, (k, base) in CAMERA_K.items():
            if name in make:
                scale = min(1.0, float(iso) / base) if iso else 1.0
                return float(2.0 ** k * scale), f"{name.title()} ISO {iso}"
    except Exception:  # noqa: BLE001
        pass
    return None, ""
