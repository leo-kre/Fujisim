"""Alle Einstellungen eines Bildes - benannt wie in der Fujifilm-Kamera (Rezepte)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field, fields

DR_CHOICES = ["DR100", "DR200", "DR400"]
EFFECT_CHOICES = ["Off", "Weak", "Strong"]
GRAIN_SIZES = ["Small", "Large"]
WB_MODES = ["Auto", "Daylight", "Shade", "Fluorescent 1", "Fluorescent 2", "Fluorescent 3",
            "Incandescent", "Kelvin"]
# Naeherungswerte der Kamera-Presets in Kelvin
WB_KELVIN = {"Daylight": 5500, "Shade": 7500, "Fluorescent 1": 6000, "Fluorescent 2": 4200,
             "Fluorescent 3": 5000, "Incandescent": 2900}
MONO_FILTERS_LIST = ["none", "yellow", "red", "green"]


@dataclass
class EditSettings:
    # --- Fuji-Kameraeinstellungen (Rezept) ---
    sim: str = "Provia"                 # Film Simulation
    dynamic_range: str = "DR100"        # DR100 / DR200 / DR400
    highlight_tone: float = 0.0         # -2 .. +4 (0.5er-Schritte)
    shadow_tone: float = 0.0            # -2 .. +4 (0.5er-Schritte)
    color: float = 0.0                  # -4 .. +4
    sharpness: float = 0.0              # -4 .. +4
    noise_reduction: float = 0.0        # -4 .. +4
    clarity: float = 0.0                # -5 .. +5
    grain_effect: str = "Off"           # Off / Weak / Strong
    grain_size: str = "Small"           # Small / Large
    color_chrome: str = "Off"           # Color Chrome Effect
    color_chrome_blue: str = "Off"      # Color Chrome FX Blue
    wb_mode: str = "Auto"
    wb_kelvin: float = 5500.0           # nur bei wb_mode == "Kelvin"
    wb_shift_r: float = 0.0             # -9 .. +9
    wb_shift_b: float = 0.0             # -9 .. +9
    mono_filter: str = "none"           # Acros: none / yellow / red / green
    mono_wc: float = 0.0                # Monochromatic Color, warm/cool -18..+18
    mono_mg: float = 0.0                # Monochromatic Color, magenta/green -18..+18
    # --- Belichtung ---
    auto_exposure: bool = True
    exposure: float = 0.0               # Belichtungskorrektur in EV
    # --- Zusaetze (nicht in der Kamera) ---
    intensity: float = 1.0
    contrast: float = 0.0               # -100..100
    halation: float = 0.0               # 0..1
    bloom: float = 0.0                  # 0..1
    vignette: float = 0.0               # 0..1
    lut_path: str = ""                  # eigene .cube-LUT (nach dem Look)
    lut_strength: float = 1.0
    # --- Grundlagen (wie Lightroom) ---
    saturation: float = 0.0             # -100..100
    vibrance: float = 0.0               # -100..100
    whites: float = 0.0                 # -100..100
    blacks: float = 0.0                 # -100..100
    # --- Farbkorrektur (Color Grading): je Zone Farbton (Grad), Saettigung 0..100, Luminanz -100..100 ---
    cg_sh_h: float = 0.0
    cg_sh_s: float = 0.0
    cg_sh_l: float = 0.0
    cg_mid_h: float = 0.0
    cg_mid_s: float = 0.0
    cg_mid_l: float = 0.0
    cg_hi_h: float = 0.0
    cg_hi_s: float = 0.0
    cg_hi_l: float = 0.0
    cg_gl_h: float = 0.0
    cg_gl_s: float = 0.0
    cg_gl_l: float = 0.0
    cg_blend: float = 50.0              # 0..100
    cg_balance: float = 0.0             # -100..100
    # --- Tonkurve: Punkte (x, y) in 0..1; RGB-Master + Einzelkanaele ---
    curve: list = field(default_factory=lambda: [[0.0, 0.0], [1.0, 1.0]])
    curve_r: list = field(default_factory=lambda: [[0.0, 0.0], [1.0, 1.0]])
    curve_g: list = field(default_factory=lambda: [[0.0, 0.0], [1.0, 1.0]])
    curve_b: list = field(default_factory=lambda: [[0.0, 0.0], [1.0, 1.0]])
    # --- Geometrie ---
    angle: float = 0.0                  # Gerade ausrichten, Grad (positiv = im Uhrzeigersinn), -45..45
    rot90: int = 0                      # Viertelumdrehungen im Uhrzeigersinn (0..3)
    flip_h: bool = False
    flip_v: bool = False
    crop_x: float = 0.0                 # Zuschnitt als Anteil der (gedrehten) Arbeitsflaeche
    crop_y: float = 0.0
    crop_w: float = 1.0
    crop_h: float = 1.0
    crop_aspect: str = "Original"       # nur Voreinstellung fuer den Zuschnitt-Dialog

    def copy(self) -> "EditSettings":
        return EditSettings(**asdict(self))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict) -> "EditSettings":
        names = {f.name for f in fields(EditSettings)}
        return EditSettings(**{k: v for k, v in d.items() if k in names})

    @staticmethod
    def from_json(text: str) -> "EditSettings":
        return EditSettings.from_dict(json.loads(text))


# Bei "Apply to all" optional pro Bild behalten
GEOMETRY_KEYS = ("angle", "rot90", "flip_h", "flip_v", "crop_x", "crop_y", "crop_w", "crop_h", "crop_aspect")
PER_IMAGE_KEYS = ("auto_exposure", "exposure", "wb_mode", "wb_kelvin", "wb_shift_r", "wb_shift_b")


def app_defaults() -> EditSettings:
    """Startwerte fuer neue Bilder (und 'Zuruecksetzen'). EditSettings() bleibt neutral."""
    return EditSettings(sim="Classic Chrome", grain_effect="Strong", grain_size="Large",
                        color_chrome="Strong", color_chrome_blue="Strong",
                        clarity=-1.0, noise_reduction=-4.0, color=1.0)
