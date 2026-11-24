# FujiSim

Sony-RAW (ARW, A7 III) → Fujifilm-Looks mit den **Einstellungen der Fuji-Kamera** (Rezepte 1:1 übertragbar).

## Start
```bash
cd ~/Downloads/fujisim && source .venv/bin/activate
python -m fujisim              # GUI (Dateien/Ordner per Drag & Drop)
```

## Wie die Looks entstehen
- **Offizielle Fuji-LUTs** (`luts/*.cube`, F-Log2C → Rec.709): Provia, Velvia, Astia, Classic Chrome,
  Pro Neg. Std, Classic Neg., Eterna, Eterna Bleach Bypass, Reala Ace, Acros.
  Pipeline: Sony-RAW (ProPhoto, linear) → F-Gamut C → F-Log2 (Formel & Primärfarben aus dem
  Fujifilm-Datenblatt, 18 % Grau = Code 400) → LUT.
- **Näherungen** (kein LUT vorhanden): Neutral, Pro Neg. Hi, Nostalgic Neg., Monochrome.
- Anderer LUT-Ordner: Toolbar „Fuji-LUT-Ordner…“ oder `FUJISIM_LUT_DIR`.
  Die LUTs gehören Fujifilm – nicht weitergeben.

## Kamera-Einstellungen
Film Simulation, Dynamic Range (DR100/200/400), Highlight/Shadow Tone (−2…+4, 0,5er-Schritte),
Color, Sharpness, Noise Reduction (−4…+4), Clarity (−5…+5), Grain Effect (Off/Weak/Strong + Small/Large),
Color Chrome Effect, Color Chrome FX Blue, White Balance (Auto/Daylight/Shade/Fluorescent/Incandescent/Kelvin)
mit WB Shift R/B (−9…+9), Acros-Filter, Monochromatic Color (WC/MG), Belichtungskorrektur.

**Rezept einfügen…** liest Text im Format von fujixweekly u. ä. („Highlight: +1“, „Grain Effect: Strong, Small“,
„White Balance: Auto, +2 Red & -5 Blue“ …). **Rezept kopieren** gibt die aktuellen Werte im selben Format aus.
Zusätze (nicht in der Kamera): Halation, Bloom, Vignette, Kontrast, Intensität, eigene LUT.

## Geometrie & Grundlagen
- **Zuschneiden** (Knopf oder Taste `R`): Rahmen an Ecken/Kanten ziehen, in der Mitte verschieben; Enter/Doppelklick = fertig.
  Seitenverhältnisse: Original, Frei, 1:1, 4:5, 3:2, 16:9 … (⇄ tauscht Hoch/Quer). Der Rahmen bleibt immer im Bild.
- **Gerade ausrichten** (Regler −45…+45°), **90° drehen**, **Spiegeln** horizontal/vertikal, „Zuschnitt & Drehung zurücksetzen“.
  Geometrie gilt pro Bild: sie wird weder von Presets noch von „Apply to all“ noch von „Zurücksetzen“ überschrieben.
- **Grundlagen**: Sättigung, Dynamik (Vibrance), Weiß, Schwarz.
- **Export-Dialog**: JPEG/PNG/TIFF, Qualität, Größe: Original, lange/kurze Kante, Breite, Höhe, Prozent oder „In Rahmen B × H“,
  optional „Nicht vergrößern“. Zuschnitt und Drehung werden mit exportiert.

## Graphen & Color Grading
- **Histogramm** (oben im Panel): RGB + Helligkeit des angezeigten Bildes; Dreiecke oben links/rechts warnen bei abgeschnittenen Tiefen/Lichtern.
- **Color Grading**: Farbräder für Schatten, Mitten, Lichter und Global (Farbton = Winkel, Sättigung = Abstand, Doppelklick = zurück)
  mit je einem Luminanz-Regler; **Überblendung** und **Balance** steuern Breite und Lage der Zonen.
- **Tonkurve**: Punktkurve für RGB sowie Rot/Grün/Blau einzeln. Klick = Punkt setzen, ziehen = verschieben, Rechtsklick/Doppelklick = löschen.
  Das Luma-Histogramm liegt hinter der Kurve.
- Räder und Kurven gehören zum Look: sie werden in Presets gespeichert (Zuschnitt/Drehung nicht).

