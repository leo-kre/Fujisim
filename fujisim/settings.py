"""Alle Einstellungen eines Bildes - benannt wie in der Fujifilm-Kamera (Rezepte)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields

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
PER_IMAGE_KEYS = ("auto_exposure", "exposure", "wb_mode", "wb_kelvin", "wb_shift_r", "wb_shift_b")


def app_defaults() -> EditSettings:
    """Startwerte fuer neue Bilder (und 'Zuruecksetzen'). EditSettings() bleibt neutral."""
    return EditSettings(sim="Classic Chrome", grain_effect="Strong", grain_size="Large",
                        color_chrome="Strong", color_chrome_blue="Strong",
                        clarity=-1.0, noise_reduction=-4.0, color=1.0)
