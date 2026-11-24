# DRAFT – Überarbeitung von Farb- und Effektdarstellung (Stand 2026-11-24)

Status: **Entwurf zur Freigabe.** Es wurde noch kein Rendering-Code geändert. Alles unten ist Recherche + Plan.
Gekennzeichnet ist, was **belegt** (Messung/Hersteller), **Forenmeinung** oder **Vermutung von mir** ist.

## 1. Befund: warum die Bilder nicht zu den Beispielbildern passen (Hypothesen, nach Wahrscheinlichkeit)

Ausgangslage aus `calibration/RESULTS.md` und `pipeline.py`: Nur Classic Chrome (Farbkorrektur), Belichtung, Grain,
Color Chrome Effect und FX Blue sind gegen echte Fuji-Dateien gemessen. Alles andere ist geschätzt, „bewusst mild“.
Die importierten fujixweekly-Rezepte benutzen aber genau die ungemessenen Stellschrauben stark:

| Rezept (importiert) | Basis-Sim | DR | Highlight/Shadow | Color | Clarity | WB |
|---|---|---|---|---|---|---|
| Kodak Pro 400 | Reala Ace | **400** | −2 / 0 | +1 | −2 | 5200K, +2R/−3B |
| Reala Ace (X-T5) | **Classic Neg.** (trotz Titel) | **400** | −1,5 / −2 | +2 | −2 | Auto, −1R/+1B |
| Nostalgic Americana | Nostalgic Neg. | 200 | −1 / −1,5 | −2 | −3 | 5800K, −2R/−4B |
| Kodak Vision3 250D v2 | Nostalgic Neg. | 200 | **+4 / +3** | −1 | −2 | Fluorescent 1, **−5R/0B** |

1. **Nicht kalibrierte Sims.** Nostalgic Neg. und Pro Neg. Hi sind reine Näherungen (keine offizielle LUT), Reala Ace /
   Classic Neg. nutzen die Video-LUT ohne Foto-Korrektur. Beim Classic Chrome war die Video-LUT bereits dE 7,2 vom
   Kamera-JPEG entfernt (belegt, eigene Messung); bei den anderen ist der Fehler unbekannt, vermutlich ähnlich oder größer.
2. **DR200/DR400 geschätzt.** Fuji belichtet bei DR200/400 das RAW 1 bzw. 2 Blenden dunkler (ISO-Anhebung) und hebt Schatten
   per Verarbeitung wieder an (Forum/Blogs, mit Messwerten aus Foren bestätigt: „DR400 unterbelichtet um 1 Stop, DR800 um 2“ –
   Nomenklatur je nach Kamera). Das ist ein Tonwert-/Schatten-/Rauschverhalten, kein „mildes Knie über Mittelgrau“.
   Drei der vier Rezepte laufen mit DR200/400 → vermutlich **größte Einzelabweichung bei Helligkeit/Kontrast**.
3. **Highlight/Shadow Tone: 0,035 pro Stufe geschätzt.** Vision3 mit +4/+3 und Pro 400 mit −2 liegen weit außerhalb jeder Messung.
4. **Color (±): pauschal 10 % Sättigung pro Stufe**, in Wirklichkeit vermutlich nicht gleichmäßig über Farbton/Helligkeit.
5. **Weißabgleich.** Fuji-WB-Shift und Kelvin-Presets sind nicht dasselbe wie unsere Gains (Forum: die Shift-Wirkung hängt
   von der Farbtemperatur ab, ein fester Mapping-Faktor `2^(0,05·Stufe)` ist **Vermutung**). Fehler hier färbt das ganze Bild.
   Ein Teil der Rezepte (5800K −2R/−4B, Fluorescent 1 −5R) verschiebt stark.
6. **Sensorunterschied.** Die Beispielbilder sind X-Trans-V-Aufnahmen (X-T5/X100VI), wir rendern Sony A7 III. Eigenes
   Rauschverhalten, andere Farbmatrix → Rezepte sehen nie pixelgleich aus; Ziel muss Annäherung bei Farbe/Tonwerten/Effekten sein.
