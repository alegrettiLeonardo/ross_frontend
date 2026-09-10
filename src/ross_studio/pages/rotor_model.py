from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError
from ..icons import engineering_icon
from ..models import ProjectModel
from ..ross_backend import RossModelBuilder
from ..ross_native_view import RossNativeRotorView
from ..rotor_scene import InteractiveRotorSketch
from ..rotor_selection import RotorEntityRef, WORKSPACE_SELECTION
from ..topology import NodeInsertionService
from ..ump import project_ump_specs
from ..widgets import Card, ModelSummaryCard, ProjectInfoCard, QuickActionsCard, configure_table, item
from ..workspace_commands import WORKSPACE_COMMANDS


class RotorModelPage(QWidget):
    """Single engineering model workspace controlled by the left navigation.

    ROSS Studio 0.12 removes the duplicated horizontal model tabs. The left sidebar is
    the only primary navigation. A shared selection model synchronizes the model-driven
    sketch and the currently visible engineering table.
    """

    run_requested = Signal()
    validate_requested = Signal()
    status_message = Signal(str)

    EDITOR_KEYS = ("shaft", "disks", "supports", "seals", "couplings", "loads", "ump", "probes")
    EDITOR_TITLES = {
        "shaft": "Physical Shaft Sections & FE Discretization",
        "disks": "Disks / Rotor Masses",
        "supports": "Flexible Supports",
        "seals": "Seals",
        "couplings": "Couplings",
        "loads": "Loads",
        "ump": "Unbalanced Magnetic Pull (UMP)",
        "probes": "Probes",
    }

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.selection = WORKSPACE_SELECTION
        self.editor_tables: dict[str, QTableWidget] = {}
        self.editor_pages: dict[str, QWidget] = {}
        self._table_ref_builders: dict[str, list[RotorEntityRef]] = {}
        self._mesh_edit_guard = False

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
        header = QLabel("Rotor Engineering Model")
        header.setObjectName("cardHeader")
        header_row.addWidget(header)
        header_row.addStretch(1)
        self.physical_label = QLabel(f"Physical Sections  {project.physical_sections}")
        self.physical_label.setObjectName("muted")
        header_row.addWidget(self.physical_label)
        arrow = QLabel("  →  FE discretization + exact node insertion  →  ")
        arrow.setObjectName("muted")
        header_row.addWidget(arrow)
        self.fem_label = QLabel(f"ROSS ShaftElements  {project.ross_shaft_elements}")
        self.fem_label.setObjectName("subHeader")
        header_row.addWidget(self.fem_label)
        rotor_layout.addLayout(header_row)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#dbe6f0;")
        rotor_layout.addWidget(line)

        self.view_stack = QStackedWidget()
        self.sketch = InteractiveRotorSketch(project, selection=self.selection)
        self.view_stack.addWidget(self.sketch)
        if project.engineering is not None:
            self.native_view = RossNativeRotorView(project.engineering)
            self.view_stack.addWidget(self.native_view)
        else:
            self.native_view = None
        rotor_layout.addWidget(self.view_stack, 1)
        center.addWidget(rotor_card, 6)

        data_card = Card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(10, 8, 10, 10)
        data_layout.setSpacing(8)
        heading_row = QHBoxLayout()
        self.workspace_title = QLabel(self.EDITOR_TITLES["shaft"])
        self.workspace_title.setObjectName("cardHeader")
        heading_row.addWidget(self.workspace_title)
        heading_row.addStretch(1)
        mesh_help = QLabel("Sidebar = model navigation · click sketch ↔ table selection")
        mesh_help.setObjectName("muted")
        heading_row.addWidget(mesh_help)
        data_layout.addLayout(heading_row)

        self.editor_stack = QStackedWidget()
        data_layout.addWidget(self.editor_stack, 1)
        self._add_editor("shaft", self._segments_page())
        self._add_editor("disks", self._disks_page())
        self._add_editor("supports", self._supports_page())
        self._add_editor("seals", self._seals_page())
        self._add_editor("couplings", self._couplings_page())
        self._add_editor("loads", self._loads_page())
        self._add_editor("ump", self._ump_page())
        self._add_editor("probes", self._probes_page())
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

        self.sketch.entity_activated.connect(self._sketch_entity_activated)
        self.selection.selection_changed.connect(self._selection_changed)
        WORKSPACE_COMMANDS.fit_view_requested.connect(self._fit_view)
        WORKSPACE_COMMANDS.zoom_in_requested.connect(self._zoom_in)
        WORKSPACE_COMMANDS.zoom_out_requested.connect(self._zoom_out)
        WORKSPACE_COMMANDS.view_mode_requested.connect(self.set_view_mode)
        self.select_editor("shaft")

    def _add_editor(self, key: str, page: QWidget) -> None:
        self.editor_pages[key] = page
        self.editor_stack.addWidget(page)

    @staticmethod
    def _toolbar() -> QHBoxLayout:
        """Show future model-builder actions without pretending they are functional."""
        top = QHBoxLayout()
        top.addStretch(1)
        for text, icon_name in (("Add", "plus"), ("Delete", "trash"), ("Import…", "import")):
            button = QPushButton(text)
            button.setObjectName("outlineButton")
            button.setIcon(engineering_icon(icon_name, 18))
            button.setEnabled(False)
            button.setToolTip("Enabled in the Complete Rotor Model Builder tranche; no silent edit is performed.")
            top.addWidget(button)
        return top

    @staticmethod
    def _readonly_table(headers: list[str], rows: list[list[object]], *, stretch_col: int | None = None) -> QTableWidget:
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table(table, row_height=32)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                table.setItem(row_index, col_index, item(value, center=col_index != stretch_col))
        if rows:
            table.selectRow(0)
        table.resizeColumnsToContents()
        if stretch_col is not None:
            table.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
        return table

    def _table_page(self, key: str, table: QTableWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(self._toolbar())
        layout.addWidget(table, 1)
        self.editor_tables[key] = table
        table.itemSelectionChanged.connect(lambda k=key: self._table_selection_changed(k))
        return page

    def _effective_section_counts(self) -> Counter[int]:
        if self.project.engineering is None:
            return Counter()
        return Counter(element.physical_section for element in RossModelBuilder.shaft_plan(self.project.engineering))

    def _segments_page(self) -> QWidget:
        engineering = self.project.engineering
        counts = self._effective_section_counts()
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        x = 0.0
        if engineering is not None:
            for index, section in enumerate(engineering.shaft_sections):
                rows.append([
                    section.section,
                    f"{section.length_mm:g}",
                    f"{section.od_left_mm:g}",
                    f"{section.odr_mm:g}",
                    f"{section.id_left_mm:g}",
                    f"{section.idr_mm:g}",
                    section.fe_elements,
                    counts[section.section],
                    section.material,
                ])
                refs.append(RotorEntityRef("shaft", index, f"Shaft section {section.section}", x + section.length_mm / 2.0))
                x += section.length_mm
        headers = [
            "Section",
            "Length (mm)",
            "OD Left (mm)",
            "OD Right (mm)",
            "ID Left (mm)",
            "ID Right (mm)",
            "Base FE Elements",
            "Effective ROSS Elements",
            "Material",
        ]
        table = self._readonly_table(headers, rows, stretch_col=8)
        self.segment_table = table
        self._table_ref_builders["shaft"] = refs
        # Only the explicit FE-count column is presently an active domain editor.
        for row in range(table.rowCount()):
            cell = table.item(row, 6)
            cell.setFlags(cell.flags() | Qt.ItemFlag.ItemIsEditable)
            cell.setToolTip("Minimum number of finite shaft elements requested inside this physical section")
            effective = table.item(row, 7)
            effective.setToolTip("Actual ROSS ShaftElements after mandatory physical-node insertion")
        table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked)
        table.cellChanged.connect(self._mesh_cell_changed)
        return self._table_page("shaft", table)

    def _disks_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, mass in enumerate(engineering.distributed_masses):
                id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
                rows.append([
                    mass.name,
                    "Distributed rotor mass",
                    f"{mass.start_mm:g}",
                    f"{mass.center_mm:g}",
                    plan.node_for(mass.center_mm),
                    f"{mass.length_mm:g}",
                    f"{mass.mass_kg:g}",
                    f"{mass.od_mm:g}",
                    f"{id_kg_m2:.6g}",
                    f"{ip_kg_m2:.6g}",
                    "DiskElement",
                ])
                refs.append(RotorEntityRef("disks", index, mass.name, mass.center_mm))
            offset = len(engineering.distributed_masses)
            for local_index, disk in enumerate(engineering.disks):
                rows.append([
                    disk.name,
                    "Rigid disk",
                    "—",
                    f"{disk.position_mm:g}",
                    plan.node_for(disk.position_mm),
                    "—",
                    f"{disk.mass_kg:g}",
                    "—",
                    f"{disk.id_kg_m2:.6g}",
                    f"{disk.ip_kg_m2:.6g}",
                    "DiskElement",
                ])
                refs.append(RotorEntityRef("disks", offset + local_index, disk.name, disk.position_mm))
        table = self._readonly_table(
            ["Name", "Engineering body", "Start (mm)", "Center / x (mm)", "ROSS Node", "Length (mm)", "Mass (kg)", "OD (mm)", "Id (kg·m²)", "Ip (kg·m²)", "ROSS realization"],
            rows,
            stretch_col=0,
        )
        self._table_ref_builders["disks"] = refs
        return self._table_page("disks", table)

    def _supports_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, support in enumerate(engineering.supports):
                bearing = engineering.bearings[support.bearing_index]
                rows.append([
                    support.name,
                    bearing.name,
                    f"{bearing.position_mm:g}",
                    plan.node_for(bearing.position_mm),
                    f"{support.mass_kg:g}",
                    f"{support.kxx:.3e}",
                    f"{support.kyy:.3e}",
                    f"{support.cxx:.3e}",
                    f"{support.cyy:.3e}",
                ])
                refs.append(RotorEntityRef("supports", index, support.name, bearing.position_mm))
        table = self._readonly_table(
            ["Name", "Bearing", "x (mm)", "Shaft Node", "Mass (kg)", "Kxx (N/m)", "Kyy (N/m)", "Cxx (N·s/m)", "Cyy (N·s/m)"],
            rows,
            stretch_col=0,
        )
        self._table_ref_builders["supports"] = refs
        return self._table_page("supports", table)

    def _seals_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, seal in enumerate(engineering.seals):
                rows.append([seal.name, f"{seal.position_mm:g}", plan.node_for(seal.position_mm), f"{seal.kxx:.3e}", f"{seal.kyy:.3e}", f"{seal.cxx:.3e}", f"{seal.cyy:.3e}"])
                refs.append(RotorEntityRef("seals", index, seal.name, seal.position_mm))
        table = self._readonly_table(["Name", "Position (mm)", "ROSS Node", "Kxx", "Kyy", "Cxx", "Cyy"], rows, stretch_col=0)
        self._table_ref_builders["seals"] = refs
        return self._table_page("seals", table)

    def _couplings_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, coupling in enumerate(engineering.couplings):
                rows.append([coupling.name, f"{coupling.position_mm:g}", plan.node_for(coupling.position_mm), f"{coupling.left_mass_kg:g}", f"{coupling.right_mass_kg:g}", f"{coupling.kt_x_n_m:.3e}", f"{coupling.kr_x_n_m_rad:.3e}"])
                refs.append(RotorEntityRef("couplings", index, coupling.name, coupling.position_mm))
        table = self._readonly_table(["Name", "Position (mm)", "ROSS Node", "Left mass", "Right mass", "Kt X", "Kr X"], rows, stretch_col=0)
        self._table_ref_builders["couplings"] = refs
        return self._table_page("couplings", table)

    def _loads_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, load in enumerate(engineering.loads):
                node = plan.node_for(load.position_mm)
                rows.append([load.name, load.kind, f"{load.position_mm:g}", node, f"{load.magnitude:g}", f"{load.phase_deg:g}", "Exact inserted node" if node is not None else "ERROR"])
                refs.append(RotorEntityRef("loads", index, load.name, load.position_mm))
        table = self._readonly_table(["Name", "Type", "Position (mm)", "ROSS Node", "Magnitude", "Phase (deg)", "Node mapping"], rows, stretch_col=0)
        self._table_ref_builders["loads"] = refs
        return self._table_page("loads", table)

    def _ump_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            for index, spec in enumerate(project_ump_specs(engineering)):
                rows.append([
                    spec.name,
                    f"{spec.start_mm:g}",
                    f"{spec.end_mm:g}",
                    f"{spec.length_mm:g}",
                    f"{spec.stiffness_per_length_n_m2:.9g}",
                    f"{spec.stiffness_per_length_n_m2 * spec.length_mm / 1000.0:.9g}",
                    spec.source_unit,
                    spec.source,
                ])
                refs.append(RotorEntityRef("ump", index, spec.name, 0.5 * (spec.start_mm + spec.end_mm)))
        if not rows:
            rows = [["—", "—", "—", "—", "0", "0", "N/m²", "No active UMP"]]
        table = self._readonly_table(
            ["Name", "Start (mm)", "End (mm)", "Length (mm)", "k′ UMP (N/m²)", "Integrated k (N/m)", "Source unit", "Source"],
            rows,
            stretch_col=7,
        )
        self._table_ref_builders["ump"] = refs
        return self._table_page("ump", table)

    def _probes_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, probe in enumerate(engineering.probes):
                rows.append([probe.name, f"{probe.position_mm:g}", plan.node_for(probe.position_mm), probe.coordinate, f"{probe.orientation_deg:g}"])
                refs.append(RotorEntityRef("probes", index, probe.name, probe.position_mm))
        table = self._readonly_table(["Name", "Position (mm)", "ROSS Node", "Coordinate", "Orientation (deg)"], rows, stretch_col=0)
        self._table_ref_builders["probes"] = refs
        return self._table_page("probes", table)

    def select_editor(self, key: str) -> None:
        normalized = "shaft" if key in {"rotor", "home"} else key
        page = self.editor_pages.get(normalized)
        if page is None:
            normalized = "shaft"
            page = self.editor_pages[normalized]
        self.editor_stack.setCurrentWidget(page)
        self.workspace_title.setText(self.EDITOR_TITLES[normalized])

    def set_view_mode(self, mode: str) -> None:
        if mode == "ROSS Native" and self.native_view is not None:
            self.native_view.refresh()
            self.view_stack.setCurrentWidget(self.native_view)
        else:
            self.view_stack.setCurrentWidget(self.sketch)

    def _fit_view(self) -> None:
        if self.view_stack.currentWidget() is self.sketch:
            self.sketch.fit()

    def _zoom_in(self) -> None:
        if self.view_stack.currentWidget() is self.sketch:
            self.sketch.zoom_in()

    def _zoom_out(self) -> None:
        if self.view_stack.currentWidget() is self.sketch:
            self.sketch.zoom_out()

    def _sketch_entity_activated(self, kind: str, index: int) -> None:
        if kind == "bearings":
            WORKSPACE_COMMANDS.navigate_requested.emit("bearings")
            return
        if kind in self.editor_pages:
            WORKSPACE_COMMANDS.navigate_requested.emit(kind)
            self._select_table_row(kind, index)

    def _select_table_row(self, kind: str, index: int) -> None:
        table = self.editor_tables.get(kind)
        if table is not None and 0 <= index < table.rowCount():
            table.selectRow(index)
            table.scrollToItem(table.item(index, 0))

    def _selection_changed(self, ref: RotorEntityRef | None) -> None:
        if ref is None or ref.kind == "bearings":
            return
        if ref.kind in self.editor_pages:
            self._select_table_row(ref.kind, ref.index)

    def _table_selection_changed(self, kind: str) -> None:
        if self._mesh_edit_guard:
            return
        table = self.editor_tables.get(kind)
        refs = self._table_ref_builders.get(kind, [])
        if table is None:
            return
        row = table.currentRow()
        if 0 <= row < len(refs):
            self.selection.select(refs[row])

    def _mesh_cell_changed(self, row: int, column: int) -> None:
        if self._mesh_edit_guard or column != 6 or self.project.engineering is None:
            return
        table = self.segment_table
        section = self.project.engineering.shaft_sections[row]
        cell = table.item(row, column)
        previous = section.fe_elements
        try:
            value = int(cell.text().strip())
            if str(value) != cell.text().strip() and not cell.text().strip().startswith("+"):
                raise ValueError
            section.fe_elements = value
            section.validate()
            # Force full topology validation before accepting the edit.
            self.project.engineering.validate()
        except (ValueError, EngineeringError) as exc:
            section.fe_elements = previous
            self._mesh_edit_guard = True
            cell.setText(str(previous))
            self._mesh_edit_guard = False
            self.status_message.emit(f"FE discretization rejected: {exc}")
            return

        counts = self._effective_section_counts()
        self._mesh_edit_guard = True
        for index, current in enumerate(self.project.engineering.shaft_sections):
            table.item(index, 7).setText(str(counts[current.section]))
        self._mesh_edit_guard = False
        self.project.touch()
        self.fem_label.setText(f"ROSS ShaftElements  {self.project.ross_shaft_elements}")
        self.sketch.update()
        # A native ROSS plot is a snapshot of the strict rotor; require a fresh build.
        if self.native_view is not None:
            self.native_view._loaded = False
        self.status_message.emit(
            f"Section {section.section}: base mesh {section.fe_elements} element(s); effective rotor {self.project.ross_shaft_elements} ShaftElements"
        )
