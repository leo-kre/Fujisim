"""Minimaler .cube-3D-LUT-Loader mit trilinearer Interpolation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Lut:
    table: np.ndarray  # [b, g, r, 3]
    dmin: np.ndarray
    dmax: np.ndarray

    @property
    def size(self) -> int:
        return self.table.shape[0]


def load_cube(path: str) -> Lut:
    size = None
    dmin, dmax = np.zeros(3, np.float32), np.ones(3, np.float32)
    data: list[str] = []
    with open(path, "r", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            c = line[0]
            if c.isdigit() or c in "-+.":
                data.append(line)
                continue
            key = line.split()[0].upper()
            if key == "LUT_3D_SIZE":
                size = int(line.split()[1])
            elif key == "LUT_1D_SIZE":
                raise ValueError("1D-LUTs werden nicht unterstuetzt (nur 3D .cube)")
            elif key == "DOMAIN_MIN":
                dmin = np.array(line.split()[1:4], np.float32)
            elif key == "DOMAIN_MAX":
                dmax = np.array(line.split()[1:4], np.float32)
    if size is None:
        raise ValueError("Ungueltige .cube-Datei (LUT_3D_SIZE fehlt)")
    flat = np.array(" ".join(data).split(), np.float32)
    if flat.size != size ** 3 * 3:
        raise ValueError("Ungueltige .cube-Datei (falsche Anzahl Werte)")
    return Lut(flat.reshape(size, size, size, 3), dmin, dmax)


def apply(lut: Lut, rgb: np.ndarray) -> np.ndarray:
    n = lut.size
    flat = rgb.reshape(-1, 3)
    out = np.empty_like(flat)
    t = lut.table
    scale = (n - 1) / np.maximum(lut.dmax - lut.dmin, 1e-6)
    step = 1 << 20
    for s in range(0, len(flat), step):
        c = flat[s:s + step]
        p = np.clip((c - lut.dmin) * scale, 0, n - 1)
        i0 = np.minimum(p.astype(np.int32), n - 2)
        f = (p - i0).astype(np.float32)
        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
        fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]

        def at(dr, dg, db):
            return t[b0 + db, g0 + dg, r0 + dr]

        c00 = at(0, 0, 0) * (1 - fr) + at(1, 0, 0) * fr
        c10 = at(0, 1, 0) * (1 - fr) + at(1, 1, 0) * fr
        c01 = at(0, 0, 1) * (1 - fr) + at(1, 0, 1) * fr
        c11 = at(0, 1, 1) * (1 - fr) + at(1, 1, 1) * fr
        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg
        out[s:s + step] = c0 * (1 - fb) + c1 * fb
    return out.reshape(rgb.shape)