7. **Belichtung im Rezept.** Die Rezepte nennen Belichtungskorrektur (+⅓…+2); Beispielbilder sind damit gemacht. Unsere
   Auto-Belichtung ist fest (+1,04 EV Sony) – Bilder sehen daher dunkler/heller aus als die Beispiele. Hinweis in der GUI/Rezept-Import fehlt.
8. **Reihenfolge der Pipeline unbelegt.** Forum: Fuji wende vermutlich ein Kameraprofil/Baseline-Kurve **vor** der Film-Sim an
   (Forenmeinung, nicht belegt). Wir gehen ProPhoto→F-Gamut C→F-Log2→LUT, das ist plausibel, aber die DR-/Tone-Stufen
   sitzen nach/in der LUT (`k_lut_look` knee) statt davor.

## 2. Quellenkatalog (was ich im Netz gefunden habe)

### 2.1 Hersteller / Fachwissen
- Fujifilm zu Color Chrome Effect (Marketing, kein Algorithmus): Tonalitätsanalyse aus Sensordaten, soll Kanalüberlast bei
  gesättigten Rot/Orange/Grün-Tönen vermeiden, Herkunft Fortia; **kein** Sättigungsregler, Rechenzeit ca. 1 s;
  wirkt nicht auf RAW. https://fujifilm-x.com/en-gb/learning-centre/color-chrome-and-film-grain-effects
- Offizielle F-Log2/F-Log2C-LUTs (Video, 10 Sims): https://petapixel.com/2025/11/18/fujifilms-new-f-log2-and-f-log2c-film-simulation-luts-look-fantastic ,
  https://www.fujifilm-x.com/en-ie/?p=77176 (Download). Keine Aussage zur Übereinstimmung mit Kamera-JPEG.
- Clarity: Fujifilm-Handbuch: ändert „Definition“, Lichter/Schatten kaum; fujixweekly: Mikrokontrast der Mitteltöne, 0 vs ±2 schwer
  sichtbar, +2 vs −2 deutlich; Diffusionsfilter-Vergleich: 5 % CineBloom ≈ −1…−2, 10 % ≈ −3…−4, 20 % ≈ −5 (Autor, grob).
  https://fujixweekly.com/2026/04/05/what-does-clarity-actually-do/
- D-Range Priority: ersetzt DR + Highlight/Shadow; Weak ≈ DR200 mit Highlight −2/Shadow −3 (nicht exakt einstellbar);
  Auto ≈ DR200 H/S −1 (X-T5, GFX100S II) bzw. DR400 H/S −2 (X-E4); nach Kamera verschieden.
  https://fujixweekly.com/2025/01/17/the-curious-case-of-d-range-priority-auto/
- WB-Shift: zwei Achsen R/B −9…+9, keine Stufengröße veröffentlicht; DPReview-Experiment: Kelvin ≈ Verschiebung entlang der „weißen Linie“ des Shift-Gitters.
  https://fujixweekly.com/2020/08/19/fujifilm-white-balance-shift-what-it-is-how-to-use-it ,
  https://www.dpreview.com/forums/thread/4675011
- Grain: nur Off/Weak/Strong × Small/Large; Acros hat zusätzlich eingebautes ISO-abhängiges Korn; GFX-Korn ist nicht gleich skaliert wie X-Korn.
  https://fujixweekly.com/2019/12/06/fujifilm-grain-settings/ , https://fujixweekly.com/2025/01/03/fujifilm-grain-comparison-gfx100s-ii-vs-x-t5/

