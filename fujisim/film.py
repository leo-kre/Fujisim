"""Parametrische Filmsimulationen.

Jede Simulation besteht aus: Tonkurve (S-Kurve, Schwarzpunkt, Schulter),
farbtonabhaengigen Aenderungen (Hue/Saettigung/Helligkeit in 8 Baendern),
globaler Saettigung und Split-Toning. Die Werte sind per Auge an die bekannten
Fuji-Looks angenaehert - fuer exakte Farben kann zusaetzlich eine .cube-LUT
geladen werden.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

BAND_NAMES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"]
BAND_CENTERS = np.array([0, 30, 60, 120, 180, 240, 285, 330], np.float32)


def _bands(**kw):
    """name=(hue_shift_deg, sat_delta, lum_delta)."""
    arr = np.zeros((3, 8), np.float32)
    for name, vals in kw.items():
        i = BAND_NAMES.index(name)
        arr[:, i] = vals
    return arr


@dataclass(frozen=True)
class Look:
    contrast: float = 0.3
    black: float = 0.0
    shoulder: float = 0.75
    shadows: float = 0.0
    sat: float = 1.0
    bands: np.ndarray = None  # shape (3, 8): dh, ds, dl
    shadow_tint: tuple = (0.0, 0.0, 0.0)
    highlight_tint: tuple = (0.0, 0.0, 0.0)
    mono: bool = False
    note: str = ""

    def scaled(self, k: float) -> "Look":
        bands = None if self.bands is None else self.bands * k
        return replace(
            self,
            contrast=self.contrast * k,
            black=self.black * k,
            shadows=self.shadows * k,
            sat=1.0 + (self.sat - 1.0) * k,
            bands=bands,
            shadow_tint=tuple(v * k for v in self.shadow_tint),
            highlight_tint=tuple(v * k for v in self.highlight_tint),
        )


FILMS: dict[str, Look] = {
    "Neutral": Look(contrast=0.15, sat=1.0, note="Kaum Look, nur sRGB-Basis"),
    "Provia": Look(
        contrast=0.35, sat=1.06, shoulder=0.78,
        bands=_bands(blue=(0, 0.05, 0), green=(0, 0.03, 0)),
        note="Standard, natuerlich",
    ),
    "Velvia": Look(
        contrast=0.8, black=-0.012, sat=1.32, shoulder=0.72,
        bands=_bands(red=(0, 0.10, -0.03), orange=(2, 0.06, 0), yellow=(0, 0.10, 0),
                     green=(-4, 0.18, -0.06), cyan=(0, 0.10, -0.04),
                     blue=(-3, 0.20, -0.10), magenta=(0, 0.08, 0)),
        note="Kraeftig, Landschaft",
    ),
    "Astia": Look(
        contrast=0.18, sat=1.0, shadows=0.12, shoulder=0.8,
        bands=_bands(orange=(0, -0.05, 0.02), red=(0, -0.03, 0), blue=(0, 0.06, 0),
                     green=(0, 0.04, 0)),
        note="Weich, Hauttoene",
    ),
    "Classic Chrome": Look(
        contrast=0.6, black=0.012, sat=0.80, shoulder=0.72,
        bands=_bands(red=(3, -0.08, -0.04), orange=(2, -0.10, -0.02),
                     yellow=(-4, -0.22, -0.04), green=(8, -0.32, -0.10),
                     cyan=(-4, -0.10, -0.14), blue=(-14, -0.08, -0.18),
                     purple=(-8, -0.20, -0.10), magenta=(0, -0.20, 0)),
        shadow_tint=(-0.010, 0.002, 0.016), highlight_tint=(0.014, 0.006, -0.012),
        note="Gedeckt, dokumentarisch",
    ),
    "Pro Neg. Std": Look(
        contrast=0.12, sat=0.86, shadows=0.08, shoulder=0.8,
        bands=_bands(orange=(0, -0.04, 0.02), green=(3, -0.08, 0), blue=(0, -0.04, 0)),
        note="Weich, Portrait",
    ),
    "Pro Neg. Hi": Look(
        contrast=0.4, sat=0.94, shoulder=0.76,
        bands=_bands(orange=(0, -0.02, 0.02), green=(3, -0.05, 0)),
        note="Etwas mehr Kontrast",
    ),
    "Classic Neg.": Look(
        contrast=0.7, black=0.01, sat=1.0, shoulder=0.7,
        bands=_bands(red=(-4, 0.12, -0.06), orange=(-2, 0.05, -0.02),
                     yellow=(-6, -0.10, 0), green=(12, -0.22, -0.16),
                     cyan=(-6, 0.05, -0.12), blue=(-14, -0.12, -0.20),
                     purple=(6, 0.05, -0.05), magenta=(8, 0.15, -0.04)),
        shadow_tint=(-0.020, 0.010, 0.020), highlight_tint=(0.024, 0.0, -0.014),
        note="Teal-Schatten, warme Lichter",
    ),
    "Nostalgic Neg.": Look(
        contrast=0.35, black=0.022, shadows=0.1, sat=0.97, shoulder=0.74,
        bands=_bands(red=(-2, 0.04, 0), orange=(0, 0.12, 0), yellow=(-4, 0.05, 0),
                     green=(6, -0.16, -0.06), cyan=(0, -0.10, -0.08),
                     blue=(-8, -0.20, -0.10), magenta=(4, 0.0, 0)),
        shadow_tint=(0.004, 0.0, 0.0), highlight_tint=(0.034, 0.012, -0.030),
        note="Warm, bernsteinfarben",
    ),
    "Eterna": Look(
        contrast=0.04, black=0.012, shadows=0.2, sat=0.80, shoulder=0.85,
        bands=_bands(green=(2, -0.10, -0.04), blue=(-4, -0.06, -0.04),
                     red=(0, -0.05, 0)),
        shadow_tint=(-0.004, 0.004, 0.010), highlight_tint=(0.006, 0.003, -0.004),
        note="Filmisch flach, Video-Look",
    ),
    "Eterna Bleach Bypass": Look(
        contrast=0.75, black=0.01, sat=0.50, shoulder=0.72,
        bands=_bands(blue=(-4, -0.1, -0.1), green=(0, -0.1, -0.05)),
        shadow_tint=(-0.005, 0.003, 0.008),
        note="Entsaettigt, hart (Naeherung ohne LUT)",
    ),
    "Reala Ace": Look(
        contrast=0.48, sat=1.0, shoulder=0.76,
        bands=_bands(red=(0, 0.04, -0.02), green=(0, 0.0, -0.03), blue=(-2, 0.04, -0.04)),
        highlight_tint=(0.005, 0.002, -0.004),
        note="Neutral mit Biss",
    ),
    "Acros": Look(contrast=0.62, black=-0.004, shoulder=0.74, mono=True,
                  note="Schwarzweiss, feine Tonwerte"),
    "Monochrome": Look(contrast=0.3, shoulder=0.8, mono=True, note="Schwarzweiss, weicher"),
}

MONO_FILTERS = {
    "none": (0.30, 0.59, 0.11),
    "yellow": (0.46, 0.46, 0.08),
    "red": (0.80, 0.18, 0.02),
    "green": (0.18, 0.70, 0.12),
}
