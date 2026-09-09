from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTabWidget, QTableWidget, QVBoxLayout, QWidget

from ..icons import engineering_icon
from ..models import ProjectModel
from ..topology import NodeInsertionService
from ..widgets import Card, ModelSummaryCard, ProjectInfoCard, QuickActionsCard, RotorSketch, configure_table, item


class RotorModelPage(QWidget):
    run_requested = Signal()
    validate_requested = Signal()

    TAB_KEYS = {"shaft": 0, "disks": 1, "supports": 2, "seals": 3, "couplings": 4, "loads": 5, "probes": 6, "rotor": 0, "home": 0}

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        center = QVBoxLayout()
        center.setSpacing(10)
        center.setContentsMargins(0, 0, 0, 0)
        root.addLayout(center, 1)

        rotor_card = Card()
        rotor_layout = QVBoxLayout(rotor_card)
        rotor_layout.setContentsMargins(0, 0, 0, 0)
        rotor_layout.setSpacing(0)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(18, 10, 18, 8)
        header = QLabel("Rotor Model")
        header.setObjectName("cardHeader")
        header_row.addWidget(header)
        header_row.addStretch(1)
        physical = QLabel(f"Physical Shaft Sections  {project.physical_sections}")
        physical.setObjectName("muted")
        header_row.addWidget(physical)
        arrow = QLabel("  →  explicit node insertion  →  ")
        arrow.setObjectName("muted")
        header_row.addWidget(arrow)
        fem = QLabel(f"ROSS ShaftElements  {project.ross_shaft_elements}")
        fem.setObjectName("subHeader")
        header_row.addWidget(fem)
        rotor_layout.addLayout(header_row)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#dbe6f0;")
        rotor_layout.addWidget(line)
        self.sketch = RotorSketch(project)
        rotor_layout.addWidget(self.sketch, 1)
        center.addWidget(rotor_card, 6)

        data_card = Card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(10, 0, 10, 10)
        data_layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        data_layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._segments_tab(), "Shaft Segments")
        self.tabs.addTab(self._distributed_mass_tab(), "Disks / Rotor Masses")
        self.tabs.addTab(self._supports_tab(), "Supports")
        self.tabs.addTab(self._seals_tab(), "Seals")
        self.tabs.addTab(self._couplings_tab(), "Couplings")
        self.tabs.addTab(self._loads_tab(), "Loads")
        self.tabs.addTab(self._probes_tab(), "Probes")
        center.addWidget(data_card, 7)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right_panel = QWidget()
        right_panel.setFixedWidth(326)
        right_panel.setLayout(right)
        root.addWidget(right_panel)
        right.addWidget(ProjectInfoCard(project))
        right.addWidget(ModelSummaryCard(project), 1)
        actions = QuickActionsCard()
        actions.run_requested.connect(self.run_requested.emit)
        actions.validate_requested.connect(self.validate_requested.emit)
        right.addWidget(actions)

    def select_editor(self, key: str) -> None:
        self.tabs.setCurrentIndex(self.TAB_KEYS.get(key, 0))

    @staticmethod
    def _toolbar(title: str) -> QHBoxLayout:
        top = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("cardHeader")
        top.addWidget(label)
        top.addStretch(1)
        for text, icon_name in [("Add", "plus"), ("Delete", "trash"), ("Import...", "import")]:
            button = QPushButton(text)
            button.setObjectName("outlineButton")
            button.setIcon(engineering_icon(icon_name, 18))
            top.addWidget(button)
        return top

    @staticmethod
    def _table(headers: list[str], rows: list[list[object]], *, stretch_col: int | None = None) -> QTableWidget:
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table(table, row_height=32)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, item(value, center=c != stretch_col))
        if rows:
            table.selectRow(0)
        table.resizeColumnsToContents()
        if stretch_col is not None:
            table.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
        return table

    def _tab(self, title: str, headers: list[str], rows: list[list[object]], *, stretch_col: int | None = None) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 9, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(self._toolbar(title))
        layout.addWidget(self._table(headers, rows, stretch_col=stretch_col), 1)
        return page

    def _segments_tab(self) -> QWidget:
        rows = [[s.section, f"{s.length_mm:g}", f"{s.od_left_mm:g}", f"{s.od_right_mm:g}", f"{s.id_left_mm:g}", f"{s.id_right_mm:g}", s.material] for s in self.project.segments]
        page = self._tab("Physical Shaft Sections", ["Section", "Length (mm)", "OD Left (mm)", "OD Right (mm)", "ID Left (mm)", "ID Right (mm)", "Material"], rows, stretch_col=6)
        self.segment_table = page.findChild(QTableWidget)
        return page

    def _distributed_mass_tab(self) -> QWidget:
        eng = self.project.engineering
        rows: list[list[object]] = []
        if eng is not None:
            plan = NodeInsertionService.plan(eng)
            for mass in eng.distributed_masses:
                id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
                rows.append([
                    mass.name,
                    f"{mass.start_mm:g}",
                    f"{mass.center_mm:g}",
                    plan.node_for(mass.center_mm),
                    f"{mass.length_mm:g}",
                    f"{mass.mass_kg:g}",
                    f"{mass.od_mm:g}",
                    f"{mass.id_mm:g}",
                    f"{id_kg_m2:.6g}",
                    f"{ip_kg_m2:.6g}",
                    "DiskElement",
                    "Yes" if mass.ump_enabled else "No",
                ])
        return self._tab(
            "Disks / Rotor Components",
            ["Name", "Start (mm)", "Center (mm)", "Node", "Length (mm)", "Mass (kg)", "OD (mm)", "ID (mm)", "Id (kg·m²)", "Ip (kg·m²)", "ROSS realization", "UMP"],
            rows,
            stretch_col=0,
        )

    def _supports_tab(self) -> QWidget:
        eng = self.project.engineering
        rows = [] if eng is None else [[s.name, s.bearing_index + 1, f"{s.mass_kg:g}", f"{s.kxx:.3e}", f"{s.kyy:.3e}", f"{s.cxx:.3e}", f"{s.cyy:.3e}"] for s in eng.supports]
        return self._tab("Flexible Supports", ["Name", "Bearing", "Mass (kg)", "Kxx (N/m)", "Kyy (N/m)", "Cxx (N·s/m)", "Cyy (N·s/m)"], rows, stretch_col=0)

    def _seals_tab(self) -> QWidget:
        eng = self.project.engineering
        rows = [] if eng is None else [[s.name, f"{s.position_mm:g}", f"{s.kxx:.3e}", f"{s.kyy:.3e}", f"{s.cxx:.3e}", f"{s.cyy:.3e}"] for s in eng.seals]
        return self._tab("Seals", ["Name", "Position (mm)", "Kxx", "Kyy", "Cxx", "Cyy"], rows, stretch_col=0)

    def _couplings_tab(self) -> QWidget:
        eng = self.project.engineering
        rows = [] if eng is None else [[c.name, f"{c.position_mm:g}", f"{c.left_mass_kg:g}", f"{c.right_mass_kg:g}", f"{c.kt_x_n_m:.3e}", f"{c.kr_x_n_m_rad:.3e}"] for c in eng.couplings]
        return self._tab("Couplings", ["Name", "Position (mm)", "Left mass", "Right mass", "Kt X", "Kr X"], rows, stretch_col=0)

    def _loads_tab(self) -> QWidget:
        eng = self.project.engineering
        plan = None if eng is None else NodeInsertionService.plan(eng)
        rows = [] if eng is None else [[l.name, l.kind, f"{l.position_mm:g}", plan.node_for(l.position_mm), f"{l.magnitude:g}", f"{l.phase_deg:g}", "Exact inserted node" if plan.node_for(l.position_mm) is not None else "ERROR"] for l in eng.loads]
        return self._tab("Loads", ["Name", "Type", "Position (mm)", "Node", "Magnitude", "Phase (deg)", "Node mapping"], rows, stretch_col=0)

    def _probes_tab(self) -> QWidget:
        eng = self.project.engineering
        plan = None if eng is None else NodeInsertionService.plan(eng)
        rows = [] if eng is None else [[p.name, f"{p.position_mm:g}", plan.node_for(p.position_mm), p.coordinate, f"{p.orientation_deg:g}"] for p in eng.probes]
        return self._tab("Probes", ["Name", "Position (mm)", "Node", "Coordinate", "Orientation (deg)"], rows, stretch_col=0)
