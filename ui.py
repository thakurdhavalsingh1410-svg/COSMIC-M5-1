from __future__ import annotations

import html
import json
import math
import os
import platform
import random
import sys
import threading
import time
from pathlib import Path
from experience.performance_manager import load_performance_config


def _perf() -> dict:
    try:
        return load_performance_config()
    except Exception:
        return {
            "mode": "performance",
            "local_background_ms": 120,
            "local_orb_ms": 50,
            "local_metrics_ms": 5000,
            "stars": 28,
            "particles": 6,
        }


try:
    import psutil
except ModuleNotFoundError:
    psutil = None

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"
TASKS_FILE = CONFIG_DIR / "ui_tasks.json"

_DEFAULT_W, _DEFAULT_H = 1360, 820
_MIN_W, _MIN_H = 1120, 680
_SIDEBAR_W = 126
_LEFT_W = 260
_RIGHT_W = 330

_OS = platform.system()


class C:
    BG = "#030712"
    BG2 = "#061126"
    PANEL = "#071426"
    PANEL2 = "#0b1d33"
    BORDER = "#123653"
    BORDER2 = "#176985"
    CYAN = "#00f0ff"
    CYAN2 = "#67e8f9"
    BLUE = "#2563eb"
    PURPLE = "#a855f7"
    VIOLET = "#7c3aed"
    GREEN = "#34d399"
    YELLOW = "#facc15"
    RED = "#fb7185"
    TEXT = "#e5faff"
    TEXT2 = "#b6c7d8"
    MUTED = "#6b8299"
    WHITE = "#ffffff"


def qcol(value: str, alpha: int = 255) -> QColor:
    color = QColor(value)
    color.setAlpha(alpha)
    return color


def _fmt_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