### 2.2 Technik-Diskussionen (Forenmeinung, selten Messungen)
- pixls.us „Replicating Fujifilm JPG colors from RAW“ (5 Seiten): Fuji-Tonkurve eigenartig (langsames Highlight-Rolloff),
  WB-Shift abhängig von Farbtemperatur, gezielte Farbtonverschiebungen („Memory Colors“), Klarheit/Color Chrome vermutlich räumlich
  und nicht per LUT abbildbar. Hilfreiche Zahlen: darktable-Sigmoid-Kontrast 1,5–1,8 + ca. +20 % Sättigung bei Classic-Chrome-LUT.
  https://discuss.pixls.us/t/replicating-fujifilm-jpg-colors-from-raw-files/34458
  und https://discuss.pixls.us/t/or-why-simulating-different-films-might-not-be-as-easy-as-you-think/19817
- Zwei-Stufen-Ansatz (erst Tonkurve, dann Farb-CLUT) funktioniert robuster als eine einzige LUT (bastibe, selber Thread).
- Andere Projekte: Fujifier (Adobe-Kameraprofile, keine Messung) https://github.com/ip-web/Fujifier ;
  fujifilm-converter https://github.com/chr1sc2y/fujifilm-converter ; grawji (nutzt echte Kamera-Engine per USB, braucht Fuji-Body)
  https://github.com/p5k369/grawji ; Sowerby-LUTs https://blog.sowerby.me/fuji-film-simulation-profiles/ ;
  colormatch (ICC aus JPG/RAW) https://github.com/pmjdebruijn/colormatch ; clut2dtstyle https://github.com/manu-mannattil/clut2dtstyle .
  **Keines enthält Messungen** zu Grain/CCE/Clarity/DR; wir sind mit `RESULTS.md` bereits weiter.

### 2.3 Bilder für den Effekt-Abgleich (nichts davon bisher heruntergeladen)
**A. RAF + Kamera-JPEG-Paare (echte Referenz, Pixel-Vergleich möglich):**
- pixls X-T3 DSCF5240 (Provia): RAF https://discuss.pixls.us/uploads/short-url/wi0eTfdVXe5hrqibOKqVDelVaMx.RAF ,
  JPG https://d2x313g9lpht1q.cloudfront.net/original/3X/a/0/a0bc6300374dabc6ef4ea4ab49297c97eb6dd6e3.jpeg
- pixls X-T4 DSCF2999 (CC-BY-SA): RAF https://discuss.pixls.us/uploads/short-url/lFu9bEdMZJAcXUJV7tEa1RLrtHl.RAF ,
  JPG https://discuss.pixls.us/uploads/short-url/3h3cgekleuJaatJkU6vZGT2IKE5.jpeg
