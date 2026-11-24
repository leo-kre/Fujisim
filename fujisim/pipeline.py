"""Bildpipeline fuer einen Bildausschnitt: linear (ProPhoto) -> Fuji-Look -> sRGB uint8.

Alle groessenabhaengigen Parameter sind relativ zur langen Kante des Gesamtbildes im
Ausgabemassstab (ctx.long_px) -> Vorschau, Zoom und Export sehen gleich aus.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import effects, flog, grading, kernels
from .film import BAND_CENTERS, FILMS, MONO_FILTERS
from .settings import EditSettings, WB_KELVIN

F32 = np.float32
# Grain, gemessen an X-T5/X-T30-JPEGs (100%-Ausschnitte): Korn-Std in 8-bit-Stufen Weak ~2.0, Strong ~5.5 bei
# nativer Aufloesung, fast nur Helligkeit; Autokorrelation bei 1 px: Small ~0.16 (fast weiss), Large ~0.45 -> Zelle ~1 px / ~1.5 px bei 7728 px langer Kante.
GRAIN_AMOUNT = {"Off": 0.0, "Weak": 0.063, "Strong": 0.175}
GRAIN_SIZE = {"Small": 1.29e-4, "Large": 1.94e-4}   # Zellgroesse als Anteil der langen Kante
CHROME_AMOUNT = {"Off": 0.0, "Weak": 0.5, "Strong": 1.0}
# DR200/400: NICHT gemessen (keine Referenzdaten). Mildes Knie erst ab ~1.5 Blenden ueber Mittelgrau.
DR_ROLL = {"DR100": 1.0, "DR200": 0.75, "DR400": 0.55}
DR_KNEE = 0.5
# DR400: gemessen an 5 Rezepten auf derselben Aufnahme (fujixweekly, GFX100S II): Kamera hebt Schatten/Mitten gegenueber
# dem Modell um bis zu +12 % des Displaywerts (Luma-Rest bei e=0.08/0.25/0.42/0.58/0.75/0.92: +8/+11/+12/+8/+3.5/+1.6 %).
# DR200 zeigte keinen Rest (Nostalgic Americana) -> keine Anhebung.
DR_LIFT = {"DR400": ([0.0, 0.08, 0.25, 0.42, 0.58, 0.75, 0.92, 1.0], [0.043, 0.07, 0.091, 0.102, 0.071, 0.030, 0.014, 0.0])}
LUMA_S = np.array([0.2126, 0.7152, 0.0722], F32)
_NEUTRAL_BANDS = np.zeros((3, 8))


@dataclass
class Ctx:
    z: float            # Ausgabepixel pro Originalpixel
    full_w: float       # Gesamtbild im Ausgabemassstab (z * Originalgroesse)
    full_h: float
    ox: float           # Position der linken oberen Ecke des Ausschnitts im Ausgabegitter
    oy: float
    seed: int = 0
    gain: float = 1.0
    ratio: object = None

    @property
    def long_px(self) -> float:
        return max(self.full_w, self.full_h)


def oetf(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(F32)


def sigmoid_params(c: float):
    k = 6.0 * c
    g0 = float(1 / (1 + np.exp(k * 0.45)))
    g1 = float(1 / (1 + np.exp(-k * 0.55)))
    return k, g0, g1


KELVIN_STRENGTH = 0.4     # Exponent auf die Kelvin-Gains: Kamera wirkt deutlich schwaecher als "Licht neutralisieren" (7 Rezepte, eine Szene)
SHIFT_STEP_R = 0.05       # log2 pro WB-Shift-Stufe
SHIFT_STEP_B = 0.08       # Blau-Shift wirkt staerker als Rot (gleiche 7 Rezepte; Rot 0.05 beibehalten)


def wb_gains(s: EditSettings, ratio) -> np.ndarray:
    g = np.ones(3, F32)
    if s.wb_mode != "Auto":
        if ratio is not None:
            g = g * np.asarray(ratio, F32)
        k = s.wb_kelvin if s.wb_mode == "Kelvin" else WB_KELVIN.get(s.wb_mode, 5500)
        g = g * np.power(flog.kelvin_gains(k), KELVIN_STRENGTH).astype(F32)
    return g * np.array([2 ** (SHIFT_STEP_R * s.wb_shift_r), 1.0, 2 ** (SHIFT_STEP_B * s.wb_shift_b)], F32)


def _parametric_tone(x, look):
    sh = look.shoulder
    x = np.where(x > sh, sh + (1 - sh) * np.tanh((x - sh) / (1 - sh)), x).astype(F32)
    e = oetf(x)
    k = 6.0 * look.contrast
    if abs(k) > 1e-3:
        _, g0, g1 = sigmoid_params(look.contrast)
        e = ((1 / (1 + np.exp(-k * (e - 0.45)))) - g0) / (g1 - g0)
    e = look.black + e * (1 - look.black)
    e = e + 0.2 * look.shadows * 6.75 * e * (1 - e) ** 2
    return np.clip(e, 0, 1).astype(F32)


def margin_px(s: EditSettings, long_px: float) -> int:
    """Wie viele Pixel Kontext um den Ausschnitt noetig sind (fuer Unschaerfe-Effekte)."""
    m = 6
    if s.halation > 0 or s.bloom > 0:
        m = max(m, int(0.08 * long_px))
    if s.clarity:
        m = max(m, int(0.08 * long_px))
    return m


def process_region(lin: np.ndarray, s: EditSettings, ctx: Ctx, fuji_lut=None, custom_lut=None) -> np.ndarray:
    """lin: float32 (h,w,3) linear ProPhoto im Ausgabemassstab. -> uint8 (h,w,3)."""
    h, w, _ = lin.shape
    look = FILMS.get(s.sim, FILMS["Neutral"]).scaled(s.intensity)
    use_fuji = fuji_lut is not None
    long_px = ctx.long_px

    # Belichtung + WB + Farbraum in einer Matrix
    ev = s.exposure + (np.log2(max(ctx.gain, 1e-4)) if s.auto_exposure else 0.0)
    M = flog.PRO_TO_FGC if use_fuji else flog.PRO_TO_SRGB
    M2 = (M * (wb_gains(s, ctx.ratio) * F32(2.0 ** ev))[None, :]).astype(F32)
    x = (lin.reshape(-1, 3) @ M2.T).reshape(h, w, 3)
    np.maximum(x, 0, out=x)
    luma_w = flog.LUMA_FGC if use_fuji else flog.LUMA_SRGB

    if s.halation > 0 or s.bloom > 0:
        x = effects.halation_bloom(x, luma_w, s.halation, s.bloom, long_px)
    if s.vignette > 0:
        x = x * effects.vignette_gain(h, w, ctx.ox, ctx.oy, ctx.full_w, ctx.full_h, s.vignette)

    r = DR_ROLL.get(s.dynamic_range, 1.0)
    is_mono = look.mono
    mono_w = np.array(MONO_FILTERS.get(s.mono_filter, MONO_FILTERS["none"]), F32)

    # ---- Look ----
    e = np.empty_like(x)
    if use_fuji:
        if is_mono and s.mono_filter != "none":
            x = np.repeat((x @ mono_w)[..., None], 3, -1)
        kernels.k_lut_look(np.ascontiguousarray(x), fuji_lut.table, fuji_lut.dmin.astype(np.float64),
                           ((fuji_lut.size - 1) / np.maximum(fuji_lut.dmax - fuji_lut.dmin, 1e-6)).astype(np.float64),
                           DR_KNEE, r, e)
        corr = flog.official_correction(s.sim)
        if corr is not None:     # gelernte Differenz LUT -> Kamera-JPEG (Foto- statt Video-Rendering)
            kernels.k_corr(e, corr, 1.0)
        if s.intensity < 1.0:
            xs = x @ (flog.PRO_TO_SRGB @ np.linalg.inv(flog.PRO_TO_FGC)).T.astype(F32)
            neutral = _parametric_tone(xs, FILMS["Neutral"])
            e = neutral + (e - neutral) * F32(s.intensity)
        bands, sat_base, do_tints = None, 1.0, False
    else:
        if r < 1.0:
            x = np.where(x > DR_KNEE, DR_KNEE + (x - DR_KNEE) * r, x).astype(F32)
        e = _parametric_tone(x, look)
        if is_mono:
            e = np.repeat((e @ mono_w)[..., None], 3, -1)
        bands, sat_base, do_tints = look.bands, look.sat, True

    # ---- Grundlagen: Weiss-/Schwarzpunkt, Sättigung, Vibrance (nicht bei Monochrom) ----
    if s.whites or s.blacks:
        bp, wp = -0.06 * s.blacks / 100.0, 1.0 - 0.06 * s.whites / 100.0
        e = ((np.clip(e, 0, 1) - bp) / max(wp - bp, 0.2)).astype(F32)
    if (s.saturation or s.vibrance) and not is_mono:
        e = np.clip(e, 0, 1)
        yv = (e @ LUMA_S)[..., None]
        k = np.full(e.shape[:2] + (1,), 1.0 + s.saturation / 100.0, F32)
        if s.vibrance:
            mx, mn = e.max(-1, keepdims=True), e.min(-1, keepdims=True)
            k = k * (1.0 + (s.vibrance / 100.0) * (1.0 - (mx - mn) / np.maximum(mx, 1e-4)))
        e = (yv + (e - yv) * k).astype(F32)

    lift = DR_LIFT.get(s.dynamic_range)
    if lift is not None and not is_mono:
        e = np.clip(e, 0, 1)
        e = (e + np.interp(e, lift[0], lift[1]).astype(F32)).astype(F32)

    # ---- Grading (Tonwerte, Kontrast, Farbe) ----
    chrome = CHROME_AMOUNT[s.color_chrome]
    cblue = CHROME_AMOUNT[s.color_chrome_blue]
    sat_gain = sat_base * (1 + 0.10 * s.color)
    do_tone = bool(s.highlight_tone or s.shadow_tone)
    do_con = bool(s.contrast)
    ck, cg0, cg1 = sigmoid_params(1.2 * s.contrast / 100.0) if do_con else (0.0, 0.0, 1.0)
    do_color = (not is_mono) and (bands is not None or sat_gain != 1.0 or chrome > 0 or cblue > 0 or do_tints)
    P = np.array([0.035 * s.highlight_tone, 0.035 * s.shadow_tone, ck, cg0, cg1, sat_gain, chrome, cblue], np.float64)
    flags = np.array([do_tone, do_con, do_color, bands is not None, do_tints, is_mono], np.int64)
    tone = (np.array([1, 0, -1.0]) * (s.mono_wc / 18.0) + np.array([0.5, -1, 0.5]) * (s.mono_mg / 18.0))
    y = np.empty((h, w), F32)
    kernels.k_grade(e, y, P, (bands if bands is not None else _NEUTRAL_BANDS).astype(np.float64),
                    BAND_CENTERS.astype(np.float64), np.array(look.shadow_tint, np.float64),
                    np.array(look.highlight_tint, np.float64), tone, flags)

    # ---- Tonkurve + Color Grading (Display-Raum, nach dem Look) ----
    curves = [s.curve, s.curve_r, s.curve_g, s.curve_b]
    do_curve = not all(grading.curve_is_identity(c) for c in curves)
    do_cg = grading.has_grading(s)
    if do_curve or do_cg:
        if do_curve:
            e = grading.apply_curves(e, *curves)
        if do_cg:
            e = grading.color_grade(e, s)
        y = (np.clip(e, 0, 1) @ LUMA_S).astype(F32)

    # ---- eigene LUT (Zusatz) ----
    if custom_lut is not None and s.lut_strength > 0:
        from . import lut as lutmod
        ec = np.clip(e, 0, 1)
        e = ec + (lutmod.apply(custom_lut, ec) - ec) * F32(s.lut_strength)

    # ---- Clarity / Sharpness / NR / Grain ----
    dummy2 = np.zeros((1, 1), F32)
    dummy3 = np.zeros((1, 1, 3), F32)
    yc = dummy2
    if s.clarity:
        yc = effects.blur(y, 0.025 * long_px)
    sharp_amt = max(0.0, 0.4 + 0.25 * s.sharpness)
    sig_s = 0.0004 * long_px
    use_sharp = sharp_amt > 0 and sig_s >= 0.35
    ys = effects.blur(y, sig_s) if use_sharp else dummy2
    use_nr = s.noise_reduction > 0
    enr = effects.blur(np.clip(e, 0, 1), max(0.4, 0.0007 * long_px)) if use_nr else dummy3
    g_amt = GRAIN_AMOUNT[s.grain_effect]
    cell = GRAIN_SIZE[s.grain_size] * long_px
    if cell < 1.0:        # Korn kleiner als ein Ausgabepixel: wird beim Verkleinern gemittelt -> schwaecher
        g_amt *= cell
        cell = 1.0
    out = np.empty((h, w, 3), np.uint8)
    kernels.k_finish(e, y, yc, ys, enr, out, 0.036 * s.clarity, sharp_amt, min(1.0, 0.07 * s.noise_reduction),
                     g_amt, cell, 0.3, int(ctx.seed) & 0x7FFFFFFF, float(ctx.ox), float(ctx.oy),
                     bool(is_mono), bool(s.clarity), bool(use_sharp), bool(use_nr))
    return out
