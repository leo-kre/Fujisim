"""PySide6-Editor: Filmstreifen, Vorschau, Regler, 'Apply to all', Export."""
from __future__ import annotations

import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QSettings, QObject, QRectF, QSize, QRunnable, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor, QIcon, QImage, QImageReader, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog,
    QInputDialog, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSplitter, QVBoxLayout, QWidget, QDialog,
    QDialogButtonBox,
)

from . import raw_io
from . import flog, presets, recipe
from .engine import ImageSession, export_file
from .film import FILMS
from .settings import (DR_CHOICES, EFFECT_CHOICES, GRAIN_SIZES, MONO_FILTERS_LIST, PER_IMAGE_KEYS,
                       WB_MODES, EditSettings, app_defaults)

THUMB_W, THUMB_H = 200, 134      # Rahmen der Filmstreifen-Vorschau (Hoch- und Querformat passen hinein)

# key, Label, min, max, scale(Wert = int/scale), Dezimalstellen
SLIDER_GROUPS = [
    ("Fuji: Tonwerte && Farbe", [
        ("highlight_tone", "Highlight Tone", -4, 8, 2, 1),
        ("shadow_tone", "Shadow Tone", -4, 8, 2, 1),
        ("color", "Color", -4, 4, 1, 0),
        ("clarity", "Clarity", -5, 5, 1, 0),
        ("sharpness", "Sharpness", -4, 4, 1, 0),
        ("noise_reduction", "Noise Reduction", -4, 4, 1, 0),
    ]),
    ("Fuji: Weißabgleich", [
        ("wb_kelvin", "Kelvin", 25, 100, 0.01, 0),
        ("wb_shift_r", "WB Shift Red", -9, 9, 1, 0),
        ("wb_shift_b", "WB Shift Blue", -9, 9, 1, 0),
    ]),
    ("Monochrom (Acros/Mono)", [
        ("mono_wc", "Mono Color WC", -18, 18, 1, 0),
        ("mono_mg", "Mono Color MG", -18, 18, 1, 0),
    ]),
    ("Belichtung", [("exposure", "Belichtungskorrektur (EV)", -300, 300, 100, 2)]),
    ("Zusätze (nicht in der Kamera)", [
        ("intensity", "Look-Intensität", 0, 100, 100, 2),
        ("contrast", "Kontrast", -100, 100, 1, 0),
        ("halation", "Halation", 0, 100, 100, 2),
        ("bloom", "Bloom", 0, 100, 100, 2),
        ("vignette", "Vignette", 0, 100, 100, 2),
    ]),
    ("Eigene LUT (optional, .cube)", [("lut_strength", "LUT-Stärke", 0, 100, 100, 2)]),
]

# key, Label, Auswahl
COMBO_SPECS = [
    ("dynamic_range", "Dynamic Range", DR_CHOICES),
    ("grain_effect", "Grain Effect", EFFECT_CHOICES),
    ("grain_size", "Grain Size", GRAIN_SIZES),
    ("color_chrome", "Color Chrome Effect", EFFECT_CHOICES),
    ("color_chrome_blue", "Color Chrome FX Blue", EFFECT_CHOICES),
    ("wb_mode", "White Balance", WB_MODES),
    ("mono_filter", "Acros-Filter", MONO_FILTERS_LIST),
]


def to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    h, w, _ = arr.shape
    return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()


# ---------------------------------------------------------------- Worker (ein Thread, "latest wins")
class Worker(QThread):
    """Fuehrt Laden und Rendern nacheinander aus. Es gibt nie eine Warteschlange:
    neue Anfragen ersetzen alte, das Ergebnis veralteter Anfragen wird verworfen."""

    loaded = Signal(int, object)                # load_serial, session
    full_ready = Signal(int)                    # load_serial
    rendered = Signal(int, int, object, object, float)   # load_serial, render_serial, uint8, meta, secs
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.cond = threading.Condition()
        self.load_req = None      # (serial, path)
        self.render_req = None    # dict
        self.full_req = None      # (serial, session)
        self.current_load = 0
        self.quit_flag = False

    def post_load(self, serial, path):
        with self.cond:
            self.current_load = serial
            self.load_req = (serial, path)
            self.render_req = None
            self.full_req = None
            self.cond.notify()

    def post_render(self, job):
        with self.cond:
            self.render_req = job
            self.cond.notify()

    def stop(self):
        with self.cond:
            self.quit_flag = True
            self.load_req = self.render_req = self.full_req = None
            self.current_load = -1
            self.cond.notify()
        if not self.wait(1500):          # steckt in einem langen Dekodier-/Lesevorgang
            self.terminate()
            self.wait(1500)

    def run(self):
        while True:
            with self.cond:
                while not (self.load_req or self.render_req or self.full_req or self.quit_flag):
                    self.cond.wait()
                if self.quit_flag:
                    return
                if self.load_req:
                    kind, item, self.load_req = "load", self.load_req, None
                elif self.render_req:
                    kind, item, self.render_req = "render", self.render_req, None
                else:
                    kind, item, self.full_req = "full", self.full_req, None
            try:
                if kind == "load":
                    serial, path = item
                    sess = ImageSession.open_fast(path)
                    if serial == self.current_load:
                        self.loaded.emit(serial, sess)
                        with self.cond:
                            if serial == self.current_load and not self.load_req:
                                self.full_req = (serial, sess)
                elif kind == "render":
                    if item["load"] != self.current_load:
                        continue
                    t0 = time.perf_counter()
                    out = item["session"].render(item["s"], item["z"], item["X0"], item["Y0"], item["cw"], item["ch"])
                    self.rendered.emit(item["load"], item["serial"], np.ascontiguousarray(out), item["meta"],
                                       time.perf_counter() - t0)
                else:
                    serial, sess = item
                    if serial == self.current_load:
                        sess.load_full()
                        if serial == self.current_load:
                            self.full_ready.emit(serial)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(f"{type(exc).__name__}: {exc}")
            finally:
                item = sess = out = None   # keine Referenz auf das letzte Bild festhalten


