"""Schnelle, parallele Pixel-Kernel (numba). Alles float32, Zeilen parallel."""
from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

LR, LG, LB = 0.2126, 0.7152, 0.0722  # sRGB-Luma


# ------------------------------------------------------------------ LUT
@njit(cache=True, fastmath=True, inline="always")
def _flog2(x):
    if x < 0.0:
        x = 0.0
    if x >= 0.000889:
        y = 0.245281 * math.log10(5.555556 * x + 0.064829) + 0.384316
    else:
        y = 8.799461 * x + 0.092864
    if y < 0.0:
        y = 0.0
    elif y > 1.0:
        y = 1.0
    return y


@njit(cache=True, fastmath=True, inline="always")
def _knee(v, t, r):
    if r < 1.0 and v > t:
        return t + (v - t) * r
    return v


@njit(parallel=True, cache=True, fastmath=True)
def k_lut_look(x, table, dmin, dscale, knee_t, knee_r, out):
    """x: linear F-Gamut C -> DR-Knie -> F-Log2 -> trilineare 3D-LUT -> out (Rec.709-kodiert)."""
    H, W, _ = x.shape
    n = table.shape[0]
    nm1 = float(n - 1)
    for i in prange(H):
        for j in range(W):
            er = _flog2(_knee(x[i, j, 0], knee_t, knee_r))
            eg = _flog2(_knee(x[i, j, 1], knee_t, knee_r))
            eb = _flog2(_knee(x[i, j, 2], knee_t, knee_r))
            pr = min(max((er - dmin[0]) * dscale[0], 0.0), nm1)
            pg = min(max((eg - dmin[1]) * dscale[1], 0.0), nm1)
            pb = min(max((eb - dmin[2]) * dscale[2], 0.0), nm1)
            ir = min(int(pr), n - 2)
            ig = min(int(pg), n - 2)
            ib = min(int(pb), n - 2)
            fr = pr - ir
            fg = pg - ig
            fb = pb - ib
            for c in range(3):
                c000 = table[ib, ig, ir, c]
                c100 = table[ib, ig, ir + 1, c]
                c010 = table[ib, ig + 1, ir, c]
                c110 = table[ib, ig + 1, ir + 1, c]
                c001 = table[ib + 1, ig, ir, c]
                c101 = table[ib + 1, ig, ir + 1, c]
                c011 = table[ib + 1, ig + 1, ir, c]
                c111 = table[ib + 1, ig + 1, ir + 1, c]
                c00 = c000 + (c100 - c000) * fr
                c10 = c010 + (c110 - c010) * fr
                c01 = c001 + (c101 - c001) * fr
                c11 = c011 + (c111 - c011) * fr
                c0 = c00 + (c10 - c00) * fg
                c1 = c01 + (c11 - c01) * fg
                out[i, j, c] = c0 + (c1 - c0) * fb


# ------------------------------------------------------------------ Grading
@njit(cache=True, fastmath=True, inline="always")
def _clip01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


