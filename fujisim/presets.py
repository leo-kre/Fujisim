"""Preset-Verwaltung: speichern, ueberschreiben, loeschen. Jedes Preset ist eine JSON-Datei."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from .settings import GEOMETRY_KEYS, EditSettings

# Pro Bild individuell -> gehoert nicht in ein Preset
EXCLUDE = ("auto_exposure", "exposure") + GEOMETRY_KEYS
_MARKER = ".defaults_installed"


def preset_dir() -> Path:
    env = os.environ.get("FUJISIM_PRESET_DIR")
    d = Path(env) if env else Path(__file__).resolve().parent.parent / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", name.strip(), flags=re.UNICODE).strip(" .")
    return s or "preset"


def _path(name: str) -> Path:
    return preset_dir() / f"{_slug(name)}.json"


def list_presets() -> list[str]:
    out = []
    for f in preset_dir().glob("*.json"):
        try:
            out.append(json.loads(f.read_text())["name"])
        except Exception:  # noqa: BLE001
            continue
    return sorted(out, key=str.lower)


def exists(name: str) -> bool:
    return any(n.lower() == name.strip().lower() for n in list_presets())


def _find(name: str) -> Path | None:
    for f in preset_dir().glob("*.json"):
        try:
            if json.loads(f.read_text())["name"].lower() == name.strip().lower():
                return f
        except Exception:  # noqa: BLE001
            continue
    return None


def save(name: str, s: EditSettings, source: str = "", note: str = "", overwrite: bool = False) -> Path:
    """Speichert ein Preset. Existiert der Name schon, wird nur mit overwrite=True ersetzt."""
    name = name.strip()
    if not name:
        raise ValueError("Preset braucht einen Namen")
    old = _find(name)
    if old is not None and not overwrite:
        raise FileExistsError(name)
    data = {k: v for k, v in asdict(s).items() if k not in EXCLUDE}
    meta_old = {}
    if old is not None:
        try:
            meta_old = json.loads(old.read_text())
        except Exception:  # noqa: BLE001
            pass
    path = old or _path(name)
    path.write_text(json.dumps({
        "name": name if old is None else meta_old.get("name", name),
        "source": source or meta_old.get("source", ""),
        "note": note or meta_old.get("note", ""),
        "settings": data,
    }, indent=2, ensure_ascii=False))
    return path


def load(name: str) -> dict:
    f = _find(name)
    if f is None:
        raise KeyError(name)
    return json.loads(f.read_text())


def delete(name: str) -> bool:
    f = _find(name)
    if f is None:
        return False
    f.unlink()
    return True


def apply_preset(current: EditSettings, preset: dict) -> EditSettings:
    """Preset auf Einstellungen anwenden; Belichtung (pro Bild) bleibt erhalten."""
    new = EditSettings.from_dict({**asdict(EditSettings()), **preset["settings"]})
    for k in EXCLUDE:
        setattr(new, k, getattr(current, k))
    return new


def load_settings(name_or_path: str, base: EditSettings | None = None) -> EditSettings:
    """Fuer die CLI: Preset-Name oder JSON-Datei (auch altes Format ohne 'settings')."""
    base = base or EditSettings()
    p = Path(name_or_path)
    if p.suffix.lower() == ".json" and p.exists():
        d = json.loads(p.read_text())
        return EditSettings.from_dict(d["settings"] if "settings" in d else d)
    return apply_preset(base, load(name_or_path))


def install_defaults(force: bool = False) -> int:
    """Legt die mitgelieferten Rezepte einmalig an (spaeter geloeschte kommen nicht zurueck)."""
    d = preset_dir()
    marker = d / _MARKER
    if marker.exists() and not force:
        return 0
    from .default_presets import DEFAULTS
    from .recipe import apply_recipe
    n = 0
    for name, text, source, note in DEFAULTS:
        if exists(name) and not force:
            continue
        s, _, _ = apply_recipe(EditSettings(), text)
        save(name, s, source=source, note=note, overwrite=True)
        n += 1
    marker.write_text("1")
    return n


if __name__ == "__main__":
    import sys
    print(f"{install_defaults(force='--reset' in sys.argv)} Start-Presets angelegt in {preset_dir()}")
