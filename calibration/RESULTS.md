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


## Nachmessung aus Web-Vergleichsbildern (Nov 2026, Rohdaten in `refs/web/`, nicht einchecken)
Quellen: [20-Sims-Vergleich, gleiche Aufnahme](https://fujixweekly.com/2025/09/08/film-simulation-comparison/) (Kacheln ausgeschnitten, Beschriftung ausgespart),
DR-P-Reprocess-Serie X-E4/GFX ([Artikel](https://fujixweekly.com/2025/01/17/the-curious-case-of-d-range-priority-auto/)),
Clarity-Serie ([Artikel](https://fujixweekly.com/2026/04/05/what-does-clarity-actually-do/)), WB-Shift-Paar ([Artikel](https://fujixweekly.com/2020/08/19/fujifilm-white-balance-shift-what-it-is-how-to-use-it)),
Capture-One-Exporte einer X-Pro2-RAF ([pixls](https://discuss.pixls.us/t/replicating-fujifilm-jpg-colors-from-raw-files/34458); **keine** Kamera-JPEGs, nur Zweitreferenz).

| Befund | Messung | Aenderung |
|---|---|---|
| Methode 20-Sims-Bild | Szene = Provia-Kachel, ueber Provia-Modell invertiert; dann jede andere Sim vorwaerts gerechnet und mit ihrer Kachel verglichen. Methodenboden dE 3.0-3.6 | – |
| LUT-Sims auf diesem Bild | Velvia 5.6, Astia 3.8, Classic Chrome 4.7, Reala Ace 4.0, Pro Neg. Std 4.0, Classic Neg. 4.3, Eterna 5.0, Eterna BB 4.0 | unveraendert (nur ca. 1 dE ueber Boden; eine Szene reicht nicht fuer Korrekturen, siehe Hinweis) |
| **Pro Neg. Hi** (alte Naeherung) | dE 8.3, zu hell (dL +4.8) | jetzt Pro-Neg.-Std-LUT + gelerntes Gitter: 2-fold-Test **8.3 -> 3.6** |
| **Nostalgic Neg.** (alte Naeherung) | dE 9.1, zu hell (dL +6.3), zu wenig Rot/Gelb | jetzt Reala-Ace-LUT + gelerntes Gitter: 2-fold-Test **9.1 -> 3.8** (Reala Ace roh 6.5) |
| **Clarity** | lokale Kontrastenergie (Std von y - Gauss(y), sigma 2-40 px) relativ zu 0: +5 = 1.16-1.19, +2 = 1.05, -2 = 0.95, -5 = 0.82-0.85; fast unabhaengig vom Radius | Staerke 0.06 -> 0.036 pro Stufe (war 1.7x zu stark), Radius 0.012 -> 0.025 der langen Kante; Test an Clarity-0-Bild: +5 1.17 / -5 0.82 |
| **Highlight/Shadow** | Schritt H-1->-2 / S-1->-2 (X-E4, gleiche Szene): Schatten +9 bei Y 42-71, Lichter -9 bei Y 212 (von 255); Betrag 0.035/Stufe stimmte, Kurvenform lag zu mittig | Kurvenform von 6.75 r(1-r)^2 auf 14.93 r(1-r)^5 (Schatten Spitze bei 17 %, Lichter bei 83 %), Betrag unveraendert |
| WB-Shift +1R/-1B (ein Paar) | R/G x1.045-1.067, B/G x0.89-0.92 im JPEG (Tonkurve verstaerkt) -> roh etwa R +3.5-5 %, B -6.5-8 % pro Stufe | **nicht geaendert** (ein Paar, Achsen nicht trennbar; Vermutung B staerker als R) |

**Grenzen:** Die zwei gelernten Gitter (`data/corr_pro_neg_hi.npy`, `corr_nostalgic_neg.npy`) stammen aus **einer** Szene (Kino-Schild); Farben, die dort nicht vorkommen, fallen
durch die Glaettung auf die Basis-LUT zurueck. Der 2-fold-Test trennt nur obere/untere Bildhaelfte derselben Szene. Weitere Szenen mit Nostalgic Neg./Pro Neg. Hi bleiben noetig.
Ebenfalls einzeln gemessen, aber **nicht eingebaut** (Gewinn nur ca. 0.9-1.4 dE, eine Szene): Korrekturen fuer Pro Neg. Std, Classic Neg., Eterna, Eterna BB, Velvia.
**Nicht ableitbar:** DR100 gegen DR200/DR400 (die X-E4/GFX-Serie enthaelt keine DR100-Basis, Dateizuordnung teils unsicher), Color +/-, Reala-Ace/Classic-Neg.-Foto-Rendering gegen die Kamera (kein RAW), Sensorunterschied Sony/X-Trans.
Methodenskripte lagen im Scratchpad (nicht archiviert); die Kachel-Koordinaten: 5x4, x = 26/843/1660/2478/3296, y = 47/608/1168/1729, 775x517 px.


## Rezept-Test auf einer Aufnahme (7 fujixweekly-Rezepte, GFX100S II, in der Kamera neu entwickelt)
Quelle: [Nostalgic-Negative-Vergleich](https://fujixweekly.com/2025/09/11/nostalgic-negative-makes-your-photos-feel-like-memories/) (Bilder in `refs/web/nostalgic/`), Rezept-Einstellungen aus den jeweiligen Artikeln
(Nostalgic Americana, Nostalgia Negative, Kodak Vericolor Warm/VPS, Agfa Ultra 100 v2, Kodak Negative, 1970's Summer – alle Nostalgic Neg. als Basis).
Methode: Szene = Bild mit Werkseinstellung (Nostalgic Neg., alles 0), ueber unser Nostalgic-Neg.-Modell invertiert (Messboden dE 3.3);
dann jedes Rezept mit unserer Pipeline gerechnet (ohne Clarity/Grain/Sharpness) und mit dem Kamerabild verglichen. Bildzuordnung = Reihenfolge der Seite (nicht ausdruecklich beschriftet).

| Befund | Messung | Aenderung |
|---|---|---|
| Ausgangslage | mittlerer dE ueber 7 Rezepte **11.5** (Vericolor Warm 29.9: 3000 K) | – |
| **Kelvin-WB** | Kamera wirkt viel schwaecher als unser "Licht neutralisieren": z. B. 3000 K + R+8/B-9: Modell B x2.0, Kamera x0.85 | Kelvin-Gains mit Exponent 0.4 |
| **WB-Shift Blau** | B-Stufe wirkt staerker als Rot | Blau 2^0.08 statt 2^0.05 pro Stufe (Rot 0.05) |
| **DR400** | bei 3 sauberen Rezepten fehlt dem Modell +8-12 % Displaywert in Schatten/Mitten (Rest +20..+34 von 255), Lichter +1..+13 | additive Anhebung (Tabelle `DR_LIFT`, mit 0.85 skaliert, weil Agfa und 1970's Summer dann um ca. 15/255 zu hell werden) |
| **DR200** | Nostalgic Americana (DR200): Luma-Rest ~0 | keine Aenderung |
| **DR100 / Highlight / Shadow / Color / CCE** | Vericolor Warm (DR100, H-2, S-1, Color+2, CCE/FX Blue Strong): dE 3.7 = Messboden, sobald der WB frei angepasst ist | keine Aenderung; Vorzeichen Highlight (+ = dunklere Lichter) bleibt: Umdrehen machte VW von 3.7 auf 6.4 schlechter |
| neue Kurvenform H/S (14.93 r^5 (1-r)) | an den 2 sauberen Rezepten besser (VW 4.8 -> 3.7, Americana 4.3 -> 3.9), an 1970's Summer/Nostalgia Negative leicht schlechter | beibehalten |
| **Ergebnis** | mittlerer dE ueber 7 Rezepte **11.5 -> 7.7** (Americana 4.8, Vericolor Warm 5.3, VPS 7.5, 1970's 8.6, Kodak Neg. 8.9, Nostalgia Neg. 9.5, Agfa 9.0) | – |

**Grenzen:** Alle Konstanten (Kelvin-Exponent, Blau-Schritt, DR400-Tabelle) sind an **einer Aufnahme** mit 7 Rezepten angepasst (3-5 Freiheitsgrade, in-sample). Mit frei gefittetem WB laege der dE bei 4-6, der WB bleibt also die groesste Restabweichung.
Die Einzelfits der freien WB-Gains (R/B) lassen sich nicht zu einem Modell verdichten (B-Shift im Datensatz nur -3..-9, kollinear). Der R-Shift ist praktisch nicht bestimmbar. Auto-WB der Kamera gegen unsere as-shot-Annahme ist nicht gemessen (Szene war sonnig, ~Tageslicht).
Weitere Szenen mit Rezepten auf Basis anderer Sims (Classic Chrome, Reala Ace, Classic Neg.) fehlen noch.
