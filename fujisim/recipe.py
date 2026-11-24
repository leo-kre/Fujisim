"""Fuji-Rezepte als Text einlesen/ausgeben (Format wie auf fujixweekly & Co.)."""
from __future__ import annotations

import re
from fractions import Fraction

from .film import FILMS
from .settings import EditSettings, WB_KELVIN, WB_MODES


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", s.lower())


_SIM_ALIASES = {
    "provia": "Provia", "proviastandard": "Provia", "proviastd": "Provia", "velvia": "Velvia", "velviavivid": "Velvia",
    "astia": "Astia", "astiasoft": "Astia", "classicchrome": "Classic Chrome",
    "pronegstd": "Pro Neg. Std", "pronegstandard": "Pro Neg. Std", "proneghi": "Pro Neg. Hi",
    "classicneg": "Classic Neg.", "classicnegative": "Classic Neg.",
    "nostalgicneg": "Nostalgic Neg.", "nostalgicnegative": "Nostalgic Neg.",
    "eterna": "Eterna", "eternacinema": "Eterna", "eternableachbypass": "Eterna Bleach Bypass",
    "realaace": "Reala Ace", "acros": "Acros", "monochrome": "Monochrome", "neutral": "Neutral",
}


def _num(text: str):
    """'+2', '-1.5', '+1 1/3', '2/3' -> float (erster Wert, Bereiche -> erster Wert)."""
    text = text.replace("−", "-").replace("–", "-")
    m = re.search(r"([+-]?)\s*(\d+)\s+(\d+)/(\d+)", text)
    if m:
        v = int(m.group(2)) + Fraction(int(m.group(3)), int(m.group(4)))
        return float(-v if m.group(1) == "-" else v)
    m = re.search(r"([+-]?)\s*(\d+)/(\d+)", text)
    if m:
        v = Fraction(int(m.group(2)), int(m.group(3)))
        return float(-v if m.group(1) == "-" else v)
    m = re.search(r"[+-]?\d+(?:[.,]\d+)?", text)
    return float(m.group(0).replace(",", ".")) if m else None


def _effect(text: str):
    t = text.lower()
    for key, val in (("strong", "Strong"), ("weak", "Weak"), ("off", "Off")):
        if key in t:
            return val
    return None


