"""Kommandozeile: python -m fujisim.cli bild.ARW --sim "Classic Chrome" --grain 0.4"""
from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path

from .film import FILMS
from .raw_io import RAW_EXT
from .engine import export_file as export_image
from .settings import EditSettings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sony-RAW -> Fujifilm-Look")
    ap.add_argument("inputs", nargs="+", help="RAW-Dateien oder Ordner")
    ap.add_argument("-o", "--out", default=".", help="Ausgabeordner")
    ap.add_argument("--preset", help="Preset-Name (z. B. \"Kodak Pro 400\") oder JSON-Datei")
    ap.add_argument("--format", default="jpg", choices=["jpg", "png"])
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--max-edge", type=int, default=0, help="Lange Kante begrenzen (0 = voll)")
    for f in fields(EditSettings):
        if f.type in ("float", float):
            ap.add_argument(f"--{f.name.replace('_', '-')}", type=float)
        elif f.type in ("str", str):
            ap.add_argument(f"--{f.name.replace('_', '-')}")
    ap.add_argument("--no-auto-exposure", action="store_true")
    ap.add_argument("--recipe", help="Fuji-Rezept als Textdatei (Film Simulation: ..., Highlight: +1, ...)")
    a = ap.parse_args(argv)

    from . import presets
    presets.install_defaults()
    s = presets.load_settings(a.preset) if a.preset else EditSettings()
    if a.recipe:
        from .recipe import apply_recipe
        s, _, unknown = apply_recipe(s, Path(a.recipe).read_text())
        for u in unknown:
            print(f"Rezept: Zeile nicht erkannt: {u!r}", file=sys.stderr)
    for f in fields(EditSettings):
        v = getattr(a, f.name, None)
        if v is not None:
            setattr(s, f.name, v)
    if a.no_auto_exposure:
        s.auto_exposure = False
    if s.sim not in FILMS:
        sys.exit(f"Unbekannte Simulation '{s.sim}'. Verfuegbar: {', '.join(FILMS)}")

    files = []
    for p in map(Path, a.inputs):
        files += sorted(q for q in p.iterdir() if q.suffix.lower() in RAW_EXT) if p.is_dir() else [p]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files, 1):
        dst = out / f"{f.stem}_{s.sim.replace(' ', '').replace('.', '')}.{a.format}"
        print(f"[{i}/{len(files)}] {f.name} -> {dst.name}", flush=True)
        export_image(str(f), s, str(dst), a.quality, a.max_edge)


if __name__ == "__main__":
    main()
