"""PySide6-Editor: Filmstreifen, Vorschau, Regler, 'Apply to all', Export."""
from __future__ import annotations

import gc
import math
from dataclasses import asdict
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QPointF, QSettings, QObject, QRectF, QSize, QRunnable, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QConicalGradient, QCursor, QKeySequence, QPen, QPolygonF,
                           QRadialGradient, QShortcut, QColor, QIcon, QImage, QImageReader, QPainter, QPalette, QPixmap)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog,
    QInputDialog, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSplitter, QVBoxLayout, QWidget, QDialog,
    QDialogButtonBox, QGridLayout, QSpinBox,
)

from . import raw_io
from . import flog, geometry, grading, presets, recipe
from .engine import ImageSession, export_file, resize_zoom
from .film import FILMS
from .settings import (DR_CHOICES, EFFECT_CHOICES, GEOMETRY_KEYS, GRAIN_SIZES, MONO_FILTERS_LIST, PER_IMAGE_KEYS,
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
    ("Grundlagen", [
        ("saturation", "Sättigung", -100, 100, 1, 0),
        ("vibrance", "Dynamik (Vibrance)", -100, 100, 1, 0),
        ("whites", "Weiß", -100, 100, 1, 0),
        ("blacks", "Schwarz", -100, 100, 1, 0),
    ]),
    ("Color Grading: Mischung", [
        ("cg_blend", "Überblendung", 0, 100, 1, 0),
        ("cg_balance", "Balance (Schatten ↔ Lichter)", -100, 100, 1, 0),
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
    ("Geometrie: Zuschneiden && Drehen", [("angle", "Gerade ausrichten (°)", -450, 450, 10, 1)]),
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
    def __init__(self, win, jobs, outdir, fmt, quality, resize=None, no_upscale=True):
        super().__init__()
        self.win, self.jobs, self.outdir = win, jobs, outdir
        self.fmt, self.quality, self.resize, self.no_upscale = fmt, quality, resize, no_upscale
        self.cancel = False

    def run(self):
        errors = []
        for i, (path, s) in enumerate(self.jobs):
            if self.cancel:
                break
            self.win.sig.export_progress.emit(i, os.path.basename(path))
            dst = Path(self.outdir) / f"{Path(path).stem}_{s.sim.replace(' ', '').replace('.', '')}.{self.fmt}"
            try:
                export_file(path, s, str(dst), self.quality, resize=self.resize, no_upscale=self.no_upscale)
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
    cropChanged = Signal(object)      # (x, y, w, h) normiert auf die Arbeitsflaeche
    cropDone = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.crop_mode = False
        self.crop_rect = (0.0, 0.0, 1.0, 1.0)
        self.crop_ratio = 0.0         # Breite/Hoehe, 0 = frei
        self.crop_ok = None           # Pruefung (rect) -> bool, z. B. "liegt im gedrehten Bild"
        self._cdrag = None
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
        if self.crop_mode:
            self._paint_crop(p)

    # -- Zuschneiden: Overlay + Bedienung
    def _wrect(self):
        """Zuschnitt in Widget-Koordinaten (x0, y0, x1, y1)."""
        z, left, top, _, _ = self.vrect()
        r = self.devicePixelRatioF()
        x, y, w, h = self.crop_rect
        f = lambda X, Y: ((X - left) * z / r, (Y - top) * z / r)  # noqa: E731
        a, b = f(x * self.W, y * self.H)
        c, d = f((x + w) * self.W, (y + h) * self.H)
        return a, b, c, d

    def _paint_crop(self, p):
        x0, y0, x1, y1 = self._wrect()
        W, Hh = self.width(), self.height()
        dim = QColor(0, 0, 0, 150)
        p.fillRect(QRectF(0, 0, W, max(0, y0)), dim)
        p.fillRect(QRectF(0, y1, W, max(0, Hh - y1)), dim)
        p.fillRect(QRectF(0, y0, max(0, x0), y1 - y0), dim)
        p.fillRect(QRectF(x1, y0, max(0, W - x1), y1 - y0), dim)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for k in (1, 2):
            p.drawLine(x0 + (x1 - x0) * k / 3, y0, x0 + (x1 - x0) * k / 3, y1)
            p.drawLine(x0, y0 + (y1 - y0) * k / 3, x1, y0 + (y1 - y0) * k / 3)
        p.setPen(QPen(QColor(30, 30, 30), 1))
        p.setBrush(QColor(255, 255, 255))
        for hx, hy in self._handles(x0, y0, x1, y1).values():
            p.drawRect(QRectF(hx - 4, hy - 4, 8, 8))

    @staticmethod
    def _handles(x0, y0, x1, y1):
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        return {"tl": (x0, y0), "t": (mx, y0), "tr": (x1, y0), "r": (x1, my),
                "br": (x1, y1), "b": (mx, y1), "bl": (x0, y1), "l": (x0, my)}

    def _hit(self, pos):
        x0, y0, x1, y1 = self._wrect()
        for name, (hx, hy) in self._handles(x0, y0, x1, y1).items():
            if abs(pos.x() - hx) <= 9 and abs(pos.y() - hy) <= 9:
                return name
        if x0 <= pos.x() <= x1 and y0 <= pos.y() <= y1:
            return "move"
        return None

    def _to_image(self, pos):
        z, left, top, _, _ = self.vrect()
        r = self.devicePixelRatioF()
        return left + pos.x() * r / z, top + pos.y() * r / z

    def _crop_press(self, e):
        hit = self._hit(e.position())
        if hit:
            X, Y = self._to_image(e.position())
            x, y, w, h = self.crop_rect
            self._cdrag = (hit, X, Y, (x * self.W, y * self.H, (x + w) * self.W, (y + h) * self.H))

    def _crop_move(self, e):
        W, H = float(self.W), float(self.H)
        if not self._cdrag:
            cur = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                   "bl": Qt.SizeBDiagCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                   "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor, "move": Qt.SizeAllCursor}.get(self._hit(e.position()))
            self.setCursor(QCursor(cur) if cur else QCursor(Qt.ArrowCursor))
            return
        hit, X0, Y0, (a, b, c, d) = self._cdrag
        X, Y = self._to_image(e.position())
        dx, dy = X - X0, Y - Y0
        ratio = self.crop_ratio
        MIN = 24.0
        if hit == "move":
            w, h = c - a, d - b
            na = min(max(a + dx, 0.0), W - w)
            nb = min(max(b + dy, 0.0), H - h)
            cand = (na, nb, na + w, nb + h)
        else:
            if "l" in hit:
                a = min(a + dx, c - MIN)
            if "r" in hit:
                c = max(c + dx, a + MIN)
            if "t" in hit:
                b = min(b + dy, d - MIN)
            if "b" in hit:
                d = max(d + dy, b + MIN)
            if ratio > 0:
                w, h = c - a, d - b
                if len(hit) == 2:                          # Ecke: gegenueberliegende Ecke bleibt
                    if w / h > ratio:
                        w = h * ratio
                    else:
                        h = w / ratio
                    if "l" in hit:
                        a = c - w
                    else:
                        c = a + w
                    if "t" in hit:
                        b = d - h
                    else:
                        d = b + h
                elif hit in ("l", "r"):                  # Kante: Hoehe folgt, um die Mitte
                    h = w / ratio
                    my = (b + d) / 2
                    b, d = my - h / 2, my + h / 2
                else:
                    w = h * ratio
                    mx = (a + c) / 2
                    a, c = mx - w / 2, mx + w / 2
            cand = (a, b, c, d)
        if cand[0] < -1e-6 or cand[1] < -1e-6 or cand[2] > W + 1e-6 or cand[3] > H + 1e-6:
            return
        rect = (cand[0] / W, cand[1] / H, (cand[2] - cand[0]) / W, (cand[3] - cand[1]) / H)
        if self.crop_ok is not None and not self.crop_ok(rect):
            return
        self.crop_rect = rect
        self.cropChanged.emit(rect)
        self.update()

    # -- Interaktion
    def _changed(self):
        self.update()
        self.viewChanged.emit()

    def wheelEvent(self, e):
        if not self.W or self.crop_mode:
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
        if self.crop_mode and self.W:
            if e.button() == Qt.LeftButton:
                self._crop_press(e)
            return
        if e.button() == Qt.LeftButton and self.W:
            self.drag = (e.position(), self.cx, self.cy)

    def mouseMoveEvent(self, e):
        if self.crop_mode and self.W:
            self._crop_move(e)
            return
        if self.drag and self.W and not self.fit:
            r = self.devicePixelRatioF()
            p0, cx0, cy0 = self.drag
            z = self.eff_zoom()
            self.cx = cx0 - (e.position().x() - p0.x()) * r / z
            self.cy = cy0 - (e.position().y() - p0.y()) * r / z
            self._changed()

    def mouseReleaseEvent(self, e):
        self.drag = None
        self._cdrag = None

    def mouseDoubleClickEvent(self, e):
        if not self.W:
            return
        if self.crop_mode:
            self.cropDone.emit()
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
        if self.crop_mode and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.cropDone.emit()
        elif e.key() == Qt.Key_0:
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

# ---------------------------------------------------------------- Graphen: Histogramm, Farbrad, Tonkurve
class HistogramWidget(QWidget):
    """RGB- + Luma-Histogramm des gerade angezeigten Bildes, mit Hinweis auf abgeschnittene Tiefen/Lichter."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(96)
        self.bins = None            # (4, 256): R, G, B, Luma
        self.clip = (0.0, 0.0)

    def set_image(self, arr: np.ndarray):
        a = arr[::3, ::3].reshape(-1, 3)
        luma = (a @ np.array([0.2126, 0.7152, 0.0722], np.float32)).astype(np.uint8)
        h = [np.bincount(a[:, c], minlength=256)[:256] for c in range(3)] + [np.bincount(luma, minlength=256)[:256]]
        self.bins = np.array(h, np.float32)
        n = max(1, a.shape[0])
        self.clip = (float((a.min(1) == 0).sum() / n), float((a.max(1) == 255).sum() / n))
        self.update()

    def luma_bins(self):
        return None if self.bins is None else self.bins[3]

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect().adjusted(0, 0, -1, -1)
        p.fillRect(r, QColor(28, 28, 28))
        p.setPen(QColor(60, 60, 60))
        for k in range(1, 4):
            p.drawLine(r.width() * k // 4, 0, r.width() * k // 4, r.height())
        if self.bins is None:
            return
        top = float(np.percentile(self.bins[:3], 99.5)) or 1.0
        W, H = r.width(), r.height() - 2
        xs = np.linspace(0, W, 256)
        cols = [QColor(255, 60, 60, 120), QColor(60, 220, 60, 120), QColor(70, 110, 255, 120), QColor(210, 210, 210, 70)]
        p.setPen(Qt.NoPen)
        for c in (3, 0, 1, 2):
            poly = QPolygonF([QPointF(0, H + 1)] + [QPointF(xs[i], H + 1 - min(1.0, self.bins[c][i] / top) * H) for i in range(256)]
                             + [QPointF(W, H + 1)])
            p.setBrush(cols[c])
            p.drawPolygon(poly)
        if self.clip[0] > 0.005:
            p.setBrush(QColor(80, 140, 255))
            p.drawPolygon(QPolygonF([QPointF(2, 2), QPointF(12, 2), QPointF(2, 12)]))
        if self.clip[1] > 0.005:
            p.setBrush(QColor(255, 120, 80))
            p.drawPolygon(QPolygonF([QPointF(W - 2, 2), QPointF(W - 12, 2), QPointF(W - 2, 12)]))


class ColorWheel(QWidget):
    """Farbrad: Position = Farbton (Winkel) und Saettigung (Abstand). Doppelklick setzt zurueck."""
    changed = Signal(float, float)          # Farbton (Grad), Saettigung 0..100

    def __init__(self, size=132):
        super().__init__()
        self.setFixedSize(size, size)
        self.hue = 0.0
        self.sat = 0.0
        self._bg = None

    def set_value(self, hue: float, sat: float):
        self.hue, self.sat = hue % 360.0, min(max(sat, 0.0), 100.0)
        self.update()

    def _geom(self):
        c = QPointF(self.width() / 2, self.height() / 2)
        return c, min(self.width(), self.height()) / 2 - 5

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, R = self._geom()
        cg = QConicalGradient(c, 0)
        for k in range(13):
            cg.setColorAt(k / 12.0, QColor.fromHsvF((k % 12) / 12.0, 1.0, 1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(c, R, R)
        rg = QRadialGradient(c, R)
        rg.setColorAt(0.0, QColor(128, 128, 128, 255))
        rg.setColorAt(1.0, QColor(128, 128, 128, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(c, R, R)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(20, 20, 20), 1.5))
        p.drawEllipse(c, R, R)
        a = math.radians(self.hue)
        d = R * self.sat / 100.0
        pt = QPointF(c.x() + d * math.cos(a), c.y() - d * math.sin(a))
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(QColor(0, 0, 0, 60) if self.sat > 0 else QColor(255, 255, 255, 60))
        p.drawEllipse(pt, 6, 6)

    def _set_from(self, pos):
        c, R = self._geom()
        dx, dy = pos.x() - c.x(), -(pos.y() - c.y())
        sat = min(1.0, math.hypot(dx, dy) / R) * 100.0
        hue = math.degrees(math.atan2(dy, dx)) % 360.0 if sat > 0.5 else self.hue
        self.hue, self.sat = hue, sat
        self.update()
        self.changed.emit(self.hue, self.sat)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._set_from(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._set_from(e.position())

    def mouseDoubleClickEvent(self, e):
        self.hue, self.sat = self.hue, 0.0
        self.update()
        self.changed.emit(self.hue, 0.0)


class CurveEditor(QWidget):
    """Tonkurve: Punkte setzen (Klick), ziehen, entfernen (Doppelklick/Rechtsklick). Kanal: RGB, Rot, Gruen, Blau."""
    changed = Signal(str, object)           # Schluessel ('curve', 'curve_r', ...), Punkteliste

    KEYS = {"RGB": ("curve", QColor(235, 235, 235)), "Rot": ("curve_r", QColor(255, 90, 90)),
            "Grün": ("curve_g", QColor(90, 220, 90)), "Blau": ("curve_b", QColor(100, 140, 255))}

    def __init__(self, hist=None):
        super().__init__()
        self.setFixedSize(300, 300)
        self.hist = hist
        self.channel = "RGB"
        self.curves = {k: [[0.0, 0.0], [1.0, 1.0]] for k, _ in self.KEYS.values()}
        self.drag = None

    def set_curves(self, s):
        self.curves = {k: [list(p) for p in getattr(s, k)] for k, _ in self.KEYS.values()}
        self.update()

    def set_channel(self, name):
        self.channel = name
        self.update()

    @property
    def pts(self):
        return self.curves[self.KEYS[self.channel][0]]

    def _m(self):
        return 10

    def _to_w(self, x, y):
        m = self._m()
        return m + x * (self.width() - 2 * m), self.height() - m - y * (self.height() - 2 * m)

    def _to_n(self, px, py):
        m = self._m()
        return (px - m) / (self.width() - 2 * m), (self.height() - m - py) / (self.height() - 2 * m)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(28, 28, 28))
        x0, y1 = self._to_w(0, 0)
        x1, y0 = self._to_w(1, 1)
        hb = self.hist.luma_bins() if self.hist is not None else None
        if hb is not None:
            top = float(np.percentile(hb, 99.5)) or 1.0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 28))
            poly = QPolygonF([QPointF(x0, y1)] + [QPointF(x0 + (x1 - x0) * i / 255, y1 - min(1.0, hb[i] / top) * (y1 - y0))
                                                 for i in range(256)] + [QPointF(x1, y1)])
            p.drawPolygon(poly)
        p.setPen(QPen(QColor(65, 65, 65), 1))
        for k in range(5):
            p.drawLine(x0 + (x1 - x0) * k / 4, y0, x0 + (x1 - x0) * k / 4, y1)
            p.drawLine(x0, y0 + (y1 - y0) * k / 4, x1, y0 + (y1 - y0) * k / 4)
        p.setPen(QPen(QColor(90, 90, 90), 1, Qt.DashLine))
        p.drawLine(x0, y1, x1, y0)
        for name, (key, col) in self.KEYS.items():
            if name != self.channel and not grading.curve_is_identity(self.curves[key]):
                self._draw_curve(p, self.curves[key], QColor(col.red(), col.green(), col.blue(), 90), 1.2)
        col = self.KEYS[self.channel][1]
        self._draw_curve(p, self.pts, col, 2.0)
        p.setPen(QPen(QColor(20, 20, 20), 1))
        p.setBrush(col)
        for x, y in self.pts:
            wx, wy = self._to_w(x, y)
            p.drawEllipse(QPointF(wx, wy), 5, 5)

    def _draw_curve(self, p, pts, col, width):
        lut = grading.curve_lut(pts, 256)
        p.setPen(QPen(col, width))
        p.setBrush(Qt.NoBrush)
        last = None
        for i in range(256):
            w = QPointF(*self._to_w(i / 255.0, float(lut[i])))
            if last is not None:
                p.drawLine(last, w)
            last = w

    def _nearest(self, pos, tol=9):
        best, bi = tol, None
        for i, (x, y) in enumerate(self.pts):
            wx, wy = self._to_w(x, y)
            d = math.hypot(pos.x() - wx, pos.y() - wy)
            if d < best:
                best, bi = d, i
        return bi

    def _emit(self):
        self.changed.emit(self.KEYS[self.channel][0], [list(p) for p in self.pts])
        self.update()

    def mousePressEvent(self, e):
        i = self._nearest(e.position())
        if e.button() == Qt.RightButton:
            if i is not None and len(self.pts) > 2:
                del self.pts[i]
                self._emit()
            return
        if i is None:
            x, y = self._to_n(e.position().x(), e.position().y())
            x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
            if any(abs(px - x) < 0.02 for px, _ in self.pts):
                return
            self.pts.append([x, y])
            self.pts.sort()
            i = self.pts.index([x, y])
            self._emit()
        self.drag = i

    def mouseMoveEvent(self, e):
        if self.drag is None:
            return
        x, y = self._to_n(e.position().x(), e.position().y())
        y = min(max(y, 0.0), 1.0)
        i, pts = self.drag, self.pts
        lo = pts[i - 1][0] + 0.01 if i > 0 else 0.0
        hi = pts[i + 1][0] - 0.01 if i < len(pts) - 1 else 1.0
        if i == 0:
            x = min(max(x, 0.0), hi)
        elif i == len(pts) - 1:
            x = min(max(x, lo), 1.0)
        else:
            x = min(max(x, lo), hi)
        pts[i] = [x, y]
        self._emit()

    def mouseReleaseEvent(self, e):
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        i = self._nearest(e.position())
        if i is not None and len(self.pts) > 2:
            del self.pts[i]
            self._emit()


class ExportDialog(QDialog):
    """Format, Qualitaet und Groesse (Resize) fuer den Export."""
    MODES = [("Originalgröße", None), ("Lange Kante (px)", "long"), ("Kurze Kante (px)", "short"),
             ("Breite (px)", "width"), ("Höhe (px)", "height"), ("Prozent", "percent"), ("In Rahmen B × H (px)", "fit")]

    def __init__(self, parent, qs, size):
        super().__init__(parent)
        self.setWindowTitle("Exportieren")
        self.size_px = size
        form = QFormLayout(self)
        self.fmt = QComboBox()
        self.fmt.addItems(["JPEG", "PNG", "TIFF"])
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.mode = QComboBox()
        self.mode.addItems([m[0] for m in self.MODES])
        self.v1, self.v2 = QSpinBox(), QSpinBox()
        for sp in (self.v1, self.v2):
            sp.setRange(1, 100000)
        self.noup = QCheckBox("Nicht vergrößern")
        self.info = QLabel("")
        self.info.setStyleSheet("color:#999")
        row = QHBoxLayout()
        row.addWidget(self.v1)
        row.addWidget(QLabel("×"))
        row.addWidget(self.v2)
        form.addRow("Format", self.fmt)
        form.addRow("JPEG-Qualität", self.quality)
        form.addRow("Größe", self.mode)
        form.addRow("Wert", row)
        form.addRow(self.noup)
        form.addRow(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        try:
            self.fmt.setCurrentText(qs.value("exp_fmt", "JPEG"))
            self.quality.setValue(int(qs.value("exp_q", 95)))
            self.mode.setCurrentIndex(int(qs.value("exp_mode", 0)))
            self.v1.setValue(int(qs.value("exp_v1", 2048)))
            self.v2.setValue(int(qs.value("exp_v2", 2048)))
            self.noup.setChecked(str(qs.value("exp_noup", "true")).lower() == "true")
        except Exception:  # noqa: BLE001
            self.quality.setValue(95)
            self.noup.setChecked(True)
        self._qs = qs
        for w in (self.mode, self.v1, self.v2, self.noup):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged if isinstance(w, QSpinBox)
             else w.toggled).connect(self._update)
        self.fmt.currentTextChanged.connect(lambda t: self.quality.setEnabled(t == "JPEG"))
        self.quality.setEnabled(self.fmt.currentText() == "JPEG")
        self._update()

    def options(self):
        kind = self.MODES[self.mode.currentIndex()][1]
        resize = None if kind is None else (("fit", self.v1.value(), self.v2.value()) if kind == "fit"
                                            else (kind, self.v1.value()))
        return dict(fmt={"JPEG": "jpg", "PNG": "png", "TIFF": "tif"}[self.fmt.currentText()],
                    quality=self.quality.value(), resize=resize, no_upscale=self.noup.isChecked())

    def _update(self, *_):
        kind = self.MODES[self.mode.currentIndex()][1]
        self.v1.setEnabled(kind is not None)
        self.v2.setVisible(kind == "fit")
        ow, oh = self.size_px
        if ow:
            z = resize_zoom(ow, oh, self.options()["resize"])
            if self.noup.isChecked() and z > 1:
                z = 1.0
            self.info.setText(f"Aktuelles Bild: {ow} × {oh} px  →  {max(1, round(ow * z))} × {max(1, round(oh * z))} px")

    def accept(self):
        try:
            self._qs.setValue("exp_fmt", self.fmt.currentText())
            self._qs.setValue("exp_q", self.quality.value())
            self._qs.setValue("exp_mode", self.mode.currentIndex())
            self._qs.setValue("exp_v1", self.v1.value())
            self._qs.setValue("exp_v2", self.v2.value())
            self._qs.setValue("exp_noup", self.noup.isChecked())
        except Exception:  # noqa: BLE001
            pass
        super().accept()


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
        rs = QShortcut(QKeySequence(Qt.Key_R), self)
        rs.setContext(Qt.WindowShortcut)
        rs.activated.connect(lambda: self.crop_btn.setChecked(not self.crop_btn.isChecked()) if self.current else None)

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
        self.view.cropChanged.connect(self.on_view_crop)
        self.view.cropDone.connect(lambda: self.toggle_crop(False))
        self.crop_mode = False

        panel = QWidget()
        pl = QVBoxLayout(panel)
        self.hist = HistogramWidget()

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

        self.sliders: dict[str, tuple[QSlider, QLabel, float, int]] = {}
        # Color Grading (3 Farbraeder + Global)
        gcg = QGroupBox("Color Grading")
        grid = QGridLayout(gcg)
        self.wheels: dict[str, ColorWheel] = {}
        for n, (pre, title) in enumerate((("cg_sh", "Schatten"), ("cg_mid", "Mitten"), ("cg_hi", "Lichter"), ("cg_gl", "Global"))):
            cell = QVBoxLayout()
            lab = QLabel(title)
            lab.setAlignment(Qt.AlignCenter)
            wheel = ColorWheel()
            wheel.changed.connect(lambda h, sat, pre=pre: self.on_wheel(pre, h, sat))
            self.wheels[pre] = wheel
            sl = ResetSlider(0)
            sl.setRange(-100, 100)
            sl.setValue(0)
            val = QLabel("0")
            val.setFixedWidth(30)
            val.setAlignment(Qt.AlignRight)
            key = f"{pre}_l"
            sl.valueChanged.connect(lambda v, k=key: self.on_slider(k, v))
            self.sliders[key] = (sl, val, 1, 0)
            srow = QHBoxLayout()
            srow.addWidget(QLabel("Lum"))
            srow.addWidget(sl, 1)
            srow.addWidget(val)
            cell.addWidget(lab)
            cell.addWidget(wheel, 0, Qt.AlignHCenter)
            cell.addLayout(srow)
            grid.addLayout(cell, n // 2, n % 2)
        pl.addWidget(gcg)

        # Tonkurve
        gcv = QGroupBox("Tonkurve")
        cvl = QVBoxLayout(gcv)
        self.curve_ed = CurveEditor(self.hist)
        self.curve_ed.changed.connect(self.on_curve)
        crow = QHBoxLayout()
        self.curve_box = QComboBox()
        self.curve_box.addItems(list(CurveEditor.KEYS))
        self.curve_box.currentTextChanged.connect(self.curve_ed.set_channel)
        creset = QPushButton("Kurve zurücksetzen")
        creset.clicked.connect(self.reset_curves)
        crow.addWidget(self.curve_box, 1)
        crow.addWidget(creset)
        cvl.addLayout(crow)
        cvl.addWidget(self.curve_ed, 0, Qt.AlignHCenter)
        cvl.addWidget(QLabel("Klick = Punkt setzen · ziehen = verschieben · Rechtsklick/Doppelklick = Punkt löschen"))
        cvl.itemAt(2).widget().setStyleSheet("color:#999; font-size:10px")
        cvl.itemAt(2).widget().setWordWrap(True)
        pl.addWidget(gcv)

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

        defaults = EditSettings()
        for title, items in SLIDER_GROUPS:
            box = QGroupBox(title)
            form = QFormLayout(box)
            if title.startswith("Belichtung"):
                self.auto_chk = QCheckBox("Kamera-Belichtung (fest, wie die Kamera)")
                self.auto_chk.toggled.connect(lambda v: self.set_value("auto_exposure", v))
                form.addRow(self.auto_chk)
            if title.startswith("Geometrie"):
                self.crop_btn = QPushButton("Zuschneiden (R)")
                self.crop_btn.setCheckable(True)
                self.crop_btn.toggled.connect(self.toggle_crop)
                self.aspect_box = QComboBox()
                self.aspect_box.addItems(list(geometry.ASPECTS))
                self.aspect_box.currentTextChanged.connect(self.on_aspect)
                swap = QPushButton("⇄")
                swap.setToolTip("Hoch-/Querformat tauschen")
                swap.setFixedWidth(34)
                swap.clicked.connect(self.swap_aspect)
                arow = QHBoxLayout()
                arow.addWidget(self.aspect_box, 1)
                arow.addWidget(swap)
                form.addRow(self.crop_btn)
                form.addRow("Seitenverhältnis", arow)
                grow = QHBoxLayout()
                for text, tip, fn in (("⟲ 90°", "90° gegen den Uhrzeigersinn", lambda: self.rotate90(-1)),
                                      ("⟳ 90°", "90° im Uhrzeigersinn", lambda: self.rotate90(1)),
                                      ("↔", "Horizontal spiegeln", lambda: self.flip("h")),
                                      ("↕", "Vertikal spiegeln", lambda: self.flip("v"))):
                    b = QPushButton(text)
                    b.setToolTip(tip)
                    b.clicked.connect(fn)
                    grow.addWidget(b)
                form.addRow(grow)
                rb = QPushButton("Zuschnitt && Drehung zurücksetzen")
                rb.clicked.connect(self.reset_geometry)
                form.addRow(rb)
                self.geo_widgets = [self.crop_btn, self.aspect_box, swap, rb]
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
        right = QWidget()
        right.setFixedWidth(400)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        rl.addWidget(self.hist)
        rl.addWidget(scroll, 1)

        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.addWidget(right)
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
    def _saved_edits(self) -> dict:
        if not hasattr(self, "_saved"):
            try:
                self._saved = json.loads(self.qs.value("edits", "{}"))
            except Exception:  # noqa: BLE001
                self._saved = {}
        return self._saved

    def save_edits(self):
        """Bearbeitungen aller geladenen Bilder merken (Bilder ausserhalb der Liste bleiben erhalten)."""
        try:
            saved = self._saved_edits()
            base = asdict(app_defaults())
            for path, s in self.settings.items():
                d = asdict(s)
                if d == base:
                    saved.pop(path, None)
                else:
                    saved[path] = d
            self.qs.setValue("edits", json.dumps(saved))
            self.qs.sync()
        except Exception:  # noqa: BLE001
            pass

    def save_session(self):
        self.save_edits()
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
                  *self.preset_btns, *self.combos.values(), *self.geo_widgets):
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
            d = self._saved_edits().get(sp)
            self.settings[sp] = (EditSettings.from_dict({**asdict(app_defaults()), **d})
                                 if d else app_defaults())
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
        self.save_edits()
        self.current = item.data(Qt.UserRole)
        if self.crop_mode:
            self.crop_mode = False
            self.crop_btn.blockSignals(True)
            self.crop_btn.setChecked(False)
            self.crop_btn.blockSignals(False)
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
        self.sync_view(True)
        self.request_render(False)

    def on_full_ready(self, serial):
        if serial != self.load_serial or self.session is None:
            return
        self.sync_view(False)
        self.request_render(False)

    # ---- Geometrie (Zuschneiden, Drehen, Spiegeln)
    def view_settings(self, s: EditSettings) -> EditSettings:
        """Im Zuschneiden-Modus wird die ganze (gedrehte) Arbeitsflaeche gezeigt, der Rahmen liegt als Overlay darueber."""
        if self.crop_mode:
            v = s.copy()
            v.crop_x = v.crop_y = 0.0
            v.crop_w = v.crop_h = 1.0
            return v
        return s

    def _ratio(self, s: EditSettings) -> float:
        name = s.crop_aspect
        if name == "Frei":
            return 0.0
        if name == "Original" and self.session is not None:
            cw, ch = geometry.canvas_size(s, self.session.W, self.session.H)
            return cw / ch
        return geometry.ASPECTS.get(name) or 0.0

    def sync_view(self, reset: bool):
        """Bildgroesse der Ansicht (Ergebnis bzw. Arbeitsflaeche), Zuschnitt-Overlay und Seitenverhaeltnis abgleichen."""
        if self.session is None or not self.current:
            return
        s = self.settings[self.current]
        sv = self.view_settings(s)
        ow, oh = geometry.out_size(sv, self.session.W, self.session.H)
        self.view.set_size(ow, oh, reset=reset)
        self.view.crop_mode = self.crop_mode
        self.view.crop_rect = (s.crop_x, s.crop_y, s.crop_w, s.crop_h)
        self.view.crop_ratio = self._ratio(s)
        W, H = self.session.W, self.session.H
        self.view.crop_ok = lambda r, s=s: geometry.inside_fraction(s, W, H, rect=r) >= 0.9999
        self.view.update()

    def toggle_crop(self, on: bool):
        if not self.current:
            return
        self.crop_mode = bool(on)
        if self.crop_btn.isChecked() != self.crop_mode:
            self.crop_btn.blockSignals(True)
            self.crop_btn.setChecked(self.crop_mode)
            self.crop_btn.blockSignals(False)
        if self.session is not None and not self.crop_mode:
            geometry.fit_crop(self.settings[self.current], self.session.W, self.session.H)
        self.sync_view(True)
        self.request_render(False)
        self.view.setFocus()
        self.statusBar().showMessage("Zuschneiden: Rahmen ziehen, Enter oder Doppelklick = fertig" if self.crop_mode
                                     else "Zuschnitt übernommen", 6000)

    def on_view_crop(self, rect):
        if self.current:
            s = self.settings[self.current]
            s.crop_x, s.crop_y, s.crop_w, s.crop_h = rect
            if self.session is not None:
                ow, oh = geometry.out_size(s, self.session.W, self.session.H)
                self.statusBar().showMessage(f"Zuschnitt {ow} × {oh} px")

    def on_aspect(self, name):
        if self.loading_ui or not self.current or self.session is None:
            return
        s = self.settings[self.current]
        s.crop_aspect = name
        ratio = self._ratio(s)
        if name == "Original":
            s.crop_x = s.crop_y = 0.0
            s.crop_w = s.crop_h = 1.0
            geometry.fit_crop(s, self.session.W, self.session.H)
        elif ratio > 0:
            geometry.aspect_crop(s, self.session.W, self.session.H, ratio)
        self.sync_view(not self.crop_mode)
        self.request_render(False)

    def swap_aspect(self):
        inv = {"4:5": "5:4", "5:4": "4:5", "3:2": "2:3", "2:3": "3:2", "16:9": "9:16", "9:16": "16:9",
               "4:3": "3:4", "3:4": "4:3"}
        name = self.aspect_box.currentText()
        if name in inv:
            self.aspect_box.setCurrentText(inv[name])       # loest on_aspect aus

    def rotate90(self, d: int):
        if not self.current:
            return
        s = self.settings[self.current]
        x, y, w, h = s.crop_x, s.crop_y, s.crop_w, s.crop_h
        if d > 0:       # im Uhrzeigersinn: Zuschnitt dreht mit
            s.crop_x, s.crop_y, s.crop_w, s.crop_h = 1 - y - h, x, h, w
        else:
            s.crop_x, s.crop_y, s.crop_w, s.crop_h = y, 1 - x - w, h, w
        s.rot90 = (s.rot90 + d) % 4
        self.sync_view(True)
        self.request_render(False)

    def flip(self, axis: str):
        """Spiegelt das *Ergebnis* (nicht die Quelle): bei ungerader 90°-Drehung vertauschen sich die Achsen."""
        if not self.current:
            return
        s = self.settings[self.current]
        odd = s.rot90 % 2 == 1
        if axis == "h":
            if odd:
                s.flip_v = not s.flip_v
            else:
                s.flip_h = not s.flip_h
            s.crop_x = 1 - s.crop_x - s.crop_w
        else:
            if odd:
                s.flip_h = not s.flip_h
            else:
                s.flip_v = not s.flip_v
            s.crop_y = 1 - s.crop_y - s.crop_h
        s.angle = -s.angle if s.angle else 0.0
        self.refresh_controls(s)
        self.sync_view(True)
        self.request_render(False)

    def reset_geometry(self):
        if not self.current:
            return
        s = self.settings[self.current]
        for k in GEOMETRY_KEYS:
            setattr(s, k, getattr(EditSettings(), k))
        self.refresh_controls(s)
        self.sync_view(True)
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
                             wb_mode=s.wb_mode, wb_kelvin=s.wb_kelvin,
                             **{k: getattr(s, k) for k in GEOMETRY_KEYS})
        s = self.view_settings(s)
        self.render_serial += 1
        self.worker.post_render(dict(load=self.load_serial, serial=self.render_serial, session=self.session,
                                     s=s, z=zr, X0=X0, Y0=Y0, cw=cw, ch=ch, meta=(zr, X0, Y0), q=q))

    def on_rendered(self, load, serial, arr, meta, secs):
        if load != self.load_serial or serial != self.render_serial:
            return                                # veraltetes Ergebnis verwerfen
        q = meta[0] / max(self.view.eff_zoom(), 1e-9)
        self.full_time = 0.6 * self.full_time + 0.4 * secs / max(q * q, 0.1)
        self.view.set_image(to_qimage(arr), meta)
        self.hist.set_image(arr)
        self.curve_ed.update()
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
        self.aspect_box.setCurrentText(s.crop_aspect)
        for pre, wheel in self.wheels.items():
            wheel.set_value(getattr(s, f"{pre}_h"), getattr(s, f"{pre}_s"))
        self.curve_ed.set_curves(s)
        self.update_note(s.sim)
        self.loading_ui = False

    def set_value(self, key, value):
        if self.loading_ui or not self.current:
            return
        setattr(self.settings[self.current], key, value)
        if key == "angle" and self.session is not None:
            geometry.fit_crop(self.settings[self.current], self.session.W, self.session.H)
            self.sync_view(False)
        self.request_render(True)

    def on_slider(self, key, raw):
        sl, val, scale, dec = self.sliders[key]
        v = raw / scale
        val.setText(f"{v:.{dec}f}")
        self.set_value(key, v)

    def on_wheel(self, pre, hue, sat):
        if self.loading_ui or not self.current:
            return
        s = self.settings[self.current]
        setattr(s, f"{pre}_h", float(hue))
        setattr(s, f"{pre}_s", float(sat))
        self.request_render(True)

    def on_curve(self, key, pts):
        if self.loading_ui or not self.current:
            return
        setattr(self.settings[self.current], key, [list(map(float, p)) for p in pts])
        self.request_render(True)

    def reset_curves(self):
        if not self.current:
            return
        s = self.settings[self.current]
        ident = EditSettings()
        for k in ("curve", "curve_r", "curve_g", "curve_b"):
            setattr(s, k, [list(p) for p in getattr(ident, k)])
        self.curve_ed.set_curves(s)
        self.request_render(False)

    def update_note(self, name):
        src = ("Offizielle Fuji-LUT" if name in flog.available_sims()
               else f"abgeleitet aus {flog.DERIVED[name]}-LUT + gelernte Korrektur" if name in flog.DERIVED
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
            old = self.settings[self.current]
            new = EditSettings()      # echte Defaults (alle Regler neutral), nicht die Startwerte neuer Bilder
            for k in GEOMETRY_KEYS:   # Zuschnitt/Drehung haben einen eigenen Zuruecksetzen-Knopf
                setattr(new, k, getattr(old, k))
            self.settings[self.current] = new
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
            for k in GEOMETRY_KEYS:                    # Zuschnitt/Drehung sind immer pro Bild
                setattr(new, k, getattr(self.settings[path], k))
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
        s0 = self.settings[self.current]
        size = (geometry.out_size(s0, self.session.W, self.session.H) if self.session is not None else (0, 0))
        dlg = ExportDialog(self, self.qs, size)
        if dlg.exec() != QDialog.Accepted:
            return
        opt = dlg.options()
        outdir = QFileDialog.getExistingDirectory(self, "Ausgabeordner")
        if not outdir:
            return
        paths = list(self.settings) if all_images else [self.current]
        jobs = [(p, self.settings[p].copy()) for p in paths]
        self.progress = QProgressDialog("Exportiere…", "Abbrechen", 0, len(jobs), self)
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setMinimumDuration(0)
        self.export_task = ExportTask(self, jobs, outdir, opt["fmt"], opt["quality"], opt["resize"], opt["no_upscale"])
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