def parse_recipe(text: str):
    """-> (dict mit EditSettings-Feldern, Liste nicht erkannter Zeilen)."""
    out: dict = {}
    unknown: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-•*· ").strip()
        if not line or ":" not in line:
            if line:
                unknown.append(raw)
            continue
        key, val = line.split(":", 1)
        k, v = _norm(key), val.strip()
        vl = v.lower()
        ok = True
        if k in ("filmsimulation", "filmsim", "simulation", "film"):
            nv = _norm(re.sub(r"\(.*?\)", "", v))
            mono = None
            for suffix, f in (("+ye", "yellow"), ("+y", "yellow"), ("+r", "red"), ("+g", "green")):
                if nv.startswith("acros") and nv.endswith(suffix):
                    mono, nv = f, "acros"
                    break
            nv = nv.replace("+", "")
            sim = _SIM_ALIASES.get(nv) or next((n for n in FILMS if _norm(n) == nv), None)
            if sim:
                out["sim"] = sim
                if mono:
                    out["mono_filter"] = mono
            else:
                ok = False
        elif k in ("dynamicrange", "dr"):
            m = re.search(r"(\d{3})", v)
            out["dynamic_range"] = f"DR{m.group(1)}" if m and m.group(1) in ("100", "200", "400") else "DR100"
        elif k in ("highlight", "highlights", "highlighttone"):
            n = _num(v); ok = n is not None
            if ok: out["highlight_tone"] = n
        elif k in ("shadow", "shadows", "shadowtone"):
            n = _num(v); ok = n is not None
            if ok: out["shadow_tone"] = n
        elif k in ("color", "colour"):
            n = _num(v); ok = n is not None
            if ok: out["color"] = n
        elif k in ("noisereduction", "highisonr", "nr"):
            n = _num(v); ok = n is not None
            if ok: out["noise_reduction"] = n
        elif k in ("sharpness", "sharpening", "sharpen"):
            n = _num(v); ok = n is not None
            if ok: out["sharpness"] = n
        elif k == "clarity":
            n = _num(v); ok = n is not None
            if ok: out["clarity"] = n
        elif k in ("graineffect", "grain"):
            out["grain_effect"] = _effect(v) or "Off"
            out["grain_size"] = "Large" if "large" in vl else "Small"
        elif k in ("colorchromeeffect", "colourchromeeffect", "colorchrome", "cce"):
            e = _effect(v); ok = e is not None
            if ok: out["color_chrome"] = e
        elif k in ("colorchromefxblue", "colourchromefxblue", "fxblue", "colorchromeblue", "chromeblue"):
            e = _effect(v); ok = e is not None
            if ok: out["color_chrome_blue"] = e
        elif k in ("whitebalance", "wb"):
            mode = "Auto"
            mk = re.search(r"(\d{4,5})\s*k", vl)
            if mk:
                mode, out["wb_kelvin"] = "Kelvin", float(mk.group(1))
            elif "daylight" in vl and "fluor" not in vl:
                mode = "Daylight"
            elif "shade" in vl:
                mode = "Shade"
            elif "incandescent" in vl or "tungsten" in vl:
                mode = "Incandescent"
            elif "fluor" in vl:
                mode = "Fluorescent 1"
                if "3" in vl or "cool" in vl: mode = "Fluorescent 3"
                elif "2" in vl or "warm" in vl: mode = "Fluorescent 2"
            out["wb_mode"] = mode
            r = re.search(r"([+-]?\d+)\s*red", vl); b = re.search(r"([+-]?\d+)\s*blue", vl)
            out["wb_shift_r"] = float(r.group(1)) if r else 0.0
            out["wb_shift_b"] = float(b.group(1)) if b else 0.0
        elif k in ("monochromaticcolor", "monochromecolor", "mono"):
            wc = re.search(r"wc\s*([+-]?\d+)", vl); mg = re.search(r"mg\s*([+-]?\d+)", vl)
            if wc: out["mono_wc"] = float(wc.group(1))
            if mg: out["mono_mg"] = float(mg.group(1))
            ok = bool(wc or mg)
        elif k in ("iso", "exposurecompensation", "exposurecomp", "ev", "dynamicrangepriority",
                   "sensor", "camera", "cameras", "smoothskineffect", "lens", "highisonr"):
            pass  # bewusst ignoriert (pro Bild)
        else:
            ok = False
        if not ok:
            unknown.append(raw)
    return out, unknown


def apply_recipe(s: EditSettings, text: str):
    d, unknown = parse_recipe(text)
    new = s.copy()
    for k, v in d.items():
        setattr(new, k, v)
    return new, d, unknown


def _signed(v: float) -> str:
    return f"{v:+g}" if v else "0"


def to_text(s: EditSettings) -> str:
    wb = s.wb_mode if s.wb_mode != "Kelvin" else f"{int(s.wb_kelvin)}K"
    lines = [
        f"Film Simulation: {s.sim}" + (f" ({s.mono_filter} filter)" if s.mono_filter != "none" else ""),
        f"Dynamic Range: {s.dynamic_range}",
        f"Highlight: {_signed(s.highlight_tone)}",
        f"Shadow: {_signed(s.shadow_tone)}",
        f"Color: {_signed(s.color)}",
        f"Noise Reduction: {_signed(s.noise_reduction)}",
        f"Sharpening: {_signed(s.sharpness)}",
        f"Clarity: {_signed(s.clarity)}",
        f"Grain Effect: {s.grain_effect}" + (f", {s.grain_size}" if s.grain_effect != "Off" else ""),
        f"Color Chrome Effect: {s.color_chrome}",
        f"Color Chrome FX Blue: {s.color_chrome_blue}",
        f"White Balance: {wb}, {_signed(s.wb_shift_r)} Red & {_signed(s.wb_shift_b)} Blue",
    ]
    if s.sim in ("Acros", "Monochrome"):
        lines.append(f"Monochromatic Color: WC {_signed(s.mono_wc)} / MG {_signed(s.mono_mg)}")
    return "\n".join(lines)