- Farbtafel zum Profilieren (CC-BY-NC-SA, 39 MB): https://discuss.pixls.us/uploads/short-url/3oUTCKmUEnuBFYrU5AqsyT4WhHJ.zip
- Weitere Beispiel-RAFs: https://www.kristoffertrolle.com/2020/fujifilm-sample-raw-files/ ; Imaging-Resource X-T5 RAFs
  (z. B. https://Imaging-Resource.Com/PRODS/fuji-x-t5/Y-JG-FUJI-X-T5-1643.RAF.HTM) – zu prüfen, ob JPG dazu und welche Einstellungen.
- Schon genutzt: 13 X-T2-Paare Photography Blog (`refs/xt2`).

**B. Gleiche Szene, nur eine Einstellung geändert (JPG↔JPG-Fit, kein RAW nötig):**
- Clarity +5/+2/0/−2/−5 (1000×1000): `https://i0.wp.com/fujixweekly.com/wp-content/uploads/2026/04/` + `49892402096_42791a1082_h.jpg` (+5),
  `49891880468_faf88ddbca_h.jpg` (+2), `49892412141_b7b914f888_h.jpg` (0), `49892735342_bbec9de930_h.jpg` (−2), `49892765167_8b967e4be2_h.jpg` (−5).
  *(Seite bestätigt nicht ausdrücklich, dass es derselbe Bildausschnitt ist – vor Messung prüfen.)*
- DR / Highlight / Shadow, In-Camera-Reprocess desselben Bildes, Präfix `https://i0.wp.com/fujixweekly.com/wp-content/uploads/2025/01/`:
  X-E4: `54272057403_1002d1544e_h.jpg` (Auto), `54272238820_c952b22a97_h.jpg` (Strong), `54272285695_7a1cf7fd56_h.jpg` (Weak),
  `54272240735_7241c210c2_h.jpg` (DR200 H/S −1), `54271814561_727e7973ff_h.jpg` (DR400 H/S −2), `54270928647_9717f0b5c5_h.jpg` (DR200 H/S −2);
  GFX100S II: `54270901197_9e19f95cf0_h.jpg`, `54272029908_606a89a662_h.jpg`, `54272208390_bd138f244d_h.jpg`, `54272191744_7b7e9d0f63_h.jpg`, `54271945456_3f511a5207_h.jpg`.
  → liefert direkt die **fehlende DR-/Tone-Messung** (Differenz DR100-Basis vs. DR200/400 und H/S-Stufen).
- WB-Shift: 0R/0B vs +1R/−1B (799×533): `https://i0.wp.com/fujixweekly.com/wp-content/uploads/2020/08/` + `50238530887_c51c522d3f_c.jpg`, `50238317291_1140153a2f_c.jpg`;
  4200K 0R/+9B vs Auto: `50242154317_f220532c1d_c.jpg`, `50241305148_1aac13d323_c.jpg`. Das 9-Punkte-Gitter
  `https://fujixweekly.com/wp-content/uploads/2018/10/img_8286.jpg` ist laut Autor niedrig aufgelöst/Flickr-komprimiert → nur grob nutzbar.
- Grain (schon teils genutzt): `https://i0.wp.com/fujixweekly.com/wp-content/uploads/2019/12/` + `49164104658_3001289d09_c.jpg` (Off), `49165875823_313ddd1c3b_c.jpg` (Weak),
  `49166606782_ee8be9ba57_c.jpg` (Strong), zweite Szene `49164584526_…`, `49166587417_…`, `49166369571_…`; Acros-Paare `49163804378_…`, `49163844488_…`.

**C. Zielbilder der importierten Rezepte (nur Beispiele, **kein** RAW, X-Trans V, teils In-Camera-Reprocess, daher nur Statistik-Vergleich):**
- Kodak Pro 400 (https://fujixweekly.com/2025/09/06/kodak-pro-400-fujifilm-x-trans-v-film-simulation-recipe/): `…/uploads/2025/09/54766237513_9a02f64a07_h.jpg`, `54766230618_a7eabad565_h.jpg`, `54766342185_f5d8e1b8e8_h.jpg`
- Reala Ace X-T5 (…/2023/09/15/reala-ace-…): `…/uploads/2023/09/53186152253_6f183d7bc0_h.jpg`, `53189821876_8b41b60a41_h.jpg`, `53185551515_0886002815_h.jpg`
- Nostalgic Americana (…/2024/04/29/…): `…/uploads/2024/04/53598328913_351a4c2cc0_h.jpg`, `53597842496_8adad20195_h.jpg`, `53597869891_6eecb335b5_h.jpg`
- Kodak Vision3 250D v2 (…/2023/12/19/…): `…/uploads/2023/12/53402641528_849a588ba7_h.jpg`, `53408992560_6004f3bbba_h.jpg`, `53402777099_d04bcdef3c_h.jpg`
- Übrige 8 Rezepte: Artikel-URLs liegen vor (fujixweekly.com, 2024-2026), Bilder bei Bedarf nachziehen.
Hinweis: Alle Links stammen aus den Seiten selbst; ob die nackten Pfade ohne `?resize=` erreichbar sind und welche Originalgröße sie haben, ist **nicht geprüft**.

## 3. Vorgehen (Vorschlag, Phasen mit Messkriterium)

**Phase 0 – Diagnose am Beispiel (klein, ca. 1 Std.):** Du nennst ein Rezept + Beispielbild, das „absolut nicht passt“. Ich rendere
Rezept auf einem ähnlichen Sony-Motiv und lege Histogramm/Farbverteilung neben das Beispiel, um die dominante Abweichung
(Helligkeit/DR? Farbstich/WB? Sättigung?) festzustellen, bevor ich irgendetwas umbaue.

**Phase 1 – Messen, was noch fehlt (JPG↔JPG, ohne RAW):**
1. DR100→DR200/DR400 und Highlight/Shadow-Stufen aus dem X-E4/GFX-Set (Tonkurven-Differenz je Helligkeitsbereich).
2. Clarity ±2/±5 aus den Bildpaaren: Radius, Stärke je Stufe, Wirkung auf Mitteltöne vs. Lichter/Schatten.
3. WB-Shift-Stufengröße und Interaktion mit Kelvin aus den Paaren (grob; Gitterbild nur zur Plausibilisierung).
4. Color ±: falls ein Paar auffindbar ist (fujixweekly „Color“-Artikel noch nicht durchsucht).
Ergebnis jeweils mit Fehlermaß in `RESULTS.md` (dE bzw. Tonkurven-Abweichung), keine Werte ohne Messung.

**Phase 2 – Foto-Rendering der übrigen Sims:** RAF+JPG-Paare (A) für Classic Neg., Reala Ace, Astia, Eterna, Pro Neg., Velvia
nachladen und die Korrektur-LUT-Methode (wie Classic Chrome) auf jede Sim anwenden, die mit ≥ 6 Paaren belegbar ist.
Nostalgic Neg./Pro Neg. Hi (keine LUT) erst, wenn Paare verfügbar sind; sonst bleibt „Näherung“ sichtbar gekennzeichnet.

**Phase 3 – Pipeline-Umbau:** (a) DR als Belichtungs-/Schattenmodell vor der Film-Sim, (b) Tone/Color als gemessene Kurven statt
Konstanten, (c) WB-Shift in Mired/chromatische Adaption, (d) Rezept-Import übernimmt Belichtungskorrektur als Hinweis,
(e) Kennzeichnung je Regler „gemessen / geschätzt“ in der GUI.

**Phase 4 – Validierung:** Leave-one-out über alle Paare; Zielwert: dE auf geglätteten Bildern ≤ 5,6 (aktueller CC-Wert) und
Grain/CCE nicht schlechter als jetzt. Visueller Kontrollsatz: die 4 Rezepte oben gegen ihre Beispielbilder.

## 4. Grenzen (ehrlich)
- Ohne Fuji-Kamera oder X RAW Studio gibt es keine Ground-Truth für beliebige Rezepte auf **Sony-RAWs**; wir kalibrieren
  über fremde X-Trans-Paare. Perfekte Pixelgleichheit ist nicht erreichbar (Sensor, Objektivkorrektur, NR/Schärfung der Kamera).
- Fuji veröffentlicht keine Algorithmen (Color Chrome, Clarity, Grain); alles ist gemessen oder gefolgert.
- Lizenzen: pixls-Dateien (CC-BY-SA / CC-BY-NC-SA) nur lokal zur Messung; Fujifilm-LUTs nicht weitergeben (steht schon im README);
  fujixweekly-Bilder nur für private Messung, nicht in das Repo einchecken.

## 5. Offene Entscheidungen für dich
1. Welches Rezept + Beispielbild passt am schlechtesten (für Phase 0)?
2. Darf ich die oben aufgelisteten Bilder herunterladen (ca. 100–150 MB inkl. 2 RAFs) und in `refs/` ablegen?
3. Gibt es Zugriff auf eine Fuji-Kamera / X RAW Studio? Das wäre mit Abstand die beste Referenz (Sony-RAW → nicht möglich, aber Fuji-RAF + Rezept → exakt).
