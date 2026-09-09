from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from .icons import app_icon, studio_icon
from .theme import P


class Card(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None, margins=(12, 10, 12, 12)):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(*margins)
        self.layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self.layout.addWidget(label)


class TitleBar(QFrame):
    def __init__(self, window, project_name: str = "WGM20"):
        super().__init__()
        self.window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(54)
        self._drag_pos = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 0, 0)
        lay.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(app_icon(24).pixmap(24, 24))
        lay.addWidget(icon)
        title = QLabel("ROSS STUDIO")
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        sep = QLabel("|")
        sep.setStyleSheet("color:#90AFC6;font-size:17px;")
        lay.addWidget(sep)
        self.project_label = QLabel(project_name)
        self.project_label.setObjectName("ProjectTitle")
        lay.addWidget(self.project_label)
        lay.addStretch(1)
        for text, slot, obj in (("—", window.showMinimized, "WindowButton"), ("□", self._toggle_max, "WindowButton"), ("×", window.close, "CloseButton")):
            b = QToolButton()
            b.setText(text)
            b.setObjectName(obj)
            b.setFixedSize(48, 54)
            b.clicked.connect(slot)
            lay.addWidget(b)

    def _toggle_max(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)


class Sidebar(QFrame):
    pageRequested = Signal(str)
    GROUPS = [
        (None, [("home", "Home", "home")]),
        ("MODEL", [("rotor", "Rotor", "rotor"), ("shaft", "Shaft", "shaft"), ("disk", "Disks", "disks"), ("bearing", "Bearings", "bearings"), ("seal", "Seals", "seals"), ("support", "Supports", "supports"), ("coupling", "Couplings", "couplings"), ("load", "Loads", "loads")]),
        ("ANALYSIS", [("wave", "Rotor Dynamics", "rotor_dynamics"), ("response", "Response", "response"), ("shield", "Stability", "stability"), ("transient", "Transient", "transient"), ("warning", "Faults", "faults"), ("stochastic", "Stochastic", "stochastic")]),
        ("RESULTS", [("results", "Results", "results")]),
    ]

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(216)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 14, 9, 14)
        lay.setSpacing(3)
        self.buttons: dict[str, QToolButton] = {}
        for group, entries in self.GROUPS:
            if group:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet("background:rgba(255,255,255,0.08);margin:8px 9px;")
                lay.addWidget(line)
                label = QLabel(group)
                label.setObjectName("SidebarSection")
                label.setContentsMargins(9, 4, 0, 4)
                lay.addWidget(label)
            for icon_name, text, key in entries:
                b = QToolButton()
                b.setObjectName("NavButton")
                b.setText(text)
                b.setIcon(studio_icon(icon_name))
                b.setIconSize(QSize(20, 20))
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                b.setCheckable(True)
                b.setAutoExclusive(True)
                b.setMinimumHeight(37)
                b.clicked.connect(lambda checked=False, k=key: self.pageRequested.emit(k))
                lay.addWidget(b)
                self.buttons[key] = b
        lay.addStretch(1)
        self.set_active("rotor")

    def set_active(self, key: str):
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class TopToolbar(QFrame):
    actionTriggered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("TopToolbar")
        self.setFixedHeight(58)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 10, 6)
        lay.setSpacing(5)
        items = [("new", "New", "new"), ("open", "Open", "open"), ("save", "Save", "save"), (None, None, None), ("undo", "Undo", "undo"), ("redo", "Redo", "redo"), (None, None, None), ("fit", "Fit View", "fit"), ("zoom", "Zoom In", "zoom_in"), ("zoom", "Zoom Out", "zoom_out")]
        for icon_name, text, key in items:
            if key is None:
                line = QFrame()
                line.setFixedWidth(1)
                line.setStyleSheet(f"background:{P.border_soft}; margin:8px 7px;")
                lay.addWidget(line)
                continue
            b = QToolButton()
            b.setObjectName("ToolbarButton")
            b.setText(text)
            b.setIcon(studio_icon(icon_name, P.text, 18))
            b.setIconSize(QSize(18, 18))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if key == "redo":
                b.setEnabled(False)
            b.clicked.connect(lambda checked=False, k=key: self.actionTriggered.emit(k))
            lay.addWidget(b)
        lay.addStretch(1)
        view = QToolButton()
        view.setObjectName("ToolbarButton")
        view.setText("2D View ⌄")
        view.setMinimumWidth(108)
        lay.addWidget(view)


class StatusStrip(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(34)
        self.setStyleSheet(f"background:white;border-top:1px solid {P.border_soft};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)
        self.icon = QLabel("●")
        self.icon.setStyleSheet(f"color:{P.success};font-size:15px;")
        lay.addWidget(self.icon)
        self.message = QLabel("Model validated")
        self.message.setStyleSheet(f"color:{P.success};font-weight:600;")
        lay.addWidget(self.message)
        self.detail = QLabel("|    No issues found")
        self.detail.setObjectName("Muted")
        lay.addWidget(self.detail)
        lay.addStretch(1)
        self.project = QLabel("WGM20")
        lay.addWidget(self.project)
        lay.addWidget(QLabel("|"))
        self.units = QLabel("Units: SI (mm, kg, N)")
        lay.addWidget(self.units)
        lay.addWidget(QLabel("|"))
        lay.addWidget(QLabel("Ready"))

    def set_state(self, message: str, detail: str = "No issues found", success: bool = True):
        color = P.success if success else P.warning
        self.icon.setStyleSheet(f"color:{color};font-size:15px;")
        self.message.setStyleSheet(f"color:{color};font-weight:600;")
        self.message.setText(message)
        self.detail.setText(f"|    {detail}")


class BearingTypeButton(QToolButton):
    def __init__(self, icon_name: str, text: str):
        super().__init__()
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setText(text)
        self.setIcon(studio_icon(icon_name, P.text_dark, 38))
        self.setIconSize(QSize(38, 38))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setMinimumSize(112, 92)
        self.setStyleSheet(f"QToolButton{{background:white;border:1px solid {P.border};border-radius:6px;padding:7px;color:{P.text_dark};}} QToolButton:hover{{background:{P.blue_soft};}} QToolButton:checked{{background:#E6F2FF;border:2px solid {P.blue};color:{P.blue_dark};font-weight:700;}}")