@njit(parallel=True, cache=True, fastmath=True)
def k_grade(e, y_out, P, bands, centers, tint_s, tint_h, mono_tone, flags):
    """Tonwerte, Kontrast, Farbe (Baender/Sat/Color Chrome), Split-Toning. In-place auf e.

    P: [0]a_h [1]a_s [2]con_k [3]con_g0 [4]con_g1 [5]sat_gain [6]chrome [7]chrome_blue
    flags: [0]do_tone [1]do_contrast [2]do_color [3]has_bands [4]do_tints [5]is_mono
    """
    H, W, _ = e.shape
    a_h, a_s = P[0], P[1]
    k, g0, g1 = P[2], P[3], P[4]
    sat_gain, chrome, cblue = P[5], P[6], P[7]
    for i in prange(H):
        for j in range(W):
            r = _clip01(e[i, j, 0])
            g = _clip01(e[i, j, 1])
            b = _clip01(e[i, j, 2])
            if flags[0]:
                bh = 14.93 * r * r * r * r * r * (1 - r)
                bs = 14.93 * r * (1 - r) * (1 - r) * (1 - r) * (1 - r) * (1 - r)
                r = _clip01(r - a_h * bh - a_s * bs)
                bh = 14.93 * g * g * g * g * g * (1 - g)
                bs = 14.93 * g * (1 - g) * (1 - g) * (1 - g) * (1 - g) * (1 - g)
                g = _clip01(g - a_h * bh - a_s * bs)
                bh = 14.93 * b * b * b * b * b * (1 - b)
                bs = 14.93 * b * (1 - b) * (1 - b) * (1 - b) * (1 - b) * (1 - b)
                b = _clip01(b - a_h * bh - a_s * bs)
            if flags[1]:
                r = (1.0 / (1.0 + math.exp(-k * (r - 0.45))) - g0) / (g1 - g0)
                g = (1.0 / (1.0 + math.exp(-k * (g - 0.45))) - g0) / (g1 - g0)
                b = (1.0 / (1.0 + math.exp(-k * (b - 0.45))) - g0) / (g1 - g0)
            if flags[5]:
                y = r
                w4 = 0.06 * 4.0 * y * (1.0 - y)
                r = _clip01(y + mono_tone[0] * w4)
                g = _clip01(y + mono_tone[1] * w4)
                b = _clip01(y + mono_tone[2] * w4)
            elif flags[2]:
                mx = max(r, max(g, b))
                mn = min(r, min(g, b))
                d = mx - mn
                if d <= 0.0:
                    h = 0.0
                    s = 0.0
                else:
                    if mx == r:
                        h = (g - b) / d
                        if h < 0.0:
                            h += 6.0
                    elif mx == g:
                        h = (b - r) / d + 2.0
                    else:
                        h = (r - g) / d + 4.0
                    h *= 60.0
                    s = d / mx
                v = mx
                if flags[3]:
                    kk = 7
                    for q in range(7):
                        if h < centers[q + 1]:
                            kk = q
                            break
                    c0 = centers[kk]
                    if kk < 7:
                        c1 = centers[kk + 1]
                        k1 = kk + 1
                    else:
                        c1 = 360.0 + centers[0]
                        k1 = 0
                    t = (h - c0) / (c1 - c0)
                    dh = bands[0, kk] * (1 - t) + bands[0, k1] * t
                    ds = bands[1, kk] * (1 - t) + bands[1, k1] * t
                    dl = bands[2, kk] * (1 - t) + bands[2, k1] * t
                    wgt = min(s * 4.0, 1.0)
                    h = h + dh * wgt
                    if h >= 360.0:
                        h -= 360.0
                    elif h < 0.0:
                        h += 360.0
                    s = s * (1.0 + ds * wgt)
                    s_for_l = min(max(s, 0.0), 1.0)
                    v = v * (1.0 + dl * s_for_l)
                s = _clip01(s * sat_gain)
                if chrome > 0.0:
                    # Color Chrome Effect (gemessen: Strong dunkelt gesaettigte Farben um 4-11 %, Weak ~ halb so viel)
                    # Blautoene reduziert (dafuer gibt es FX Blue)
                    dist_b = abs(((h - 230.0 + 180.0) % 360.0) - 180.0)
                    wc = 1.0 - 0.6 * max(0.0, 1.0 - dist_b / 60.0)
                    v = v * (1.0 - chrome * 0.13 * (s ** 1.3) * wc)
                if cblue > 0.0:
                    # Color Chrome FX Blue (gemessen: Strong -16..-19 % Helligkeit, +24..+29 % Saettigung, nur Blau)
                    dist = abs(((h - 230.0 + 180.0) % 360.0) - 180.0)
                    wb = 1.0 - dist / 45.0
                    if wb < 0.0:
                        wb = 0.0
                    v = v * (1.0 - cblue * 0.29 * (s ** 0.9) * wb)
                    s = min(1.0, s * (1.0 + cblue * 0.45 * s * wb))
                v = _clip01(v)
                hh = h / 60.0
                vs = v * s
                # R
                kq = (5.0 + hh) % 6.0
                r = v - vs * _clip01(min(kq, 4.0 - kq))
                kq = (3.0 + hh) % 6.0
                g = v - vs * _clip01(min(kq, 4.0 - kq))
                kq = (1.0 + hh) % 6.0
                b = v - vs * _clip01(min(kq, 4.0 - kq))
                if flags[4]:
                    yy = LR * r + LG * g + LB * b
                    ws = (1.0 - yy) * (1.0 - yy)
                    wh = yy * yy
                    r += ws * tint_s[0] + wh * tint_h[0]
                    g += ws * tint_s[1] + wh * tint_h[1]
                    b += ws * tint_s[2] + wh * tint_h[2]
            e[i, j, 0] = r
            e[i, j, 1] = g
            e[i, j, 2] = b
            y_out[i, j] = LR * _clip01(r) + LG * _clip01(g) + LB * _clip01(b)


# ------------------------------------------------------------------ Grain (positionsbasiert, kachelunabhaengig)
_M32 = np.uint64(0xFFFFFFFF)


@njit(cache=True, inline="always")
def _h32(x):
    """32-Bit-Integer-Hash (explizit auf 32 Bit maskiert, numba rechnet sonst in 64 Bit)."""
    x = np.uint64(x) & _M32
    x ^= x >> np.uint64(16)
    x = (x * np.uint64(0x7FEB352D)) & _M32
    x ^= x >> np.uint64(15)
    x = (x * np.uint64(0x846CA68B)) & _M32
    x ^= x >> np.uint64(16)
    return x


@njit(cache=True, inline="always")
def _lat(ix, iy, seed, stream):
    k = (ix * 73856093 + iy * 19349663 + seed * 83492791 + stream * 2654435761) & 0xFFFFFFFF
    h0 = _h32(np.uint64(k))
    u = 0.0
    for q in range(4):
        u += float(_h32(h0 + np.uint64(q + 1))) * (1.0 / 4294967296.0)
    return (u - 2.0) * 1.7320508


