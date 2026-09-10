from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .icons import engineering_icon
from .models import ProjectModel
from .theme import COLORS
from .workspace_commands import WORKSPACE_COMMANDS


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, *, object_name: str = "card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)


class SectionCard(Card):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(14, 12, 14, 14)
        self.root.setSpacing(8)
        header = QLabel(title)
        header.setObjectName("panelHeader")
        self.root.addWidget(header)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{COLORS.border_soft};")
        self.root.addWidget(line)


class LabelValueGrid(QWidget):
    def __init__(self, rows: Iterable[tuple[str, str, str | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for r, (label, value, unit) in enumerate(rows):
            l = QLabel(label)
            l.setObjectName("muted")
            v = QLabel(value)
            v.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(l, r, 0)
            grid.addWidget(v, r, 1)
            if unit:
                u = QLabel(unit)
                u.setObjectName("muted")
                u.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(u, r, 2)
        grid.setColumnStretch(1, 1)


class Sidebar(QFrame):
    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(218)
        self.buttons: dict[str, QPushButton] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 12, 9, 12)
        root.setSpacing(1)
        self._add_nav(root, "home", "Home", "home")
        self._divider(root)
        self._section(root, "MODEL")
        for key, label, icon in [
            ("rotor", "Rotor", "rotor"),
            ("shaft", "Shaft", "shaft"),
            ("disks", "Disks / Masses", "disk"),
            ("bearings", "Bearings", "bearing"),
            ("seals", "Seals", "seal"),
            ("supports", "Supports", "support"),
            ("couplings", "Couplings", "coupling"),
            ("loads", "Loads", "loads"),
            ("ump", "UMP", "wave"),
            ("probes", "Probes", "probe"),
        ]:
            self._add_nav(root, key, label, icon)
        self._divider(root)
        self._section(root, "ANALYSIS")
        for key, label, icon in [
            ("rotor_dynamics", "Rotor Dynamics", "wave"),
            ("response", "Response", "response"),
            ("stability", "Stability", "shield"),
            ("transient", "Transient", "transient"),
            ("faults", "Faults", "fault"),
            ("stochastic", "Stochastic", "stochastic"),
        ]:
            self._add_nav(root, key, label, icon)
        self._divider(root)
        self._section(root, "RESULTS")
        self._add_nav(root, "results", "Results", "results")
        root.addStretch(1)
        WORKSPACE_COMMANDS.navigate_requested.connect(self.set_active)

    def _section(self, root: QVBoxLayout, text: str) -> None:
        lab = QLabel(text)
        lab.setObjectName("navSection")
        root.addWidget(lab)

    def _divider(self, root: QVBoxLayout) -> None:
        line = QFrame()
        line.setObjectName("navDivider")
        root.addWidget(line)

    def _add_nav(self, root: QVBoxLayout, key: str, text: str, icon_name: str) -> None:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setIcon(engineering_icon(icon_name, 22, "#b9d2e7"))
        button.setIconSize(QSize(22, 22))
        button.clicked.connect(lambda checked=False, k=key: self.set_active(k))
        root.addWidget(button)
        self.buttons[key] = button

    def set_active(self, key: str) -> None:
        for name, button in self.buttons.items():
            button.setChecked(name == key)
        self.page_requested.emit(key)


class AppToolbar(QFrame):
    run_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setFixedHeight(60)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)
        self.buttons: dict[str, QPushButton] = {}
        for key, text, icon in [
            ("new", "New", "new"),
            ("open", "Open", "open"),
            ("save", "Save", "save"),
        ]:
            self._button(layout, key, text, icon)
        self._sep(layout)
        self._button(layout, "undo", "Undo", "undo")
        redo = self._button(layout, "redo", "Redo", "redo")
        redo.setEnabled(False)
        self._sep(layout)
        fit = self._button(layout, "fit", "Fit View", "fit")
        zoom_in = self._button(layout, "zoom_in", "Zoom In", "zoom_in")
        zoom_out = self._button(layout, "zoom_out", "Zoom Out", "zoom_out")
        fit.clicked.connect(WORKSPACE_COMMANDS.fit_view_requested.emit)
        zoom_in.clicked.connect(WORKSPACE_COMMANDS.zoom_in_requested.emit)
        zoom_out.clicked.connect(WORKSPACE_COMMANDS.zoom_out_requested.emit)
        layout.addStretch(1)
        self.view_combo = QComboBox()
        self.view_combo.setObjectName("viewCombo")
        # ROSS plot_rotor is a native interactive Plotly audit view, not a 3-D
        # assembly renderer. Keep the UI truthful; modal 3-D lives in Results.
        self.view_combo.addItems(["Engineering 2D", "ROSS Native"])
        self.view_combo.setToolTip("Engineering 2D editor or native ROSS 2.3.0 plot_rotor audit view")
        self.view_combo.currentTextChanged.connect(WORKSPACE_COMMANDS.view_mode_requested.emit)
        layout.addWidget(self.view_combo)

    def _button(self, layout: QHBoxLayout, key: str, text: str, icon: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("toolButton")
        button.setIcon(engineering_icon(icon, 20))
        button.setIconSize(QSize(20, 20))
        layout.addWidget(button)
        self.buttons[key] = button
        return button

    def _sep(self, layout: QHBoxLayout) -> None:
        line = QFrame()
        line.setObjectName("toolSeparator")
        layout.addWidget(line)


class StatusBar(QFrame):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.setObjectName("statusBar")
        self.setFixedHeight(46)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 4, 22, 4)
        layout.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(engineering_icon("check", 23).pixmap(23, 23))
        layout.addWidget(icon)
        self.message = QLabel("Model validated")
        self.message.setObjectName("statusSuccess")
        layout.addWidget(self.message)
        line = QLabel("│")
        line.setStyleSheet(f"color:{COLORS.border};")
        layout.addWidget(line)
        self.detail = QLabel("No issues found")
        layout.addWidget(self.detail)
        layout.addStretch(1)
        self.project_label = QLabel(project.name)
        layout.addWidget(self.project_label)
        layout.addWidget(QLabel("│"))
        self.units = QLabel("Units: SI (mm, kg, N)")
        layout.addWidget(self.units)
        layout.addWidget(QLabel("│"))
        layout.addWidget(QLabel("Ready"))

    def set_status(self, message: str, detail: str = "No issues found", units: str | None = None) -> None:
        self.message.setText(message)
        self.detail.setText(detail)
        if units is not None:
            self.units.setText(units)


class ProjectInfoCard(SectionCard):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__("Project Information", parent)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        items = [
            ("Project Name", project.name),
            ("Description", project.description),
            ("Created", project.created),
            ("Last Modified", project.modified),
        ]
        for row, (key, value) in enumerate(items):
            label = QLabel(key)
            label.setObjectName("muted")
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
            if key == "Description":
                field = QLabel(value)
                field.setWordWrap(True)
                field.setFrameShape(QFrame.Shape.Box)
                field.setStyleSheet(
                    f"background:white;border:1px solid {COLORS.border};border-radius:5px;padding:7px;"
                )
                field.setMinimumHeight(68)
            else:
                field = QLabel(value)
            grid.addWidget(field, row, 1)
        grid.setColumnStretch(1, 1)
        self.root.addLayout(grid)


class ModelSummaryCard(SectionCard):
    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__("Model Summary", parent)
        engineering = project.engineering
        base_elements = engineering.requested_shaft_element_count if engineering is not None else len(project.segments)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        labels = [
            ("Rotor Speed", f"{project.speed_rpm:,}", "rpm"),
            ("Material", project.material, None),
            ("Total Mass", f"{project.total_mass_kg:.1f}", "kg"),
            ("Total Length", f"{project.total_length_mm:,.0f}", "mm"),
            ("Physical Sections", str(len(project.segments)), None),
            ("Base FE Elements", str(base_elements), None),
            ("ROSS ShaftElements", str(project.ross_shaft_elements), None),
            ("Disks / Masses", str(project.disks), None),
            ("Bearings", str(project.bearings), None),
            ("Supports", str(project.supports), None),
        ]
        for row, (key, value, unit) in enumerate(labels):
            key_label = QLabel(key)
            key_label.setObjectName("muted")
            grid.addWidget(key_label, row, 0)
            if key == "Rotor Speed":
                field = QLineEdit(value)
                field.setFixedWidth(126)
                grid.addWidget(field, row, 1)
            elif key == "Material":
                field = QComboBox()
                field.addItems([project.material, "Steel (AISI 1045)", "Stainless Steel"])
                grid.addWidget(field, row, 1, 1, 2)
            else:
                grid.addWidget(QLabel(value), row, 1)
            if unit:
                unit_label = QLabel(unit)
                unit_label.setObjectName("muted")
                unit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
                grid.addWidget(unit_label, row, 2)
        grid.setColumnStretch(0, 1)
        self.root.addLayout(grid)


class QuickActionsCard(SectionCard):
    run_requested = Signal()
    validate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Quick Actions", parent)
        self.save = QPushButton("Save Project")
        self.save.setObjectName("softButton")
        self.save.setIcon(engineering_icon("save", 20))
        self.root.addWidget(self.save)
        self.validate = QPushButton("Validate Model")
        self.validate.setObjectName("successButton")
        self.validate.setIcon(engineering_icon("check", 20))
        self.root.addWidget(self.validate)
        self.run = QPushButton("Run Analysis")
        self.run.setObjectName("primaryButton")
        self.run.setIcon(engineering_icon("play", 21, "#ffffff"))
        self.root.addWidget(self.run)
        self.validate.clicked.connect(self.validate_requested.emit)
        self.run.clicked.connect(self.run_requested.emit)


def configure_table(table: QTableWidget, *, row_height: int = 32) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setStretchLastSection(True)


def item(value: object, *, center: bool = True) -> QTableWidgetItem:
    table_item = QTableWidgetItem(str(value))
    if center:
        table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return table_item