class ThumbWorker(QThread):
    """Liest nur die eingebetteten JPEG-Vorschauen (billig). Haelt keine Bilddaten."""
    thumb = Signal(str, object)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        for p in self.paths:
            if self.isInterruptionRequested():
                return
            data = raw_io.thumb_bytes(p)
            if not data:
                continue
            buf = QBuffer()
            buf.setData(data)
            buf.open(QBuffer.ReadOnly)
            rd = QImageReader(buf)
            rd.setAutoTransform(True)
            img = rd.read()
            if not img.isNull():
                self.thumb.emit(p, img.scaled(QSize(THUMB_W * 2, THUMB_H * 2), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class ExportTask(QRunnable):
    def __init__(self, win, jobs, outdir, fmt, quality, max_edge):
        super().__init__()
        self.win, self.jobs, self.outdir = win, jobs, outdir
        self.fmt, self.quality, self.max_edge = fmt, quality, max_edge
        self.cancel = False

    def run(self):
        errors = []
        for i, (path, s) in enumerate(self.jobs):
            if self.cancel:
                break
            self.win.sig.export_progress.emit(i, os.path.basename(path))
            dst = Path(self.outdir) / f"{Path(path).stem}_{s.sim.replace(' ', '').replace('.', '')}.{self.fmt}"
            try:
                export_file(path, s, str(dst), self.quality, self.max_edge)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{os.path.basename(path)}: {exc}")
        self.win.sig.export_done.emit(len(self.jobs), errors)


class Signals(QObject):
    export_progress = Signal(int, str)
    export_done = Signal(int, list)


# ---------------------------------------------------------------- Bildanzeige mit Zoom/Pan
class ImageView(QWidget):
    """Zeigt das gerenderte Ausschnittsbild. Zoom (Mausrad), Pan (Ziehen), Doppelklick: Fit <-> 100 %.

    Bildkoordinaten sind Originalpixel; `zoom` = Geraetepixel pro Originalpixel.
    """
    viewChanged = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.StrongFocus)
        self.W = self.H = 0
        self.fit = True
        self.zoom = 1.0
        self.cx = self.cy = 0.0
        self.img = None
        self.meta = None
        self.drag = None
        self.message = "RAW-Dateien hierher ziehen\noder „Öffnen“ wählen"

    # -- Geometrie
    def dev(self):
        r = self.devicePixelRatioF()
        return max(1, int(self.width() * r)), max(1, int(self.height() * r)), r

    def fit_zoom(self):
        dw, dh, _ = self.dev()
        return min(dw / self.W, dh / self.H, 1.0) if self.W else 1.0

    def eff_zoom(self):
        return self.fit_zoom() if self.fit else self.zoom

    def vrect(self):
        """-> (z, left, top, vw, vh) in Bildkoordinaten."""
        dw, dh, _ = self.dev()
        z = self.eff_zoom()
        vw, vh = dw / z, dh / z
        if self.fit or vw >= self.W:
            cx = self.W / 2
        else:
            cx = min(max(self.cx, vw / 2), self.W - vw / 2)
        if self.fit or vh >= self.H:
            cy = self.H / 2
        else:
            cy = min(max(self.cy, vh / 2), self.H - vh / 2)
        self.cx, self.cy = cx, cy
        return z, cx - vw / 2, cy - vh / 2, vw, vh

    def request_params(self, q: float):
        """Ausgabegitter-Ausschnitt fuer den Renderer: (zr, X0, Y0, cw, ch)."""
        z, left, top, vw, vh = self.vrect()
        zr = z * q
        X0, Y0 = max(0, round(left * zr)), max(0, round(top * zr))
        X1 = min(round(self.W * zr), round((left + vw) * zr))
        Y1 = min(round(self.H * zr), round((top + vh) * zr))
        return zr, X0, Y0, max(1, X1 - X0), max(1, Y1 - Y0)

    # -- Anzeige
    def set_size(self, W, H, reset=True):
        if reset or (W, H) != (self.W, self.H):
            sx = W / self.W if self.W else 1
            self.W, self.H = W, H
            if reset:
                self.fit = True
            else:
                self.cx *= sx
                self.cy *= sx

    def set_image(self, qimg, meta):
        self.img, self.meta = qimg, meta
        self.update()

    def clear(self, message=""):
        self.img = self.meta = None
        self.W = self.H = 0
        self.message = message
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.contentsRect(), QColor(24, 24, 24))
        if self.img is None or not self.W:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.contentsRect(), Qt.AlignCenter, self.message)
            return
        z, left, top, _, _ = self.vrect()
        zr, Xa, Ya = self.meta
        r = self.devicePixelRatioF()
        sx = z / zr
        tgt = QRectF((Xa / zr - left) * z / r, (Ya / zr - top) * z / r,
                     self.img.width() * sx / r, self.img.height() * sx / r)
        p.setRenderHint(QPainter.SmoothPixmapTransform, abs(sx - 1) > 1e-3)
        p.drawImage(tgt, self.img)

    # -- Interaktion
    def _changed(self):
        self.update()
        self.viewChanged.emit()

    def wheelEvent(self, e):
        if not self.W:
            return
        z, left, top, vw, vh = self.vrect()
        r = self.devicePixelRatioF()
        px, py = e.position().x() * r, e.position().y() * r
        ix, iy = left + px / z, top + py / z
        steps = e.angleDelta().y() / 120.0
        z2 = min(max(z * (1.2 ** steps), self.fit_zoom()), 8.0)
        if z2 <= self.fit_zoom() * 1.001:
            self.fit = True
        else:
            self.fit, self.zoom = False, z2
            dw, dh, _ = self.dev()
            self.cx = ix - px / z2 + dw / z2 / 2
            self.cy = iy - py / z2 + dh / z2 / 2
        self._changed()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.W:
            self.drag = (e.position(), self.cx, self.cy)

    def mouseMoveEvent(self, e):
        if self.drag and self.W and not self.fit:
            r = self.devicePixelRatioF()
            p0, cx0, cy0 = self.drag
            z = self.eff_zoom()
            self.cx = cx0 - (e.position().x() - p0.x()) * r / z
            self.cy = cy0 - (e.position().y() - p0.y()) * r / z
            self._changed()

    def mouseReleaseEvent(self, e):
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        if not self.W:
            return
        if self.fit:
            r = self.devicePixelRatioF()
            z, left, top, _, _ = self.vrect()
            self.cx = left + e.position().x() * r / z
            self.cy = top + e.position().y() * r / z
            self.fit, self.zoom = False, 1.0
        else:
            self.fit = True
        self._changed()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_0:
            self.fit = True
            self._changed()
        elif e.key() == Qt.Key_1 and self.W:
            self.fit, self.zoom = False, 1.0
            self._changed()

    def resizeEvent(self, e):
        self.viewChanged.emit()


