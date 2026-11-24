"""Minimaler Fujifilm-MakerNote-Parser (liest nur, ohne externe Tools).

Tag-Bedeutungen nach der oeffentlichen ExifTool-Tag-Dokumentation (FujiFilm::Main).
"""
from __future__ import annotations

import io
import struct

from PIL import Image

FILM_MODE = {0x000: "Provia", 0x100: "Studio Portrait", 0x110: "Studio Portrait Enhanced Saturation",
             0x120: "Astia", 0x130: "Studio Portrait Increased Sharpness", 0x200: "Velvia",
             0x300: "Studio Portrait Ex", 0x400: "Velvia", 0x500: "Pro Neg. Std", 0x501: "Pro Neg. Hi",
             0x600: "Classic Chrome", 0x700: "Eterna", 0x800: "Classic Neg.", 0x900: "Bleach Bypass",
             0xA00: "Nostalgic Neg.", 0xB00: "Reala Ace"}
WB_MODE = {0x0: "Auto", 0x1: "Auto (white priority)", 0x2: "Auto (ambiance priority)", 0x100: "Daylight",
           0x200: "Cloudy", 0x300: "Daylight Fluorescent", 0x301: "Day White Fluorescent",
           0x302: "White Fluorescent", 0x303: "Warm White Fluorescent", 0x400: "Incandescent",
           0x500: "Flash", 0x600: "Underwater", 0xF00: "Custom", 0xFF0: "Kelvin"}
TONE = {-64: "+4", -56: "+3.5", -48: "+3", -40: "+2.5", -32: "+2", -24: "+1.5", -16: "+1", -8: "+0.5",
        0: "0", 8: "-0.5", 16: "-1", 24: "-1.5", 32: "-2"}
ONOFF = {0: "Off", 32: "Weak", 64: "Strong"}
GRAIN_SIZE = {0: "Off", 16: "Small", 32: "Large"}
SHARP = {0: "-4", 1: "-3", 2: "-2", 3: "0", 4: "+2", 5: "+3", 6: "+4", 130: "-1", 132: "+1"}
COLOR = {0x0: "0", 0x80: "+1", 0x100: "+2", 0x180: "+3", 0x200: "+4", 0x400: "-1", 0x4C0: "-2",
         0x500: "-3", 0x600: "-4", 0x300: "B&W", 0x301: "B&W R", 0x302: "B&W Ye", 0x303: "B&W G",
         0x8000: "Film Simulation"}
_TYPES = {1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8), 6: ("b", 1), 7: ("B", 1),
          8: ("h", 2), 9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8)}


def read_makernote(path: str) -> dict:
    """-> {tag_id: Wert/Tupel}. Leeres dict, wenn kein Fuji-MakerNote vorhanden."""
    with open(path, "rb") as fh:
        data = fh.read()
    exif = Image.open(io.BytesIO(data)).getexif().get_ifd(0x8769)
    mn = exif.get(0x927C)
    if not mn or not bytes(mn).startswith(b"FUJIFILM"):
        return {}
    mn = bytes(mn)
    off = struct.unpack_from("<I", mn, 8)[0]
    n = struct.unpack_from("<H", mn, off)[0]
    out = {}
    for i in range(n):
        tag, typ, cnt, val = struct.unpack_from("<HHII", mn, off + 2 + i * 12)
        fmt, size = _TYPES.get(typ, ("B", 1))
        total = size * cnt
        if total <= 4:
            raw = mn[off + 2 + i * 12 + 8: off + 2 + i * 12 + 8 + total]
        else:
            raw = mn[val: val + total]
        try:
            if typ == 2:
                out[tag] = raw.split(b"\0")[0].decode("ascii", "replace")
            elif typ in (5, 10):
                vals = struct.unpack("<" + fmt[0] * (2 * cnt), raw)
                out[tag] = tuple(vals[j] / vals[j + 1] if vals[j + 1] else 0 for j in range(0, len(vals), 2))
            else:
                vals = struct.unpack("<" + fmt * cnt, raw)
                out[tag] = vals[0] if cnt == 1 else vals
        except struct.error:
            continue
    return out


def describe(path: str) -> dict:
    t = read_makernote(path)
    g = lambda k, m=None: (m.get(t.get(k), t.get(k)) if m else t.get(k))  # noqa: E731
    return {
        "film": g(0x1401, FILM_MODE),
        "dr_setting": g(0x1402), "dr": g(0x1403), "dr_mode": g(0x1400),
        "highlight": g(0x1041, TONE), "shadow": g(0x1040, TONE),
        "color": g(0x1003, COLOR), "sharpness": g(0x1001, SHARP),
        "wb": g(0x1002, WB_MODE), "wb_fine": g(0x100A), "color_temp": g(0x1005),
        "nr": g(0x100E), "grain": g(0x1047, ONOFF), "grain_size": g(0x104C, GRAIN_SIZE),
        "cce": g(0x1048, ONOFF), "cce_blue": g(0x104E, ONOFF),
        "raw_tags": {hex(k): v for k, v in t.items() if k in (0x1002, 0x1003, 0x1004, 0x100A, 0x100B, 0x100E,
                                                              0x1040, 0x1041, 0x1047, 0x1400, 0x1401, 0x1402, 0x1403)},
    }
