# Kalibrierung gegen echte Fuji-Kamera-Ausgabe

**Daten:** 13 Fuji-X-T2-RAFs von [Photography Blog](https://www.photographyblog.com/previews/fujifilm_x_t2_photos)
(RAF + im RAF eingebettetes Kamera-JPEG; die separat angebotenen JPEGs gehoeren zu anderen Motiven).
Einstellungen aus den Fuji-MakerNotes: 10x Classic Chrome, 2x Velvia, 1x Provia, alle DR100, Tones/Color/Grain neutral/aus.
Referenzguete: eingebettetes JPEG vs. volles Kamera-JPEG (RAF 01 / JPEG 10): dE 1.06.
Metrik: CIE-dE auf geglaetteten Bildern (sigma 4 px), da Kanten durch Objektivkorrektur/Schaerfung abweichen.

| Befund | Messung |
|---|---|
| Kamera skaliert **fest**, nicht pro Bild | RAW->Szene +1.12 EV (Streuung 0.04 ueber 8 Bilder); ISO 100 (erweitert) genau -1 Blende |
| Sony A7 III gleiche Logik | +1.04 EV (Streuung 0.15, 24 ARW vs. Sony-JPEG), ISO-unabhaengig |
| Alte Auto-Belichtung | wich vom Sony-JPEG im Median-Y um 25.9 ab, mit fester Skalierung 8.2 (Skala 0-255) |
| Offizielle F-Log2C-LUTs sind Video-Looks | Provia dE 3.7 (gut), Classic Chrome 7.2, Velvia 7.6: Foto-Rendering der Kamera weicht ab (Schatten heller, Rot/Orange weniger gesaettigt bei CC) |
| Gelernte 3D-Korrektur Classic Chrome | Leave-one-out ueber 10 Bilder: dE 7.22 -> 5.6 (alle 10 Bilder besser) -> **eingebaut** |
| Velvia-Korrektur | nur 2 Bilder, 2-fold gemischt (6.55->6.64, 8.62->8.11) -> **nicht eingebaut** |
| Allgemeine Korrektur auf andere Looks uebertragen | kein Nutzen (7.22->7.06) -> **nicht eingebaut** |

**Nicht kalibriert (keine Referenzdaten):** Grain, Color Chrome (Effect/FX Blue), Clarity, Highlight/Shadow Tone,
DR200/400, WB-Shift, Astia, Pro Neg., Classic Neg., Nostalgic Neg., Eterna, Reala Ace, Acros.
Dafuer braucht es RAF + Kamera-JPEG mit genau diesen Einstellungen (X-T3 oder neuer fuer Color Chrome/Clarity).

Skripte: `fuji_exif.py` (MakerNote-Parser), `build_cache2.py`, `embedded.py`, `compare.py`, `fit_corr.py`, `sweep.py`,
`train_final.py`, `sony_k.py`, `e2e.py`. Rohdaten (772 MB) liegen in `refs/xt2/` und koennen geloescht werden.


## Effekte (Messung an fujixweekly-Vergleichsbildern, Nov 2026)
Quellen: [Grain-Vergleich X-T5](https://fujixweekly.com/2025/01/03/fujifilm-grain-comparison-gfx100s-ii-vs-x-t5/) (100 %-Ausschnitte),
[Grain-Einstellungen X-T30](https://fujixweekly.com/2019/12/06/fujifilm-grain-settings/) (Off/Weak/Strong, gleiche Szene),
[Color Chrome Effect X-T30](https://fujixweekly.com/2019/04/03/fujifilm-x-t30-new-feature-color-chrome-effect/) und
[FX Blue X100V](https://fujixweekly.com/2020/06/30/fujifilm-x100v-new-feature-color-chrome-effect-blue/) (Off/Weak/Strong, gleiche Szene, pixelgenau ausgerichtet).
Rohdaten in `refs/grain/`, `refs/cce/`; Skripte `grain_measure*.py`, `cce_measure.py`.

| Effekt | Messung | vorher (geschaetzt) | jetzt |
|---|---|---|---|
| Grain Weak | Korn-Std ca. 1.3-2.6 Stufen (8 bit, native Aufloesung) | 10 | 2.0 |
| Grain Strong | ca. 3.9-7.2 (X-T5 Strong/Large 5.3) | 22 | 5.2-5.6 |
| Grain-Farbanteil | Chroma-Std < 1 Stufe (fast reine Helligkeit) | 28 % Farbrauschen | 12 % |
| Korngroesse | Autokorrelation 1 px: Small ~0.16, Large ~0.45 | 4-7 px Zellen | ~1 px / ~1.5 px |
| Color Chrome Strong | Helligkeit gesaettigter Farben -4 % (S 0.45) bis -11 % (S 0.85); Weak ~halb | -10 % bis -24 % | -4 % bis -11 % |
| FX Blue Strong | nur Blau: -16..-19 % Helligkeit, +24..+29 % Saettigung; Weak ~halb | -40 % (breiter) | -17 % / +25 % |

**Nicht gemessen (Schaetzung, bewusst mild):** Clarity (0.06 pro Stufe), DR200/DR400 (Knie ab 1.5 Blenden ueber Mittelgrau,
Steilheit 0.75/0.55), Highlight/Shadow Tone (0.035 pro Stufe), Color (10 % Saettigung pro Stufe), WB-Shift, Sharpness, NR.
Color Chrome Effect: nur warme Farbtoene (Rot/Orange) gemessen, Verhalten bei Gruen/Blau angenommen.