class ResetSlider(QSlider):
    """Doppelklick setzt den Regler auf den Standardwert zurück."""

    def __init__(self, default):
        super().__init__(Qt.Horizontal)
        self.default = default

    def mouseDoubleClickEvent(self, e):
        self.setValue(self.default)


# ---------------------------------------------------------------- Hauptfenster
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FujiSim – Fujifilm-Looks für Sony RAW")
        self.resize(1500, 920)
        self.setAcceptDrops(True)

        self.sig = Signals()
        self.export_pool = QThreadPool()
        self.export_pool.setMaxThreadCount(1)
        self.worker = Worker()
        self.worker.loaded.connect(self.on_loaded)
        self.worker.full_ready.connect(self.on_full_ready)
        self.worker.rendered.connect(self.on_rendered)
        self.worker.failed.connect(lambda m: self.statusBar().showMessage(f"Fehler: {m}", 10000))
        self.worker.start()
        self.thumb_worker = None

        self.session: ImageSession | None = None     # das EINZIGE gehaltene Bild
        self.load_serial = 0
        self.render_serial = 0
        self.settings: dict[str, EditSettings] = {}
        self.items: dict[str, QListWidgetItem] = {}
        self.current: str | None = None
        self.loading_ui = False
        self.show_before = False
        self.export_task = None
        self.progress = None
        self.full_time = 0.12          # geschaetzte Renderzeit bei voller Qualitaet (s)
        self.last_info = ""

        self.load_timer = QTimer(self)
        self.load_timer.setInterval(500)
        self.load_timer.timeout.connect(self._tick_loading)
        self.load_t0 = 0.0
        self.load_cloud = False
        self.idle = QTimer(self)       # nach Interaktion: Endqualitaet rendern
        self.idle.setSingleShot(True)
        self.idle.setInterval(170)
        self.idle.timeout.connect(lambda: self.request_render(False))

        self.sig.export_progress.connect(self.on_export_progress)
        self.sig.export_done.connect(self.on_export_done)

        self._build_ui()
        self.refresh_presets()
        for key, step in ((Qt.Key_Left, -1), (Qt.Key_Right, 1)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(lambda st=step: self.step_image(st))
        self.qs = QSettings("FujiSim", "FujiSim")

    # ---- UI
    def _build_ui(self):
        tb = self.addToolBar("Datei")
        tb.setMovable(False)
        for text, fn in (("Dateien öffnen…", self.open_files), ("Ordner öffnen…", self.open_folder),
                         ("Fuji-LUT-Ordner…", self.choose_lut_dir)):
            act = QAction(text, self)
            act.triggered.connect(fn)
            tb.addAction(act)

        self.list = QListWidget()
        self.list.setIconSize(QSize(THUMB_W, THUMB_H))
        self.list.setFixedWidth(THUMB_W + 48)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSpacing(4)
        self.list.currentItemChanged.connect(self.on_select)

        self.view = ImageView()
        self.view.viewChanged.connect(lambda: self.request_render(True))

        panel = QWidget()
        pl = QVBoxLayout(panel)

        # Presets
        gp = QGroupBox("Presets")
        pv = QVBoxLayout(gp)
        self.preset_box = QComboBox()
        self.preset_box.activated.connect(self.on_preset_chosen)
        pv.addWidget(self.preset_box)
        prow = QHBoxLayout()
        self.preset_btns = []
        for text, fn in (("Speichern als…", self.save_preset_as), ("Überschreiben", self.overwrite_preset),
                         ("Löschen", self.delete_preset)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            prow.addWidget(b)
            self.preset_btns.append(b)
        pv.addLayout(prow)
        pl.addWidget(gp)

        # Film-Auswahl
        gb = QGroupBox("Fuji: Film Simulation")
        fl = QFormLayout(gb)
        self.sim_box = QComboBox()
        sims = list(FILMS)
        self.sim_box.addItems(sims)
        self.sim_box.currentTextChanged.connect(self.on_sim)
        self.note = QLabel("")
        self.note.setStyleSheet("color:#999")
        self.note.setWordWrap(True)
        fl.addRow("Simulation", self.sim_box)
        fl.addRow("", self.note)
        pl.addWidget(gb)

        gbc = QGroupBox("Fuji: Kameraeinstellungen")
        cl = QFormLayout(gbc)
        self.combos: dict[str, QComboBox] = {}
        for key, label, choices in COMBO_SPECS:
            cb = QComboBox()
            cb.addItems(choices)
            cb.currentTextChanged.connect(lambda v, k=key: self.set_value(k, v))
            cl.addRow(label, cb)
            self.combos[key] = cb
        pl.addWidget(gbc)

        self.sliders: dict[str, tuple[QSlider, QLabel, float, int]] = {}
        defaults = EditSettings()
        for title, items in SLIDER_GROUPS:
            box = QGroupBox(title)
            form = QFormLayout(box)
            if title.startswith("Belichtung"):
                self.auto_chk = QCheckBox("Kamera-Belichtung (fest, wie die Kamera)")
                self.auto_chk.toggled.connect(lambda v: self.set_value("auto_exposure", v))
                form.addRow(self.auto_chk)
            if title.startswith("Eigene LUT"):
                row = QHBoxLayout()
                self.lut_label = QLabel("keine")
                b1, b2 = QPushButton("Laden…"), QPushButton("Entfernen")
                b1.clicked.connect(self.load_lut)
                b2.clicked.connect(self.clear_lut)
                row.addWidget(self.lut_label, 1)
                row.addWidget(b1)
                row.addWidget(b2)
                form.addRow(row)
            for key, label, lo, hi, scale, dec in items:
                dflt = round(getattr(defaults, key) * scale)
                sl = ResetSlider(dflt)
                sl.setRange(lo, hi)
                sl.setValue(dflt)
                val = QLabel("")
                val.setFixedWidth(46)
                val.setAlignment(Qt.AlignRight)
                sl.valueChanged.connect(lambda v, k=key: self.on_slider(k, v))
                row = QHBoxLayout()
                row.addWidget(sl, 1)
                row.addWidget(val)
                form.addRow(label, row)
                self.sliders[key] = (sl, val, scale, dec)
            pl.addWidget(box)

        # Aktionen
        act = QGroupBox("Aktionen")
        al = QVBoxLayout(act)
        self.apply_btn = QPushButton("Apply to all  →  Einstellungen auf alle Bilder")
        self.apply_btn.setStyleSheet("font-weight:bold; padding:8px; background:#2d6cdf; color:white;")
        self.apply_btn.clicked.connect(self.apply_to_all)
        self.keep_chk = QCheckBox("Belichtung & Weißabgleich pro Bild behalten")
        self.before_btn = QPushButton("Vorher (gedrückt halten)")
        self.before_btn.pressed.connect(lambda: self.set_before(True))
        self.before_btn.released.connect(lambda: self.set_before(False))
        reset = QPushButton("Zurücksetzen")
        reset.clicked.connect(self.reset_current)
        rrow = QHBoxLayout()
        rin, rout = QPushButton("Rezept einfügen…"), QPushButton("Rezept kopieren")
        rin.clicked.connect(self.paste_recipe)
        rout.clicked.connect(self.copy_recipe)
        rrow.addWidget(rin)
        rrow.addWidget(rout)
        srow = QHBoxLayout()
        sf, lf = QPushButton("Einstellungen speichern…"), QPushButton("Einstellungen laden…")
        sf.clicked.connect(self.save_settings_file)
        lf.clicked.connect(self.load_settings_file)
        srow.addWidget(sf)
        srow.addWidget(lf)
        ex1, exa = QPushButton("Aktuelles exportieren…"), QPushButton("Alle exportieren…")
        ex1.clicked.connect(lambda: self.export(False))
        exa.clicked.connect(lambda: self.export(True))
        row2 = QHBoxLayout()
        row2.addWidget(ex1)
        row2.addWidget(exa)
        for w in (self.apply_btn, self.keep_chk, self.before_btn, reset):
            al.addWidget(w)
        al.addLayout(rrow)
        al.addLayout(srow)
        al.addLayout(row2)
        pl.addWidget(act)
        pl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(400)

        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.addWidget(scroll)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.statusBar().showMessage("Bereit")
        self.refresh_controls(EditSettings())
        self.set_controls_enabled(False)

    def step_image(self, d: int):
        if QApplication.activeModalWidget() is not None or not self.isActiveWindow():
            return
        n = self.list.count()
        if not n:
            return
        row = max(0, min(n - 1, self.list.currentRow() + d))
        if row != self.list.currentRow():
            self.list.setCurrentRow(row)       # loest on_select aus -> Bild wird sofort geladen
            self.list.scrollToItem(self.list.currentItem())

    # ---- Sitzung merken / wiederherstellen
    def save_session(self):
        try:
            self.qs.setValue("paths", json.dumps(list(self.settings)))
            self.qs.setValue("current", self.current or "")
            self.qs.sync()
        except Exception:  # noqa: BLE001
            pass

    def restore_session(self):
        try:
            paths = [p for p in json.loads(self.qs.value("paths", "[]")) if os.path.exists(p)]
            cur = self.qs.value("current", "")
        except Exception:  # noqa: BLE001
            return
        if not paths:
            return
        self.add_paths(paths)
        if cur in self.items:
            self.list.setCurrentItem(self.items[cur])
            self.list.scrollToItem(self.items[cur])

    # ---- Einstellungen als Datei speichern / laden
    def save_settings_file(self):
        if not self.current:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Einstellungen speichern", "fujisim-settings.json",
                                           "JSON (*.json)")
        if not f:
            return
        s = self.settings[self.current]
        Path(f).write_text(s.to_json())
        self.statusBar().showMessage(f"Einstellungen gespeichert: {f}", 6000)

    def load_settings_file(self):
        if not self.current:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Einstellungen laden", "", "JSON (*.json)")
        if not f:
            return
        try:
            d = json.loads(Path(f).read_text())
            new = EditSettings.from_dict(d.get("settings", d))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Einstellungen", f"Datei konnte nicht gelesen werden: {exc}")
            return
        self.settings[self.current] = new
        self.refresh_controls(new)
        self.request_render(False)
        self.statusBar().showMessage(f"Einstellungen geladen: {Path(f).name}", 6000)

    def set_controls_enabled(self, on: bool):
        for w in (self.sim_box, self.auto_chk, self.apply_btn, self.before_btn, self.preset_box,
                  *self.preset_btns, *self.combos.values()):
            w.setEnabled(on)
        for sl, *_ in self.sliders.values():
            sl.setEnabled(on)

    # ---- Dateien
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])

    def open_files(self):
        exts = " ".join(f"*{x} *{x.upper()}" for x in sorted(raw_io.RAW_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, "RAW-Dateien", "", f"RAW ({exts})")
        self.add_paths(files)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Ordner mit RAW-Dateien")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        files = []
        for p in map(Path, paths):
            if p.is_dir():
                files += sorted(q for q in p.iterdir() if q.suffix.lower() in raw_io.RAW_EXT)
            elif p.suffix.lower() in raw_io.RAW_EXT:
                files.append(p)
        new = []
        for f in files:
            sp = str(f)
            if sp in self.settings:
                continue
            self.settings[sp] = app_defaults()
            it = QListWidgetItem(f.name)
            it.setData(Qt.UserRole, sp)
            it.setSizeHint(QSize(THUMB_W + 24, THUMB_H + 30))
            it.setIcon(self._placeholder())
            self.list.addItem(it)
            self.items[sp] = it
            if raw_io.is_dataless(sp):
                it.setText("☁ " + f.name)
                it.setToolTip("Nur in iCloud – wird beim Öffnen heruntergeladen")
            else:
                new.append(sp)       # nur lokale Dateien: Vorschau lesen
        if new:
            tw = ThumbWorker(new)          # nur eingebettete JPEG-Vorschauen, keine Rohdaten
            tw.thumb.connect(self.on_thumb)
            self._thumb_refs = [x for x in getattr(self, "_thumb_refs", []) if x.isRunning()] + [tw]
            tw.start()
        if new and self.current is None:
            self.list.setCurrentRow(0)
        self.statusBar().showMessage(f"{self.list.count()} Bilder geladen")

    def _placeholder(self):
        if not hasattr(self, "_ph"):
            pm = QPixmap(THUMB_W, THUMB_H)
            pm.fill(QColor(50, 50, 50))
            self._ph = QIcon(pm)
        return self._ph

    def on_thumb(self, path, img):
        it = self.items.get(path)
        if it is not None:
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(2.0)   # Vorschau ist 2x gross -> scharf auf Retina
            it.setIcon(QIcon(pm))

    # ---- Auswahl: altes Bild freigeben, neues laden
    def on_select(self, item, _prev):
        if item is None:
            return
        self.current = item.data(Qt.UserRole)
        self.set_controls_enabled(True)
        self.refresh_controls(self.settings[self.current])
        self.session = None                      # Speicher des vorherigen Bildes freigeben
        self.render_serial += 1
        self.view.clear("Lade…")
        gc.collect()
        self.load_serial += 1
        self.worker.post_load(self.load_serial, self.current)
        self.load_t0 = time.perf_counter()
        self.load_cloud = raw_io.is_dataless(self.current)
        self.load_timer.start()
        self._tick_loading()

    def _tick_loading(self):
        if self.session is not None or not self.current:
            self.load_timer.stop()
            return
        secs = time.perf_counter() - self.load_t0
        what = "wird aus iCloud heruntergeladen" if self.load_cloud else "lädt"
        self.statusBar().showMessage(f"{os.path.basename(self.current)} {what}… {secs:.0f} s")
        self.view.message = f"{os.path.basename(self.current)}\n{what}… {secs:.0f} s"
        self.view.update()

    def on_loaded(self, serial, sess):
        if serial != self.load_serial:
            return                                # veraltet -> sess wird freigegeben
        self.session = sess
        self.load_timer.stop()
        self.view.set_size(sess.W, sess.H, reset=True)
        self.request_render(False)

    def on_full_ready(self, serial):
        if serial != self.load_serial or self.session is None:
            return
        self.view.set_size(self.session.W, self.session.H, reset=False)
        self.request_render(False)

    # ---- Rendern (Ausschnitt in Bildschirmaufloesung)
    def request_render(self, interactive: bool):
        if self.session is None or not self.current:
            return
        q = 1.0
        if interactive:
            q = float(np.clip(np.sqrt(0.09 / max(self.full_time, 0.01)), 0.4, 1.0))
            self.idle.start()
        zr, X0, Y0, cw, ch = self.view.request_params(q)
        s = self.settings[self.current].copy()
        if self.show_before:
            s = EditSettings(sim="Neutral", exposure=s.exposure, auto_exposure=s.auto_exposure,
                             wb_mode=s.wb_mode, wb_kelvin=s.wb_kelvin)
        self.render_serial += 1
        self.worker.post_render(dict(load=self.load_serial, serial=self.render_serial, session=self.session,
                                     s=s, z=zr, X0=X0, Y0=Y0, cw=cw, ch=ch, meta=(zr, X0, Y0), q=q))

    def on_rendered(self, load, serial, arr, meta, secs):
        if load != self.load_serial or serial != self.render_serial:
            return                                # veraltetes Ergebnis verwerfen
        q = meta[0] / max(self.view.eff_zoom(), 1e-9)
        self.full_time = 0.6 * self.full_time + 0.4 * secs / max(q * q, 0.1)
        self.view.set_image(to_qimage(arr), meta)
        mb = (self.session.W * self.session.H) / 1e6 if self.session else 0
        info = "voll" if (self.session and self.session.has_full) else "Vorschau (volle Auflösung lädt…)"
        if self.session and self.session.gain_info:
            info += f" · {self.session.gain_info}"
        self.statusBar().showMessage(
            f"{os.path.basename(self.current)} · {mb:.0f} MP · Zoom {self.view.eff_zoom() * 100:.0f} % · "
            f"{secs * 1000:.0f} ms · {info}")

    def refresh_controls(self, s: EditSettings):
        self.loading_ui = True
        self.sim_box.setCurrentText(s.sim)
        for key, cb in self.combos.items():
            cb.setCurrentText(getattr(s, key))
        self.auto_chk.setChecked(s.auto_exposure)
        for key, (sl, val, scale, dec) in self.sliders.items():
            sl.setValue(round(getattr(s, key) * scale))
            val.setText(f"{getattr(s, key):.{dec}f}")
        self.lut_label.setText(Path(s.lut_path).name if s.lut_path else "keine")
        self.update_note(s.sim)
        self.loading_ui = False

    def set_value(self, key, value):
        if self.loading_ui or not self.current:
            return
        setattr(self.settings[self.current], key, value)
        self.request_render(True)

    def on_slider(self, key, raw):
        sl, val, scale, dec = self.sliders[key]
        v = raw / scale
        val.setText(f"{v:.{dec}f}")
        self.set_value(key, v)

    def update_note(self, name):
        src = ("Offizielle Fuji-LUT" if name in flog.available_sims()
               else "Näherung (keine Fuji-LUT vorhanden)")
        self.note.setText(f"{src} – {FILMS[name].note}" if name in FILMS else src)

    def on_sim(self, name):
        self.update_note(name)
        self.set_value("sim", name)

    def choose_lut_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Ordner mit den Fuji-LUTs (.cube)", str(flog.lut_dir()))
        if d:
            flog.set_lut_dir(d)
            n = len(flog.available_sims())
            self.statusBar().showMessage(f"{n} Fuji-LUTs gefunden in {d}", 8000)
            if self.current:
                self.update_note(self.settings[self.current].sim)
                self.request_render(False)

    # ---- Rezepte
    def paste_recipe(self):
        if not self.current:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Fuji-Rezept einfügen")
        dlg.resize(460, 420)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Rezept als Text einfügen (z. B. von fujixweekly):"))
        edit = QPlainTextEdit()
        edit.setPlaceholderText("Film Simulation: Classic Chrome\nDynamic Range: DR400\nHighlight: +1\n"
                                "Shadow: +1.5\nColor: +4\nGrain Effect: Strong, Small\n"
                                "White Balance: Auto, +2 Red & -5 Blue")
        lay.addWidget(edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        new, applied, unknown = recipe.apply_recipe(self.settings[self.current], edit.toPlainText())
        self.settings[self.current] = new
        self.refresh_controls(new)
        self.request_render(False)
        msg = f"Rezept angewendet ({len(applied)} Werte)"
        if unknown:
            msg += f", nicht erkannt: {len(unknown)} Zeile(n)"
        self.statusBar().showMessage(msg, 8000)

    def copy_recipe(self):
        if self.current:
            QApplication.clipboard().setText(recipe.to_text(self.settings[self.current]))
            self.statusBar().showMessage("Rezept in die Zwischenablage kopiert", 5000)

    def set_before(self, on):
        self.show_before = on
        self.request_render(False)

    def reset_current(self):
        if self.current:
            self.settings[self.current] = app_defaults()
            self.refresh_controls(self.settings[self.current])
            self.request_render(False)

    # ---- LUT / Presets
    def load_lut(self):
        if not self.current:
            return
        f, _ = QFileDialog.getOpenFileName(self, "3D-LUT", "", "Cube LUT (*.cube)")
        if f:
            try:
                from .render import get_lut
                get_lut(f)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "LUT", str(exc))
                return
            self.settings[self.current].lut_path = f
            self.lut_label.setText(Path(f).name)
            self.request_render(False)

    def clear_lut(self):
        if self.current:
            self.settings[self.current].lut_path = ""
            self.lut_label.setText("keine")
            self.request_render(False)

    # ---- Presets (speichern / ueberschreiben / loeschen)
    def refresh_presets(self, select: str | None = None):
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem("– Preset wählen –")
        for name in presets.list_presets():
            self.preset_box.addItem(name)
            try:
                meta = presets.load(name)
                tip = "\n".join(x for x in (meta.get("note", ""), meta.get("source", "")) if x)
            except Exception:  # noqa: BLE001
                tip = ""
            self.preset_box.setItemData(self.preset_box.count() - 1, tip, Qt.ToolTipRole)
        if select:
            i = self.preset_box.findText(select, Qt.MatchFixedString)
            self.preset_box.setCurrentIndex(max(i, 0))
        self.preset_box.blockSignals(False)

    def _selected_preset(self):
        i = self.preset_box.currentIndex()
        return self.preset_box.itemText(i) if i > 0 else None

    def on_preset_chosen(self, idx):
        if idx <= 0 or not self.current:
            return
        name = self.preset_box.itemText(idx)
        try:
            new = presets.apply_preset(self.settings[self.current], presets.load(name))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Preset", f"„{name}“ konnte nicht geladen werden: {exc}")
            return
        self.settings[self.current] = new
        self.refresh_controls(new)
        self.request_render(False)
        self.statusBar().showMessage(f"Preset „{name}“ angewendet (Belichtung bleibt). "
                                     f"„Apply to all“ überträgt es auf alle Bilder.", 8000)

    def save_preset_as(self):
        if not self.current:
            return
        name, ok = QInputDialog.getText(self, "Preset speichern", "Name des Presets:",
                                        text=self._selected_preset() or "")
        name = name.strip()
        if not ok or not name:
            return
        overwrite = False
        if presets.exists(name):
            r = QMessageBox.question(self, "Preset überschreiben",
                                     f"Ein Preset „{name}“ existiert bereits. Überschreiben?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
            overwrite = True
        presets.save(name, self.settings[self.current], overwrite=overwrite)
        self.refresh_presets(name)
        self.statusBar().showMessage(f"Preset „{name}“ {'überschrieben' if overwrite else 'gespeichert'}", 6000)

    def overwrite_preset(self):
        name = self._selected_preset()
        if not self.current or not name:
            QMessageBox.information(self, "Preset", "Wähle zuerst ein Preset aus der Liste.")
            return
        r = QMessageBox.question(self, "Preset überschreiben",
                                 f"„{name}“ mit den aktuellen Einstellungen überschreiben?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            presets.save(name, self.settings[self.current], overwrite=True)
            self.refresh_presets(name)
            self.statusBar().showMessage(f"Preset „{name}“ überschrieben", 6000)

    def delete_preset(self):
        name = self._selected_preset()
        if not name:
            QMessageBox.information(self, "Preset", "Wähle zuerst ein Preset aus der Liste.")
            return
        r = QMessageBox.question(self, "Preset löschen", f"Preset „{name}“ endgültig löschen?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            presets.delete(name)
            self.refresh_presets()
            self.statusBar().showMessage(f"Preset „{name}“ gelöscht", 6000)

    # ---- Apply to all
    def apply_to_all(self):
        if not self.current:
            return
        src = self.settings[self.current]
        n = 0
        for path in self.settings:
            if path == self.current:
                continue
            new = src.copy()
            if self.keep_chk.isChecked():
                for k in PER_IMAGE_KEYS:
                    setattr(new, k, getattr(self.settings[path], k))
            self.settings[path] = new
            n += 1
        self.statusBar().showMessage(f"Einstellungen auf {n} weitere Bilder übertragen", 6000)

    # ---- Rendering
    # ---- Export
    def export(self, all_images: bool):
        if not self.current:
            return
        outdir = QFileDialog.getExistingDirectory(self, "Ausgabeordner")
        if not outdir:
            return
        paths = list(self.settings) if all_images else [self.current]
        jobs = [(p, self.settings[p].copy()) for p in paths]
        self.progress = QProgressDialog("Exportiere…", "Abbrechen", 0, len(jobs), self)
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setMinimumDuration(0)
        self.export_task = ExportTask(self, jobs, outdir, "jpg", 95, 0)
        self.progress.canceled.connect(lambda: setattr(self.export_task, "cancel", True))
        self.export_pool.start(self.export_task)

    def on_export_progress(self, i, name):
        if self.progress:
            self.progress.setValue(i)
            self.progress.setLabelText(f"{i + 1}: {name}")

    def on_export_done(self, n, errors):
        if self.progress:
            self.progress.setValue(self.progress.maximum())
        msg = f"{n} Bild(er) exportiert." + (("\n\nFehler:\n" + "\n".join(errors)) if errors else "")
        QMessageBox.information(self, "Export", msg)


def _shutdown(self):
    """Alle Hintergrund-Threads beenden, bevor Qt sie zerstoert (sonst Abbruch beim Schliessen)."""
    if getattr(self, "_down", False):
        return
    self._down = True
    for tw in getattr(self, "_thumb_refs", []):
        try:
            tw.requestInterruption()
        except RuntimeError:
            pass
    self.worker.stop()
    for tw in getattr(self, "_thumb_refs", []):
        try:
            if not tw.wait(1500):
                tw.terminate()
                tw.wait(1000)
        except RuntimeError:
            pass
    if self.export_task is not None:
        self.export_task.cancel = True
    self.export_pool.waitForDone(3000)


def _close(self, e):
    self.save_session()
    self.shutdown()
    e.accept()


MainWindow.shutdown = _shutdown
MainWindow.closeEvent = _close


def _setup_debug():
    """Diagnose (FUJISIM_DEBUG=/pfad/log): Thread-Stacktraces + UI-Stall-Messung."""
    import faulthandler
    _log = open(os.environ["FUJISIM_DEBUG"], "w")
    faulthandler.dump_traceback_later(6, repeat=True, file=_log)
    _last = [time.perf_counter()]

    def _beat():                         # UI-Thread-Stalls > 250 ms protokollieren
        now = time.perf_counter()
        if now - _last[0] > 0.25:
            _log.write(f"UI-STALL {1000 * (now - _last[0]):.0f} ms bei t={now:.1f}\n")
            _log.flush()
        _last[0] = now
    _hb = QTimer()
    _hb.timeout.connect(_beat)
    _hb.start(50)
    globals()["_hb"] = _hb


def main():
    app = QApplication(sys.argv)
    if os.environ.get("FUJISIM_DEBUG"):
        _setup_debug()
    presets.install_defaults()
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(40, 40, 40))
    pal.setColor(QPalette.WindowText, QColor(220, 220, 220))
    pal.setColor(QPalette.Base, QColor(28, 28, 28))
    pal.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    pal.setColor(QPalette.Text, QColor(220, 220, 220))
    pal.setColor(QPalette.Button, QColor(55, 55, 55))
    pal.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    pal.setColor(QPalette.Highlight, QColor(45, 108, 223))
    app.setPalette(pal)
    win = MainWindow()
    app.aboutToQuit.connect(win.shutdown)
    win.show()
    if len(sys.argv) > 1:
        win.add_paths(sys.argv[1:])
    else:
        win.restore_session()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