def _os_name() -> str:
    return {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(
        _OS, _OS
    )


def _default_tasks() -> list[dict[str, str]]:
    return [
        {"task": "Physics Study", "time": "10:00 AM"},
        {"task": "Project Work", "time": "01:30 PM"},
        {"task": "Gym", "time": "06:00 PM"},
        {"task": "Code Practice", "time": "08:30 PM"},
    ]


def _load_tasks() -> list[dict[str, str]]:
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        tasks = [
            {
                "task": str(item.get("task", "")).strip(),
                "time": str(item.get("time", "")).strip(),
            }
            for item in data
            if str(item.get("task", "")).strip()
        ]
        return tasks or _default_tasks()
    except Exception:
        return _default_tasks()


def _save_tasks(tasks: list[dict[str, str]]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TASKS_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    except Exception:
        pass


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    return QFont("Segoe UI", size, weight)


def _display_font(size: int, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont("Orbitron", size, weight)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 138)
    return font


def _add_glow(widget: QWidget, color: str = C.CYAN, blur: int = 34, alpha: int = 90):
    glow = QGraphicsDropShadowEffect(widget)
    glow.setBlurRadius(blur)
    glow.setOffset(0, 0)
    glow.setColor(qcol(color, alpha))
    widget.setGraphicsEffect(glow)


class _SysMetrics:
    def __init__(self):
        self.cpu = 0.0
        self.mem = 0.0
        self.net = 0.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters() if psutil else None
        self._last_t = time.time()
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()

    def _loop(self):
        if psutil is None:
            return
        while True:
            try:
                now = time.time()
                net = psutil.net_io_counters()
                dt = max(0.001, now - self._last_t)
                traffic = (
                    net.bytes_sent
                    - self._last_net.bytes_sent
                    + net.bytes_recv
                    - self._last_net.bytes_recv
                ) / dt
                with self._lock:
                    self.cpu = psutil.cpu_percent(interval=None)
                    self.mem = psutil.virtual_memory().percent
                    self.net = traffic / (1024 * 1024)
                self._last_net = net
                self._last_t = now
            except Exception:
                pass
            time.sleep(3.0)

    def snapshot(self) -> dict:
        with self._lock:
            return {"cpu": self.cpu, "mem": self.mem, "net": self.net}


_metrics = _SysMetrics()


class CosmicBackground(QWidget):
    def __init__(self):
        super().__init__()
        self.setAutoFillBackground(False)
        self._tick = 0
        perf = _perf()
        star_count = int(perf.get("stars", 28))
        particle_count = int(perf.get("particles", 6))
        background_ms = int(perf.get("local_background_ms", 120))
        perf = _perf()
        star_count = int(perf.get("stars", 28))
        particle_count = int(perf.get("particles", 6))
        background_ms = int(perf.get("local_background_ms", 120))
        random.seed(39)
        self._stars = [
            (
                random.random(),
                random.random(),
                random.uniform(0.8, 2.3),
                random.uniform(0.2, 1.0),
            )
            for _ in range(star_count)
        ]
        self._particles = [
            [
                random.random(),
                random.random(),
                random.uniform(-0.0009, 0.0008),
                random.uniform(-0.0005, 0.0009),
            ]
            for _ in range(particle_count)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(background_ms)

    def _step(self):
        self._tick += 1
        for particle in self._particles:
            particle[0] = (particle[0] + particle[2]) % 1.0
            particle[1] = (particle[1] + particle[3]) % 1.0
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, qcol("#020617"))
        bg.setColorAt(0.48, qcol("#050816"))
        bg.setColorAt(1.0, qcol("#09051a"))
        painter.fillRect(self.rect(), bg)

        for cx, cy, radius, color in [
            (w * 0.48, h * 0.36, min(w, h) * 0.54, C.BLUE),
            (w * 0.84, h * 0.25, min(w, h) * 0.42, C.PURPLE),
            (w * 0.16, h * 0.86, min(w, h) * 0.35, C.CYAN),
        ]:
            glow = QRadialGradient(QPointF(cx, cy), radius)
            glow.setColorAt(0, qcol(color, 70))
            glow.setColorAt(1, qcol(color, 0))
            painter.fillRect(self.rect(), QBrush(glow))

        painter.setPen(QPen(qcol(C.CYAN, 20), 1))
        grid = 84
        for x in range(0, w, grid):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, grid):
            painter.drawLine(0, y, w, y)

        for sx, sy, size, power in self._stars:
            alpha = int(80 + 120 * abs(math.sin(self._tick * 0.025 + sx * 9)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcol(C.CYAN2, int(alpha * power)))
            painter.drawEllipse(QPointF(sx * w, sy * h), size, size)

        painter.setPen(QPen(qcol(C.PURPLE, 125), 1.4))
        painter.setBrush(qcol(C.PURPLE, 130))
        for x, y, dx, dy in self._particles:
            px, py = x * w, y * h
            painter.drawLine(QPointF(px - dx * w * 28, py - dy * h * 28), QPointF(px, py))
            painter.drawEllipse(QPointF(px, py), 2.2, 2.2)


class GlassCard(QFrame):
    def __init__(self, glow: str = C.CYAN, parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")
        self.setStyleSheet(
            f"""
            QFrame#glassCard {{
                background-color: rgba(7, 20, 38, 188);
                border: 1px solid rgba(34, 211, 238, 76);
                border-radius: 24px;
            }}
            QFrame#glassCard:hover {{
                border: 1px solid rgba(103, 232, 249, 170);
                background-color: rgba(9, 28, 51, 208);
            }}
            QLabel {{
                background: transparent;
                color: {C.TEXT};
            }}
            """
        )
        _add_glow(self, glow, 32, 55)


class StatusRing(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(135, 135)
        self._value = 0
        self._label = "WAITING"

    def set_value(self, value: float, label: str):
        self._value = max(0, min(100, int(round(value))))
        self._label = str(label).upper()
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(9, 9, 117, 117)

        painter.setPen(QPen(qcol(C.BORDER, 210), 9))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        if self._value >= 80:
            ring_color = C.GREEN
        elif self._value >= 55:
            ring_color = C.YELLOW
        else:
            ring_color = C.RED

        painter.setPen(QPen(qcol(ring_color, 230), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 86 * 16, int(-360 * (self._value / 100)) * 16)

        inner = QRadialGradient(QPointF(67.5, 67.5), 68)
        inner.setColorAt(0.0, qcol(C.CYAN, 45))
        inner.setColorAt(0.72, qcol(C.BLUE, 25))
        inner.setColorAt(1.0, qcol(C.BG, 0))
        painter.setBrush(QBrush(inner))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(18, 18, 99, 99))

        painter.setPen(qcol(C.WHITE))
        painter.setFont(_font(26, QFont.Weight.Light))
        painter.drawText(QRectF(0, 36, 135, 38), Qt.AlignmentFlag.AlignCenter, f"{self._value}%")
        painter.setPen(qcol(ring_color, 210))
        painter.setFont(_font(8, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 74, 135, 22), Qt.AlignmentFlag.AlignCenter, self._label)


class OrbWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.state = "INITIALISING"
        self.speaking = False
        self.muted = False
        self._tick = 0
        self.setMinimumSize(450, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        perf = _perf()
        self._spoke_count = 16 if perf.get("mode") == "performance" else 24
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(int(perf.get("local_orb_ms", 50)))

    def _step(self):
        self._tick += 1
        self.update()

    def set_state(self, state: str):
        self.state = state
        self.speaking = state == "SPEAKING"
        self.update()

    def set_muted(self, muted: bool):
        self.muted = muted
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h * 0.44
        base = min(w, h) * 0.31
        pulse = 1.0 + 0.025 * math.sin(self._tick * 0.055)
        if self.speaking:
            pulse += 0.035 * math.sin(self._tick * 0.18)
        if self.muted:
            pulse = 0.98

        for idx, scale in enumerate([2.45, 2.0, 1.55]):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate((self._tick * (0.18 + idx * 0.05)) % 360)
            painter.setPen(QPen(qcol(C.CYAN if idx != 1 else C.PURPLE, 58), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-base * scale, -base * scale * 0.42, base * scale * 2, base * scale * 0.84))
            painter.restore()

        for radius, alpha in [(base * 1.35, 65), (base * 1.12, 95), (base * 0.9, 120)]:
            painter.setPen(QPen(qcol(C.CYAN if not self.muted else C.RED, alpha), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        r = base * pulse
        orb = QRadialGradient(QPointF(cx - r * 0.28, cy - r * 0.34), r * 1.5)
        orb.setColorAt(0.0, qcol(C.WHITE, 240))
        orb.setColorAt(0.12, qcol(C.CYAN2, 220))
        orb.setColorAt(0.35, qcol(C.BLUE, 220))
        orb.setColorAt(0.68, qcol(C.PURPLE, 190))
        orb.setColorAt(1.0, qcol("#050816", 245))
        painter.setPen(QPen(qcol(C.CYAN2, 210), 1.5))
        painter.setBrush(QBrush(orb))
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        painter.setPen(QPen(qcol(C.CYAN2, 170), 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - r * 0.55, cy - r * 0.55, r * 1.1, r * 1.1))

        iris_r = r * 0.34
        iris = QRadialGradient(QPointF(cx, cy), iris_r)
        iris.setColorAt(0.0, qcol(C.WHITE, 245))
        iris.setColorAt(0.18, qcol(C.CYAN, 240))
        iris.setColorAt(0.42, qcol(C.VIOLET, 225))
        iris.setColorAt(1.0, qcol(C.BG, 245))
        painter.setBrush(QBrush(iris))
        painter.setPen(QPen(qcol(C.CYAN, 230), 2))
        painter.drawEllipse(QRectF(cx - iris_r, cy - iris_r, iris_r * 2, iris_r * 2))

        painter.setBrush(qcol(C.WHITE, 235))
        painter.setPen(Qt.PenStyle.NoPen)
        core = iris_r * (0.22 + 0.04 * math.sin(self._tick * 0.12))
        painter.drawEllipse(QPointF(cx, cy), core, core)

        for i in range(self._spoke_count):
            angle = (i / max(1, self._spoke_count)) * math.tau + self._tick * 0.018
            inner = iris_r * 1.08
            outer = iris_r * (1.24 + 0.12 * math.sin(self._tick * 0.04 + i))
            painter.setPen(QPen(qcol(C.CYAN2 if i % 2 else C.PURPLE, 135), 1))
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
            )

        status = "MUTED" if self.muted else self.state
        painter.setPen(qcol(C.CYAN2 if not self.muted else C.RED, 175))
        painter.setFont(_font(9, QFont.Weight.Bold))
        painter.drawText(QRectF(0, h - 30, w, 22), Qt.AlignmentFlag.AlignCenter, status)



class LogWidget(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"""
            QTextEdit {{
                background: rgba(2, 6, 23, 130);
                color: {C.TEXT2};
                border: 1px solid rgba(34, 211, 238, 58);
                border-radius: 14px;
                padding: 8px;
            }}
            QScrollBar:vertical {{ width: 8px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER2}; border-radius: 4px; }}
            """
        )
        self.setFont(_font(9))

    def append_log(self, text: str):
        raw = str(text)
        lower = raw.lower()
        if lower.startswith("you:") or lower.startswith("web:"):
            color = C.CYAN2
        elif lower.startswith("cosmic:"):
            color = C.PURPLE
        elif lower.startswith("err:"):
            color = C.RED
        elif lower.startswith("file:"):
            color = C.GREEN
        else:
            color = C.MUTED
        self.append(f'<span style="color:{color};">{html.escape(raw)}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class FileDropCard(GlassCard):
    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__(C.CYAN)
        self.setAcceptDrops(True)
        self._current_file: str | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        self._title = QLabel("File Intake")
        self._title.setFont(_font(10, QFont.Weight.Bold))
        self._hint = QLabel("Drop or click to give COSMIC a file")
        self._hint.setFont(_font(8))
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {C.TEXT2};")
        layout.addWidget(self._title)
        layout.addWidget(self._hint)

    def current_file(self) -> str | None:
        return self._current_file

    def _select(self, path: str):
        self._current_file = path
        file_path = Path(path)
        size = _fmt_size(file_path.stat().st_size)
        self._hint.setText(f"{file_path.name} - {size}")
        self.file_selected.emit(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Select a file for COSMIC")
            if path:
                self._select(path)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            local = urls[0].toLocalFile()
            if local and Path(local).is_file():
                self._select(local)
                event.acceptProposedAction()


class SetupOverlay(QFrame):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("setupOverlay")
        self.setStyleSheet(
            f"""
            QFrame#setupOverlay {{
                background-color: rgba(3, 7, 18, 238);
                border: 1px solid {C.CYAN};
                border-radius: 28px;
            }}
            QLabel {{ color: {C.TEXT}; background: transparent; }}
            QLineEdit, QComboBox {{
                background: rgba(2, 6, 23, 210);
                color: {C.TEXT};
                border: 1px solid {C.BORDER2};
                border-radius: 12px;
                padding: 10px;
            }}
            QPushButton {{
                background: rgba(34, 211, 238, 45);
                color: {C.TEXT};
                border: 1px solid {C.CYAN};
                border-radius: 14px;
                padding: 12px;
            }}
            QPushButton:hover {{
                background: rgba(34, 211, 238, 85);
            }}
            """
        )
        _add_glow(self, C.CYAN, 45, 110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(14)
        title = QLabel("Configure COSMIC")
        title.setFont(_display_font(18))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Add your Gemini API key to activate the local assistant.")
        subtitle.setFont(_font(10))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        self._key = QLineEdit()
        self._key.setPlaceholderText("Gemini API key")
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._os = QComboBox()
        self._os.addItems(["Windows", "macOS", "Linux"])
        idx = {"Windows": 0, "Darwin": 1, "Linux": 2}.get(_OS, 0)
        self._os.setCurrentIndex(idx)
        save = QPushButton("Activate COSMIC")
        save.setFont(_font(10, QFont.Weight.Bold))
        save.clicked.connect(self._save)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(self._key)
        layout.addWidget(self._os)
        layout.addStretch()
        layout.addWidget(save)

    def _save(self):
        key = self._key.text().strip()
        if not key:
            self._key.setPlaceholderText("API key is required")
            return
        self.done.emit(key, self._os.currentText())


class SidebarButton(QPushButton):
    def __init__(self, label: str, active: bool = False):
        super().__init__(label)
        self._label = label
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(76)
        self.setFont(_font(9, QFont.Weight.Medium))
        self.set_active(active)

    def set_active(self, active: bool):
        color = C.CYAN2 if active else C.TEXT2
        background = "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(0, 240, 255, 55), stop:1 rgba(168, 85, 247, 70))" if active else "transparent"
        border = "rgba(34, 211, 238, 105)" if active else "rgba(34, 211, 238, 0)"
        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align: center;
                color: {color};
                background: {background};
                border: 1px solid {border};
                border-radius: 20px;
            }}
            QPushButton:hover {{
                color: {C.WHITE};
                background: rgba(34, 211, 238, 34);
                border: 1px solid rgba(34, 211, 238, 90);
            }}
            """
        )


class ActionCard(QPushButton):
    def __init__(self, title: str, detail: str, accent: str = C.CYAN):
        super().__init__(f"{title}\n{detail}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(108)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFont(_font(10, QFont.Weight.Bold))
        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                padding: 14px;
                color: {C.TEXT};
                background-color: rgba(7, 20, 38, 190);
                border: 1px solid {accent};
                border-radius: 24px;
            }}
            QPushButton:hover {{
                background-color: rgba(12, 31, 57, 222);
                border: 1px solid {C.CYAN2};
            }}
            """
        )
        _add_glow(self, accent, 28, 60)


class MainWindow(QMainWindow):
    _log_sig = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("COSMIC - Local AI Command Center")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            max(0, (screen.width() - _DEFAULT_W) // 2),
            max(0, (screen.height() - _DEFAULT_H) // 2),
        )

        self.on_text_command = None
        self._muted = False
        self._current_file: str | None = None
        self._log_history: list[str] = []
        self._log_history_start = 0
        self._log_history_lock = threading.Lock()
        self._state_value = "INITIALISING"
        self._overlay: SetupOverlay | None = None
        self._current_section = "Home"
        self._nav_buttons: dict[str, SidebarButton] = {}
        self._tasks = _load_tasks()
        self._status_value_labels: dict[str, QLabel] = {}

        central = CosmicBackground()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        main = QVBoxLayout()
        main.setContentsMargins(20, 14, 20, 18)
        main.setSpacing(14)
        root.addLayout(main, stretch=1)

        main.addWidget(self._build_header())

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnMinimumWidth(0, _LEFT_W)
        grid.setColumnMinimumWidth(2, _RIGHT_W)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)
        self._content_grid = grid
        self._left_widget = self._build_left_stack()
        self._center_widget = self._build_center_stack()
        self._right_widget = self._build_right_stack()
        self._actions_widget = self._build_action_row()
        grid.addWidget(self._left_widget, 0, 0)
        grid.addWidget(self._center_widget, 0, 1)
        grid.addWidget(self._right_widget, 0, 2)
        grid.addWidget(self._actions_widget, 1, 0, 1, 3)
        main.addLayout(grid, stretch=1)
        main.addWidget(self._build_command_bar())
        self._show_section("Home")

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()

        self._metric_timer = QTimer(self)
        self._metric_timer.timeout.connect(self._update_metrics)
        self._metric_timer.start(int(_perf().get("local_metrics_ms", 5000)))
        self._update_metrics()

        self._log_sig.connect(self._append_log)
        self._state_sig.connect(self._apply_state)

        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()
        else:
            self._apply_state("LISTENING")

        QShortcut(QKeySequence("F4"), self).activated.connect(self._toggle_mute)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._toggle_fullscreen)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setFixedWidth(_SIDEBAR_W)
        sidebar.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgba(2, 6, 23, 188);
                border-right: 1px solid rgba(34, 211, 238, 42);
            }}
            QLabel {{ background: transparent; color: {C.TEXT}; }}
            """
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(10)

        mark = QLabel("COSMIC")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFont(_display_font(11))
        mark.setStyleSheet(f"color: {C.CYAN};")
        layout.addWidget(mark)
        layout.addSpacing(10)

        for label in ["Home", "Memory", "Knowledge", "Tasks", "Calendar", "System"]:
            button = SidebarButton(label, active=label == "Home")
            button.clicked.connect(lambda checked=False, section=label: self._show_section(section))
            self._nav_buttons[label] = button
            layout.addWidget(button)

        layout.addStretch()
        core = GlassCard()
        core.setFixedHeight(104)
        core_lay = QVBoxLayout(core)
        core_lay.setContentsMargins(12, 12, 12, 12)
        core_lay.setSpacing(4)
        title = QLabel("COSMIC Core")
        title.setFont(_font(9, QFont.Weight.Bold))
        state = QLabel("Online")
        state.setFont(_font(9))
        state.setStyleSheet(f"color: {C.GREEN};")
        core_lay.addWidget(title)
        core_lay.addWidget(state)
        layout.addWidget(core)
        return sidebar

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(106)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        left = QLabel("LOCAL AI")
        left.setFont(_font(9, QFont.Weight.Bold))
        left.setStyleSheet(f"color: {C.MUTED};")
        layout.addWidget(left, stretch=1)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("COSMIC")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(_display_font(36, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.CYAN2};")
        subtitle = QLabel("Your Personal AI Command System")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setFont(_font(12))
        subtitle.setStyleSheet(f"color: {C.TEXT};")
        center.addWidget(title)
        center.addWidget(subtitle)
        layout.addLayout(center, stretch=2)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._clock_lbl = QLabel("00:00 PM")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._clock_lbl.setFont(_font(13, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.TEXT};")
        self._state_lbl = QLabel("INITIALISING")
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._state_lbl.setFont(_font(8, QFont.Weight.Bold))
        self._state_lbl.setStyleSheet(f"color: {C.CYAN};")
        right.addWidget(self._clock_lbl)
        right.addWidget(self._state_lbl)
        layout.addLayout(right, stretch=1)
        return header

    def _build_left_stack(self) -> QWidget:
        stack = QWidget()
        layout = QVBoxLayout(stack)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        status = GlassCard()
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(22, 20, 22, 20)
        status_layout.setSpacing(10)
        title = QLabel("SYSTEM STATUS")
        title.setFont(_font(10, QFont.Weight.Bold))
        status_layout.addWidget(title)
        self._status_ring = StatusRing()
        status_layout.addWidget(self._status_ring, alignment=Qt.AlignmentFlag.AlignCenter)

        for name, state, color in [
            ("Core Systems", "Online", C.GREEN),
            ("Memory Bank", "Stable", C.GREEN),
            ("Knowledge Graph", "Active", C.CYAN2),
            ("Learning Engine", "Active", C.PURPLE),
        ]:
            row = QHBoxLayout()
            left = QLabel(name)
            right = QLabel(state)
            left.setFont(_font(9))
            right.setFont(_font(9, QFont.Weight.Bold))
            right.setStyleSheet(f"color: {color};")
            row.addWidget(left)
            row.addStretch()
            row.addWidget(right)
            status_layout.addLayout(row)
        layout.addWidget(status, stretch=3)

        uptime = GlassCard(C.PURPLE)
        up_layout = QVBoxLayout(uptime)
        up_layout.setContentsMargins(22, 20, 22, 20)
        up_layout.setSpacing(8)
        up_title = QLabel("UPTIME / SYSTEM HEALTH")
        up_title.setFont(_font(10, QFont.Weight.Bold))
        wave = QLabel("∿∿∿∿∿∿∿∿∿∿∿∿∿∿∿")
        wave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wave.setFont(_font(18, QFont.Weight.Bold))
        wave.setStyleSheet(f"color: {C.CYAN2}; letter-spacing: 2px;")
        self._metric_lbl = QLabel("Oscilloscope live telemetry")
        self._metric_lbl.setFont(_font(8))
        self._metric_lbl.setStyleSheet(f"color: {C.MUTED};")

        for name in ["CPU Load", "Memory Use", "Network", "Processes"]:
            row = QHBoxLayout()
            left = QLabel(name)
            right = QLabel("--")
            left.setFont(_font(9))
            right.setFont(_font(9, QFont.Weight.Bold))
            right.setStyleSheet(f"color: {C.CYAN2};")
            self._status_value_labels[name] = right
            row.addWidget(left)
            row.addStretch()
            row.addWidget(right)
            up_layout.addLayout(row)

        self._uptime_lbl = QLabel("24:07:15")
        self._uptime_lbl.setFont(_font(23, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.CYAN};")
        self._system_note = QLabel("Measuring system load...")
        self._system_note.setFont(_font(9))
        self._system_note.setWordWrap(True)
        self._system_note.setStyleSheet(f"color: {C.TEXT2};")
        up_layout.addWidget(up_title)
        up_layout.addWidget(wave)
        up_layout.addWidget(self._metric_lbl)
        up_layout.addWidget(self._uptime_lbl)
        up_layout.addWidget(self._system_note)
        layout.addWidget(uptime, stretch=2)
        return stack

    def _build_center_stack(self) -> QWidget:
        stack = QWidget()
        layout = QVBoxLayout(stack)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.orb = OrbWidget()
        layout.addWidget(self.orb, stretch=1)

        dialogue = GlassCard(C.PURPLE)
        dialogue.setMaximumHeight(220)
        dialogue_layout = QVBoxLayout(dialogue)
        dialogue_layout.setContentsMargins(18, 14, 18, 14)
        dialogue_layout.setSpacing(7)
        title = QLabel("LIVE DIALOGUE")
        title.setFont(_font(10, QFont.Weight.Bold))
        user = QLabel('Dhaval: "Review my recent study patterns."')
        user.setFont(_font(9, QFont.Weight.Bold))
        user.setStyleSheet(f"color: {C.CYAN2};")
        ai = QLabel("COSMIC: I am tracking study focus, project context, and live commands here.")
        ai.setWordWrap(True)
        ai.setFont(_font(9))
        ai.setStyleSheet(f"color: {C.TEXT2};")
        self._log = LogWidget()
        self._log.setMinimumHeight(78)
        self._log.setMaximumHeight(118)
        wave = QLabel("▁▂▃▅▆▇▆▅▃▂▁  ▁▂▃▅▇▅▃▂▁")
        wave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wave.setFont(_font(12, QFont.Weight.Bold))
        wave.setStyleSheet(f"color: {C.CYAN};")
        dialogue_layout.addWidget(title)
        dialogue_layout.addWidget(user)
        dialogue_layout.addWidget(ai)
        dialogue_layout.addWidget(self._log)
        dialogue_layout.addWidget(wave)
        layout.addWidget(dialogue)
        return stack

    def _build_right_stack(self) -> QWidget:
        stack = QWidget()
        layout = QVBoxLayout(stack)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self._context_card = GlassCard(C.PURPLE)
        self._context_layout = QVBoxLayout(self._context_card)
        self._context_layout.setContentsMargins(22, 18, 22, 18)
        self._context_layout.setSpacing(10)
        layout.addWidget(self._context_card, stretch=5)

        schedule = GlassCard()
        schedule_layout = QVBoxLayout(schedule)
        schedule_layout.setContentsMargins(22, 18, 22, 18)
        schedule_layout.setSpacing(9)
        schedule_title = QLabel("TODAY'S SCHEDULE")
        schedule_title.setFont(_font(10, QFont.Weight.Bold))
        schedule_layout.addWidget(schedule_title)
        for task, status, color in [
            ("Physics Schedule", "In progress", C.CYAN),
            ("Project Work", "Linked", C.CYAN2),
            ("Gym", "Small", C.BLUE),
            ("Code Practice", "Resources", C.PURPLE),
        ]:
            row = QHBoxLayout()
            dot = QLabel("□")
            dot.setStyleSheet(f"color: {color};")
            name = QLabel(task)
            pill = QLabel(status)
            name.setFont(_font(9, QFont.Weight.Bold))
            pill.setFont(_font(8))
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(
                f"color: {C.CYAN2}; background: rgba(34, 211, 238, 30); "
                f"border: 1px solid rgba(34, 211, 238, 55); border-radius: 9px; padding: 3px 7px;"
            )
            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(pill)
            schedule_layout.addLayout(row)
        layout.addWidget(schedule, stretch=3)

        self._file_card = FileDropCard()
        self._file_card.file_selected.connect(self._on_file_selected)
        layout.addWidget(self._file_card, stretch=1)
        return stack

    def _build_action_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        for title, detail, accent in [
            ("Study Mode", "Focus, learn and understand deeply", C.CYAN),
            ("Brainstorm", "Generate ideas and solve problems", C.CYAN),
            ("Voice Command", "Speak your thoughts, I'll handle the rest", C.PURPLE),
            ("Tasks", "Organize, track and complete tasks", C.CYAN),
            ("System Control", "Manage settings and preferences", C.CYAN),
        ]:
            card = ActionCard(title, detail, accent)
            card.clicked.connect(lambda checked=False, name=title: self._handle_action(name))
            layout.addWidget(card)
        return row

    def _panel_label(self, text: str, size: int = 9, color: str = C.TEXT2, bold: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(_font(size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        label.setStyleSheet(f"color: {color};")
        return label

    def _apply_tab_layout(self, section: str):
        if not hasattr(self, "_content_grid"):
            return
        for widget in [
            self._left_widget,
            self._center_widget,
            self._right_widget,
            self._actions_widget,
        ]:
            self._content_grid.removeWidget(widget)

        self._left_widget.setVisible(False)
        self._center_widget.setVisible(False)
        self._right_widget.setVisible(False)
        self._actions_widget.setVisible(False)

        if section == "Home":
            # Launch screen: keep the AI runtime clean and uncluttered.
            self._center_widget.setVisible(True)
            self._content_grid.addWidget(self._center_widget, 0, 0, 2, 3)
            return

        if section == "System":
            self._left_widget.setVisible(True)
            self._right_widget.setVisible(True)
            self._content_grid.addWidget(self._left_widget, 0, 0)
            self._content_grid.addWidget(self._right_widget, 0, 1, 1, 2)
        elif section in {"Tasks", "Calendar"}:
            self._right_widget.setVisible(True)
            self._content_grid.addWidget(self._right_widget, 0, 0, 1, 3)
        else:
            self._center_widget.setVisible(True)
            self._right_widget.setVisible(True)
            self._content_grid.addWidget(self._center_widget, 0, 0, 1, 2)
            self._content_grid.addWidget(self._right_widget, 0, 2)

        # Keep quick-action cards off the Home screen, but still available in utility tabs.
        self._actions_widget.setVisible(True)
        self._content_grid.addWidget(self._actions_widget, 1, 0, 1, 3)


    def _show_section(self, section: str):
        self._current_section = section
        for name, button in self._nav_buttons.items():
            button.set_active(name == section)
        self._apply_tab_layout(section)

        if section == "Tasks":
            self._render_tasks_panel()
        elif section == "System":
            self._render_system_panel()
        elif section == "Memory":
            self._render_info_panel(
                "MEMORY",
                "Persistent context, preferences, and remembered project details.",
                [
                    "Ask COSMIC to remember facts, preferences, routines, or project notes.",
                    "Memory commands are handled by the assistant backend.",
                    "Example: remember that my physics exam is next Friday.",
                ],
            )
        elif section == "Knowledge":
            self._render_info_panel(
                "KNOWLEDGE",
                "Study mode, research, summaries, explanations, and learning support.",
                [
                    "Use Study Mode for focused learning sessions.",
                    "Drop a document into File Intake, then ask COSMIC to summarize or explain it.",
                    "Example: teach me this topic like I am preparing for an exam.",
                ],
            )
        elif section == "Calendar":
            self._render_info_panel(
                "CALENDAR",
                "Schedule planning lives here; today's editable schedule is under Tasks.",
                [
                    "Use the Tasks panel to edit today's visible schedule.",
                    "Ask COSMIC to create reminders or plan your week.",
                    "Future upgrade: calendar sync and real event import.",
                ],
            )
        else:
            self._render_info_panel(
                "ACTIVE CONTEXT AND GOALS",
                "Physics Lab Report 2 — progress 0 / 10.",
                [
                    "Physics Lab Reporting: organize observations and measurements.",
                    "Gantt refinement: split research, drafting, and final review.",
                    "Recents: study sessions and project notes are ready for Mark 5 memory.",
                    "Use the command bar for a Physics deep-dive or project details.",
                ],
            )

    def _render_info_panel(self, title: str, subtitle: str, lines: list[str]):
        _clear_layout(self._context_layout)
        self._context_layout.addWidget(self._panel_label(title, 10, C.TEXT, True))
        self._context_layout.addWidget(self._panel_label(subtitle, 9, C.TEXT2))
        for line in lines:
            self._context_layout.addWidget(self._panel_label(f"- {line}", 9, C.MUTED))
        self._context_layout.addStretch()

    def _render_tasks_panel(self):
        _clear_layout(self._context_layout)
        self._context_layout.addWidget(self._panel_label("ACTIVE CONTEXT AND GOALS", 10, C.TEXT, True))
        self._context_layout.addWidget(
            self._panel_label("Physics Lab Report 2 — progress 0 / 10.", 10, C.TEXT2)
        )
        for line in [
            "Physics Lab Reporting: organize observations and measurements.",
            "Draft findings and graphs.",
            "Gantt refinement and final review.",
        ]:
            self._context_layout.addWidget(self._panel_label(f"◎ {line}", 9, C.CYAN2))

        self._context_layout.addSpacing(8)
        self._context_layout.addWidget(self._panel_label("TODAY'S TASKS", 10, C.TEXT, True))

        colors = [C.CYAN, C.CYAN2, C.BLUE, C.PURPLE, C.GREEN]
        for index, item in enumerate(self._tasks):
            row = QHBoxLayout()
            dot = QLabel("□")
            dot.setStyleSheet(f"color: {colors[index % len(colors)]};")
            task = QLabel(item["task"])
            task.setFont(_font(9, QFont.Weight.Bold))
            time_lbl = QLabel(item.get("time", "--:--"))
            time_lbl.setFont(_font(9))
            time_lbl.setStyleSheet(f"color: {C.TEXT2};")
            remove = QPushButton("x")
            remove.setFixedSize(24, 24)
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.setStyleSheet(
                f"QPushButton {{ color: {C.RED}; background: transparent; border: 1px solid {C.BORDER}; border-radius: 12px; }}"
                f"QPushButton:hover {{ border-color: {C.RED}; }}"
            )
            remove.clicked.connect(lambda checked=False, i=index: self._remove_task(i))
            row.addWidget(dot)
            row.addWidget(task)
            row.addStretch()
            row.addWidget(time_lbl)
            row.addWidget(remove)
            self._context_layout.addLayout(row)

        input_row = QHBoxLayout()
        self._task_name_input = QLineEdit()
        self._task_name_input.setPlaceholderText("Task name")
        self._task_time_input = QLineEdit()
        self._task_time_input.setPlaceholderText("Time/status")
        add = QPushButton("Add")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self._add_task)
        for widget in [self._task_name_input, self._task_time_input]:
            widget.setFont(_font(9))
            widget.setStyleSheet(
                f"QLineEdit {{ color: {C.TEXT}; background: rgba(2, 6, 23, 160); border: 1px solid {C.BORDER}; border-radius: 10px; padding: 7px; }}"
                f"QLineEdit:focus {{ border-color: {C.CYAN}; }}"
            )
        add.setStyleSheet(
            f"QPushButton {{ color: {C.CYAN2}; background: rgba(34, 211, 238, 34); border: 1px solid {C.CYAN}; border-radius: 10px; padding: 7px 12px; }}"
            f"QPushButton:hover {{ background: rgba(34, 211, 238, 70); }}"
        )
        input_row.addWidget(self._task_name_input, stretch=2)
        input_row.addWidget(self._task_time_input, stretch=1)
        input_row.addWidget(add)
        self._context_layout.addLayout(input_row)
        self._context_layout.addStretch()


    def _render_system_panel(self):
        snap = _metrics.snapshot()
        processes = len(psutil.pids()) if psutil else 0
        health, label = self._system_health(snap["cpu"], snap["mem"], snap["net"])
        self._render_info_panel(
            "SYSTEM",
            f"Live health: {health}% {label}",
            [
                f"CPU load: {snap['cpu']:.0f}%",
                f"Memory use: {snap['mem']:.0f}%",
                f"Network throughput: {snap['net']:.1f} MB/s",
                f"Running processes: {processes if processes else 'N/A'}",
                f"Operating system: {_os_name()}",
            ],
        )

    def _add_task(self):
        task = self._task_name_input.text().strip()
        task_time = self._task_time_input.text().strip() or "Anytime"
        if not task:
            self._task_name_input.setPlaceholderText("Task name required")
            return
        self._tasks.append({"task": task, "time": task_time})
        _save_tasks(self._tasks)
        self._append_log(f"SYS: Added task - {task} at {task_time}")
        self._render_tasks_panel()

    def _remove_task(self, index: int):
        if 0 <= index < len(self._tasks):
            removed = self._tasks.pop(index)
            _save_tasks(self._tasks)
            self._append_log(f"SYS: Removed task - {removed.get('task', 'task')}")
            self._render_tasks_panel()

    def _handle_action(self, action: str):
        if action == "Tasks":
            self._show_section("Tasks")
            return
        if action == "System Control":
            self._show_section("System")
            return
        if action == "Voice Command":
            if self._muted:
                self._toggle_mute()
            self._input.setFocus()
            self._append_log("SYS: Voice command mode ready.")
            return
        if action == "Study Mode":
            self._show_section("Knowledge")
            self._input.setText("Start study mode for ")
            self._input.setFocus()
            return
        if action == "Brainstorm":
            self._show_section("Home")
            self._input.setText("Brainstorm ideas for ")
            self._input.setFocus()

    def _system_health(self, cpu: float, mem: float, net: float) -> tuple[int, str]:
        cpu_penalty = max(0.0, cpu - 55) * 0.55
        mem_penalty = max(0.0, mem - 65) * 0.85
        net_penalty = min(18.0, net * 1.8)
        health = max(0, min(100, round(100 - cpu_penalty - mem_penalty - net_penalty)))
        if health >= 80:
            return health, "Optimal"
        if health >= 55:
            return health, "Busy"
        return health, "High Load"

    def _build_command_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(68)
        bar.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgba(7, 20, 38, 205);
                border: 1px solid rgba(34, 211, 238, 75);
                border-radius: 30px;
            }}
            QLineEdit {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                padding-left: 22px;
                selection-background-color: rgba(34, 211, 238, 80);
            }}
            QLineEdit::placeholder {{ color: {C.MUTED}; }}
            QPushButton {{
                background: rgba(34, 211, 238, 34);
                color: {C.CYAN2};
                border: 1px solid rgba(34, 211, 238, 92);
                border-radius: 22px;
            }}
            QPushButton:hover {{
                background: rgba(34, 211, 238, 74);
                color: {C.WHITE};
            }}
            """
        )
        _add_glow(bar, C.CYAN, 32, 65)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setFont(_font(11))
        self._input.setPlaceholderText("Initiate Physics deep-dive or ask for project details...")
        self._input.returnPressed.connect(self._send)
        layout.addWidget(self._input, stretch=1)

        self._mute_btn = QPushButton("MIC")
        self._mute_btn.setFixedSize(58, 44)
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self._mute_btn)

        full = QPushButton("F11")
        full.setFixedSize(58, 44)
        full.setCursor(Qt.CursorShape.PointingHandCursor)
        full.clicked.connect(self._toggle_fullscreen)
        layout.addWidget(full)

        send = QPushButton("SEND")
        send.setFixedSize(76, 44)
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send)
        layout.addWidget(send)
        return bar

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%I:%M %p"))

    def _update_metrics(self):
        snap = _metrics.snapshot()
        processes = len(psutil.pids()) if psutil else 0
        health, label = self._system_health(snap["cpu"], snap["mem"], snap["net"])
        self._status_ring.set_value(health, label)
        values = {
            "CPU Load": f"{snap['cpu']:.0f}%",
            "Memory Use": f"{snap['mem']:.0f}%",
            "Network": f"{snap['net']:.1f} MB/s",
            "Processes": str(processes) if processes else "N/A",
        }
        for name, value in values.items():
            if name in self._status_value_labels:
                self._status_value_labels[name].setText(value)

        if health >= 80:
            note = "All systems running smoothly."
            note_color = C.TEXT2
        elif health >= 55:
            note = "System is busy, but COSMIC remains operational."
            note_color = C.YELLOW
        else:
            note = "High load detected. Close heavy apps for smoother performance."
            note_color = C.RED
        self._system_note.setText(note)
        self._system_note.setStyleSheet(f"color: {note_color};")
        self._metric_lbl.setText("Live hardware telemetry")

        if self._current_section == "System":
            self._render_system_panel()

        try:
            if psutil is None:
                raise RuntimeError("psutil is unavailable")
            elapsed = int(time.time() - psutil.boot_time())
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self._uptime_lbl.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        except Exception:
            self._uptime_lbl.setText("24:07:15")

    def _append_log(self, text: str):
        text = str(text)
        with self._log_history_lock:
            self._log_history.append(text)
            if len(self._log_history) > 400:
                removed = len(self._log_history) - 400
                del self._log_history[:removed]
                self._log_history_start += removed
        self._log.append_log(text)

    def get_logs(self, after: int = 0) -> dict:
        with self._log_history_lock:
            after = max(self._log_history_start, int(after))
            relative = min(after - self._log_history_start, len(self._log_history))
            return {
                "items": list(self._log_history[relative:]),
                "next": self._log_history_start + len(self._log_history),
            }

    def get_state(self) -> str:
        return self._state_value

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()

    def _position_overlay(self):
        if self._overlay and self._overlay.isVisible():
            ow, oh = 470, 360
            center = self.centralWidget()
            self._overlay.setGeometry(
                (center.width() - ow) // 2,
                (center.height() - oh) // 2,
                ow,
                oh,
            )

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.orb.set_muted(self._muted)
        if self._muted:
            self._mute_btn.setText("MUTED")
            self._apply_state("MUTED")
            self._append_log("SYS: Microphone muted.")
        else:
            self._mute_btn.setText("MIC")
            self._apply_state("LISTENING")
            self._append_log("SYS: Microphone active.")

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _apply_state(self, state: str):
        self._state_value = state
        self._state_lbl.setText(state)
        self.orb.set_state(state)

    def _on_file_selected(self, path: str):
        self._current_file = path
        file_path = Path(path)
        size = _fmt_size(file_path.stat().st_size)
        self._append_log(f"FILE: {file_path.name} ({size}) loaded")
        if self.on_text_command:
            message = (
                f"[FILE_UPLOADED] path={path} | name={file_path.name} | "
                f"type={file_path.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{file_path.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(message,), daemon=True).start()

    def _check_config(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(data.get("gemini_api_key")) and bool(data.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        self._overlay = SetupOverlay(self.centralWidget())
        self._overlay.done.connect(self._on_setup_done)
        self._overlay.show()
        self._position_overlay()

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._append_log(f"SYS: Initialised. OS={os_name}. COSMIC online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(self, *_):
        pass


class CosmicUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, value: bool):
        if bool(value) != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._current_file

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, callback):
        self._win.on_text_command = callback

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def get_logs(self, after: int = 0) -> dict:
        return self._win.get_logs(after)

    def get_state(self) -> str:
        return self._win.get_state()

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")


JarvisUI = CosmicUI