@njit(cache=True, inline="always")
def _vnoise(x, y, cell, seed, stream):
    if cell <= 1.0:        # feiner als ein Pixel: weisses Pixelrauschen (keine Interpolation)
        return _lat(int(math.floor(x)), int(math.floor(y)), seed, stream)
    u = x / cell
    v = y / cell
    iu = int(math.floor(u))
    iv = int(math.floor(v))
    fu = u - iu
    fv = v - iv
    a = _lat(iu, iv, seed, stream)
    b = _lat(iu + 1, iv, seed, stream)
    c = _lat(iu, iv + 1, seed, stream)
    d = _lat(iu + 1, iv + 1, seed, stream)
    top = a + (b - a) * fu
    bot = c + (d - c) * fu
    return (top + (bot - top) * fv) * 1.5  # bilineare Interpolation daempft die Varianz


@njit(parallel=True, cache=True, fastmath=True)
def k_finish(e, y, yc, ys, enr, out, clar_gain, sharp_amt, nr_amt, g_amount, g_cell, g_rough,
             seed, ox, oy, mono, use_clar, use_sharp, use_nr):
    """NR, Clarity, Sharpening, Grain, Quantisierung -> uint8."""
    H, W, _ = e.shape
    ra = 1.0 - 0.5 * g_rough
    rb = 0.5 * g_rough
    rn = 1.0 / math.sqrt(ra * ra + rb * rb)
    for i in prange(H):
        for j in range(W):
            r = e[i, j, 0]
            g = e[i, j, 1]
            b = e[i, j, 2]
            if use_nr:
                r += (enr[i, j, 0] - r) * nr_amt
                g += (enr[i, j, 1] - g) * nr_amt
                b += (enr[i, j, 2] - b) * nr_amt
            yy = y[i, j]
            add = 0.0
            if use_clar:
                add += clar_gain * (yy - yc[i, j])
            if use_sharp:
                add += sharp_amt * (yy - ys[i, j])
            r += add
            g += add
            b += add
            if g_amount > 0.0:
                X = ox + j + 0.5
                Y = oy + i + 0.5
                ln = (ra * _vnoise(X, Y, g_cell, seed, 0) + rb * _vnoise(X, Y, g_cell * 0.5, seed, 1)) * rn
                yl = _clip01(0.2126 * _clip01(r) + 0.7152 * _clip01(g) + 0.0722 * _clip01(b))
                w = 4.0 * yl * (1.0 - yl)
                w = 0.85 + 0.15 * (w ** 0.7)
                st = g_amount * 0.13 * w
                if mono:
                    r += st * ln
                    g += st * ln
                    b += st * ln
                else:
                    r += st * (ln + 0.12 * _vnoise(X, Y, g_cell, seed, 2))
                    g += st * (ln + 0.12 * _vnoise(X, Y, g_cell, seed, 3))
                    b += st * (ln + 0.12 * _vnoise(X, Y, g_cell, seed, 4))
            out[i, j, 0] = np.uint8(_clip01(r) * 255.0 + 0.5)
            out[i, j, 1] = np.uint8(_clip01(g) * 255.0 + 0.5)
            out[i, j, 2] = np.uint8(_clip01(b) * 255.0 + 0.5)


# ------------------------------------------------------------------ Gelernte Korrektur (3D, additiv)
@njit(parallel=True, cache=True, fastmath=True)
def k_corr(e, grid, strength):
    """e += strength * trilinear(grid[r,g,b]) -- Korrektur zwischen LUT-Ergebnis und Kamera-JPEG."""
    H, W, _ = e.shape
    n = grid.shape[0]
    nm1 = float(n - 1)
    for i in prange(H):
        for j in range(W):
            pr = min(max(e[i, j, 0], 0.0), 1.0) * nm1
            pg = min(max(e[i, j, 1], 0.0), 1.0) * nm1
            pb = min(max(e[i, j, 2], 0.0), 1.0) * nm1
            ir = min(int(pr), n - 2)
            ig = min(int(pg), n - 2)
            ib = min(int(pb), n - 2)
            fr = pr - ir
            fg = pg - ig
            fb = pb - ib
            for c in range(3):
                c000 = grid[ir, ig, ib, c]
                c100 = grid[ir + 1, ig, ib, c]
                c010 = grid[ir, ig + 1, ib, c]
                c110 = grid[ir + 1, ig + 1, ib, c]
                c001 = grid[ir, ig, ib + 1, c]
                c101 = grid[ir + 1, ig, ib + 1, c]
                c011 = grid[ir, ig + 1, ib + 1, c]
                c111 = grid[ir + 1, ig + 1, ib + 1, c]
                c00 = c000 + (c100 - c000) * fr
                c10 = c010 + (c110 - c010) * fr
                c01 = c001 + (c101 - c001) * fr
                c11 = c011 + (c111 - c011) * fr
                c0 = c00 + (c10 - c00) * fg
                c1 = c01 + (c11 - c01) * fg
                e[i, j, c] += strength * (c0 + (c1 - c0) * fb)