## Presets
Im Panel oben: Preset wählen (wendet es auf das aktuelle Bild an, Belichtung bleibt), **Speichern als…**
(fragt bei vorhandenem Namen nach, ob überschrieben wird), **Überschreiben** (ersetzt das gewählte Preset
durch die aktuellen Werte), **Löschen**. Presets liegen als JSON in `presets/` (`FUJISIM_PRESET_DIR` ändert den Ort).
Beim ersten Start werden 12 Rezepte von fujixweekly.com angelegt (Quelle/Hinweise stehen als Tooltip):
Fujicolor 100 Industrial, Kodak Gold Max 400 (Expired), Pushed Analog, Appalachian Negative, Kodak Vision3 250D v2,
1971 Kodak, Nostalgic Americana, California Summer, Reala Ace (X-T5), Kodak Pro 400, Provia Positive, CineStill 800T.
Gelöschte Start-Presets kommen nicht zurück; `python -m fujisim.presets --reset` legt sie neu an.
CLI: `--preset "Kodak Pro 400"`.

**Apply to all** überträgt alle Einstellungen auf alle geladenen Bilder
(Checkbox: Belichtung & Weißabgleich pro Bild behalten).

## Batch
```bash
python -m fujisim.cli ordner/ -o out/ --recipe rezept.txt
python -m fujisim.cli foto.ARW --sim "Classic Chrome" --preset preset.json
```

## Kalibrierung gegen echte Fuji-Dateien (Details: `calibration/RESULTS.md`)
- **Kamera-Belichtung (fest):** Die Fuji-Engine skaliert RAW → Szene mit einer Konstanten statt pro Bild (gemessen
  an 13 X-T2-RAFs: +1,12 EV, Streuung 0,04). Dieselbe Logik gilt für Sony (+1,04 EV). Die App nutzt jetzt diese feste
  Skalierung inkl. ISO-Regel (erweiterter ISO = eine Blende weniger) statt einer Bild-Auto-Belichtung.
  Helle Szenen bleiben hell, dunkle dunkel – wie bei der Kamera. Abweichung zum Sony-JPEG: 25,9 → 8,2 (von 255).
- **Classic Chrome:** Die offiziellen Video-LUTs weichen vom Foto-Rendering ab. Eine aus 10 Bildern gelernte Korrektur
  senkt den Farbfehler auf unbekannten Bildern von dE 7,2 auf 5,6.
- **Effekte gemessen** an fujixweekly-Vergleichsbildern (gleiche Szene Off/Weak/Strong): Grain, Color Chrome Effect,
  FX Blue. Meine ersten Schätzwerte waren 3–4× zu stark (Grain) bzw. 2× (Color Chrome); jetzt stimmen sie mit den
  Messungen überein (`calibration/RESULTS.md`).
- **Noch nicht kalibriert** (keine Referenzbilder): Clarity, Highlight/Shadow Tone, DR200/400, Color, WB-Shift,
  Sharpness/NR und alle Looks außer Classic Chrome/Provia. Diese sind bewusst mild eingestellt.

## Was exakt ist und was Näherung
- **Exakt:** Look-Kurven/Farben der Simulationen (offizielle LUTs), F-Log2/F-Gamut-C-Mathematik.
- **Näherung:** Die Wirkung der Zahlenwerte (Highlight/Shadow Tone, Color, Clarity, Sharpness, NR, Grain,
  Color Chrome, DR200/400, WB-Presets in Kelvin, WB Shift) – Fuji veröffentlicht diese Kurven nicht.
  Skalen und Namen sind identisch, die Stärke ist nach Augenmaß abgestimmt (siehe `pipeline.py`).
- Sony-Sensor ≠ Fuji-Sensor, Belichtung wird per Auto-Belichtung geschätzt: Feintuning per Belichtungskorrektur.

## Performance / Speicher (Kernsystem)
- **Genau ein Bild im Speicher** (`ImageSession`): beim Wechsel wird das vorige freigegeben. Der Filmstreifen
  nutzt nur die eingebetteten JPEG-Vorschauen der RAWs.
- **Ausschnitts-Rendering:** gerendert wird nur der sichtbare Bereich in Bildschirmauflösung. Je nach Zoom wird
  die passende Pyramidenstufe (1/1, 1/2, 1/4 …) gelesen: Fit = schnell, 100 % und mehr = echte Pixel.
  Mausrad = Zoom, Ziehen = Verschieben, Doppelklick oder `1` = 100 %, `0` = Fit.
- Beim Laden ist das Bild sofort (halbe Auflösung) bearbeitbar, die volle Auflösung lädt im Hintergrund nach.
- Während des Ziehens an Reglern/Zoom wird in reduzierter Qualität gerendert, danach in voller.
- Pixelarbeit läuft in parallelen numba-Kernen; Export arbeitet kachelweise (geringer Speicherbedarf).
