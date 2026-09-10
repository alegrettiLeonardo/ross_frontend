from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError
from ..icons import engineering_icon
from ..model_builder_service import MutationAudit, RotorModelMutationService
from ..model_entity_dialogs import (
    CouplingEditorDialog,
    DiskEditorDialog,
    DistributedMassEditorDialog,
    LoadEditorDialog,
    MassTypeDialog,
    PointMassEditorDialog,
    ProbeEditorDialog,
    SealEditorDialog,
    ShaftSectionEditorDialog,
    SupportEditorDialog,
)
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

    The left sidebar is the only primary model navigator. A shared selection model
    synchronizes the model-driven sketch and engineering tables. ROSS Studio 0.14
    routes every enabled domain edit through ``RotorModelMutationService`` so an
    edit cannot reach the live project unless domain validation, exact-node mapping
    and a strict ROSS assembly all succeed first.
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
        self.model_builder = RotorModelMutationService()
        self.editor_tables: dict[str, QTableWidget] = {}
        self.editor_pages: dict[str, QWidget] = {}
        self.editor_action_buttons: dict[str, dict[str, QPushButton]] = {}
        self._table_ref_builders: dict[str, list[RotorEntityRef]] = {}
        self._disk_row_targets: list[tuple[str, int]] = []
        self._mesh_edit_guard = False
        self._current_editor_key = "shaft"

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
        mesh_help = QLabel("Sidebar = model navigation · click sketch ↔ table selection · edits are strict-Ross qualified")
        mesh_help.setObjectName("muted")
        heading_row.addWidget(mesh_help)
        data_layout.addLayout(heading_row)

        self.editor_stack = QStackedWidget()
        data_layout.addWidget(self.editor_stack, 1)
        self._populate_editors()
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

    def _populate_editors(self) -> None:
        self._add_editor("shaft", self._segments_page())
        self._add_editor("disks", self._disks_page())
        self._add_editor("supports", self._supports_page())
        self._add_editor("seals", self._seals_page())
        self._add_editor("couplings", self._couplings_page())
        self._add_editor("loads", self._loads_page())
        self._add_editor("ump", self._ump_page())
        self._add_editor("probes", self._probes_page())

    def _add_editor(self, key: str, page: QWidget) -> None:
        self.editor_pages[key] = page
        self.editor_stack.addWidget(page)

    def _toolbar(self, key: str) -> QHBoxLayout:
        """Expose only actions whose engineering transaction is implemented."""
        top = QHBoxLayout()
        top.addStretch(1)
        enabled = {
            "shaft": {"edit"},
            "disks": {"add", "edit", "delete"},
            "supports": {"edit"},
            "seals": {"add", "edit", "delete"},
            "couplings": {"add", "edit", "delete"},
            "loads": {"add", "edit", "delete"},
            "probes": {"add", "edit", "delete"},
        }.get(key, set())
        buttons: dict[str, QPushButton] = {}
        for action, text, icon_name in (
            ("add", "Add", "plus"),
            ("edit", "Edit", "gear"),
            ("delete", "Delete", "trash"),
            ("import", "Import…", "import"),
        ):
            button = QPushButton(text)
            button.setObjectName("outlineButton")
            button.setIcon(engineering_icon(icon_name, 18))
            button.setEnabled(action in enabled)
            if action not in enabled:
                if key == "shaft" and action in {"add", "delete"}:
                    button.setToolTip(
                        "Shaft section insertion/deletion is blocked until the user chooses an explicit downstream absolute-coordinate remapping policy."
                    )
                elif key == "supports" and action in {"add", "delete"}:
                    button.setToolTip(
                        "Flexible-support creation/deletion changes bearing ownership and remains Bearing Studio/topology controlled."
                    )
                elif key == "ump":
                    button.setToolTip(
                        "UMP is derived from its qualified engineering source and is not edited as a detached duplicate here."
                    )
                elif action == "import":
                    button.setToolTip("Import is intentionally gated until a schema-preserving transaction is qualified.")
                else:
                    button.setToolTip("This editor action is not qualified; no silent edit is performed.")
            if action == "add":
                button.clicked.connect(lambda checked=False, k=key: self._add_entity(k))
            elif action == "edit":
                button.clicked.connect(lambda checked=False, k=key: self._edit_entity(k))
            elif action == "delete":
                button.clicked.connect(lambda checked=False, k=key: self._delete_entity(k))
            buttons[action] = button
            top.addWidget(button)
        self.editor_action_buttons[key] = buttons
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
        layout.addLayout(self._toolbar(key))
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
        self._disk_row_targets = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, mass in enumerate(engineering.distributed_masses):
                id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
                rows.append([
                    mass.name,
                    "Distributed rotor mass [Massas]",
                    f"{mass.start_mm:g}",
                    f"{mass.center_mm:g}",
                    plan.node_for(mass.center_mm),
                    f"{mass.length_mm:g}",
                    f"{mass.mass_kg:g}",
                    f"{mass.od_mm:g}",
                    f"{id_kg_m2:.6g}",
                    f"{ip_kg_m2:.6g}",
                    "—",
                    "DiskElement equivalent",
                ])
                refs.append(RotorEntityRef("disks", len(refs), mass.name, mass.center_mm))
                self._disk_row_targets.append(("distributed_mass", index))
            for index, disk in enumerate(engineering.disks):
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
                    "—",
                    "DiskElement",
                ])
                refs.append(RotorEntityRef("disks", len(refs), disk.name, disk.position_mm))
                self._disk_row_targets.append(("disk", index))
            for index, mass in enumerate(engineering.point_masses):
                rows.append([
                    mass.name,
                    "Concentrated mass [Concent]",
                    "—",
                    f"{mass.position_mm:g}",
                    plan.node_for(mass.position_mm),
                    "—",
                    f"{mass.mass_kg:g}",
                    "—",
                    f"{mass.ix_kg_m2:.6g}",
                    f"{mass.iy_kg_m2:.6g}",
                    f"{mass.iz_kg_m2:.6g}",
                    "qualified concentrated DiskElement",
                ])
                refs.append(RotorEntityRef("disks", len(refs), mass.name, mass.position_mm))
                self._disk_row_targets.append(("point_mass", index))
        table = self._readonly_table(
            [
                "Name", "Engineering body", "Start (mm)", "Center / x (mm)", "ROSS Node",
                "Length (mm)", "Mass (kg)", "OD (mm)", "Id / Ix (kg·m²)",
                "Ip / Iy (kg·m²)", "Iz (kg·m²)", "ROSS realization",
            ],
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
                rows.append([
                    seal.name, f"{seal.position_mm:g}", plan.node_for(seal.position_mm),
                    f"{seal.kxx:.3e}", f"{seal.kyy:.3e}", f"{seal.kxy:.3e}", f"{seal.kyx:.3e}",
                    f"{seal.cxx:.3e}", f"{seal.cyy:.3e}", f"{seal.cxy:.3e}", f"{seal.cyx:.3e}",
                ])
                refs.append(RotorEntityRef("seals", index, seal.name, seal.position_mm))
        table = self._readonly_table(
            ["Name", "Position (mm)", "ROSS Node", "Kxx", "Kyy", "Kxy", "Kyx", "Cxx", "Cyy", "Cxy", "Cyx"],
            rows,
            stretch_col=0,
        )
        self._table_ref_builders["seals"] = refs
        return self._table_page("seals", table)

    def _couplings_page(self) -> QWidget:
        engineering = self.project.engineering
        rows: list[list[object]] = []
        refs: list[RotorEntityRef] = []
        if engineering is not None:
            plan = NodeInsertionService.plan(engineering)
            for index, coupling in enumerate(engineering.couplings):
                rows.append([
                    coupling.name,
                    f"{coupling.position_mm:g}",
                    plan.node_for(coupling.position_mm),
                    f"{coupling.left_mass_kg:g}",
                    f"{coupling.right_mass_kg:g}",
                    f"{coupling.left_ip_kg_m2:.6g}",
                    f"{coupling.right_ip_kg_m2:.6g}",
                    f"{coupling.kt_x_n_m:.3e}",
                    f"{coupling.kt_y_n_m:.3e}",
                    f"{coupling.kt_z_n_m:.3e}",
                    f"{coupling.kr_x_n_m_rad:.3e}",
                    f"{coupling.kr_y_n_m_rad:.3e}",
                    f"{coupling.kr_z_n_m_rad:.3e}",
                ])
                refs.append(RotorEntityRef("couplings", index, coupling.name, coupling.position_mm))
        table = self._readonly_table(
            [
                "Name", "Position (mm)", "ROSS Node", "Left mass", "Right mass", "Left Ip", "Right Ip",
                "Kt X", "Kt Y", "Kt Z", "Kr X", "Kr Y", "Kr Z",
            ],
            rows,
            stretch_col=0,
        )
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
                rows.append([
                    load.name, load.kind, f"{load.position_mm:g}", node,
                    f"{load.magnitude:g}", f"{load.phase_deg:g}",
                    "Exact inserted node" if node is not None else "ERROR",
                ])
                refs.append(RotorEntityRef("loads", index, load.name, load.position_mm))
        table = self._readonly_table(
            ["Name", "Type", "Position (mm)", "ROSS Node", "Magnitude", "Phase (deg)", "Node mapping"],
            rows,
            stretch_col=0,
        )
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
                rows.append([
                    probe.name, f"{probe.position_mm:g}", plan.node_for(probe.position_mm),
                    probe.coordinate, f"{probe.orientation_deg:g}",
                ])
                refs.append(RotorEntityRef("probes", index, probe.name, probe.position_mm))
        table = self._readonly_table(
            ["Name", "Position (mm)", "ROSS Node", "Coordinate", "Orientation (deg)"],
            rows,
            stretch_col=0,
        )
        self._table_ref_builders["probes"] = refs
        return self._table_page("probes", table)

    def _selected_row(self, key: str) -> int:
        table = self.editor_tables.get(key)
        return -1 if table is None else table.currentRow()

    def _disk_target(self, row: int) -> tuple[str, int]:
        if not 0 <= row < len(self._disk_row_targets):
            raise EngineeringError(f"Disk/mass row {row} does not map to an engineering body.")
        return self._disk_row_targets[row]

    @staticmethod
    def _disk_table_row(engineering, kind: str, index: int) -> int:
        if kind == "distributed_mass":
            return index
        if kind == "disk":
            return len(engineering.distributed_masses) + index
        if kind == "point_mass":
            return len(engineering.distributed_masses) + len(engineering.disks) + index
        raise EngineeringError(f"Unsupported disk/mass kind {kind!r}.")

    @staticmethod
    def _require_name(record, label: str) -> None:
        if not getattr(record, "name", "").strip():
            raise EngineeringError(f"{label} name cannot be empty.")

    def _edit_entity(self, key: str) -> None:
        engineering = self.project.engineering
        if engineering is None:
            self.status_message.emit("Model edit rejected: engineering domain is not loaded")
            return
        row = self._selected_row(key)
        if row < 0:
            self.status_message.emit(f"Select a {key} row before Edit")
            return

        try:
            if key == "shaft":
                dialog = ShaftSectionEditorDialog(engineering.shaft_sections[row], self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                preview = self.model_builder.preview_update(engineering, "shaft", row, dialog.changes())
            elif key == "supports":
                support = engineering.supports[row]
                bearing_name = engineering.bearings[support.bearing_index].name
                dialog = SupportEditorDialog(support, bearing_name, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                preview = self.model_builder.preview_update(engineering, "support", row, dialog.changes())
            elif key == "disks":
                kind, index = self._disk_target(row)
                if kind == "distributed_mass":
                    dialog = DistributedMassEditorDialog(
                        engineering.distributed_masses[index], total_length_mm=engineering.total_length_mm, parent=self
                    )
                elif kind == "disk":
                    dialog = DiskEditorDialog(engineering.disks[index], total_length_mm=engineering.total_length_mm, parent=self)
                else:
                    dialog = PointMassEditorDialog(
                        engineering.point_masses[index], total_length_mm=engineering.total_length_mm, parent=self
                    )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self._require_name(dialog.record(), self.EDITOR_TITLES[key])
                preview = self.model_builder.preview_update(engineering, kind, index, dialog.changes())
            elif key == "seals":
                dialog = SealEditorDialog(engineering.seals[row], total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self._require_name(dialog.record(), "Seal")
                preview = self.model_builder.preview_update(engineering, "seal", row, dialog.changes())
            elif key == "couplings":
                dialog = CouplingEditorDialog(engineering.couplings[row], total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self._require_name(dialog.record(), "Coupling")
                preview = self.model_builder.preview_update(engineering, "coupling", row, dialog.changes())
            elif key == "loads":
                dialog = LoadEditorDialog(engineering.loads[row], total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, "Load")
                if not record.kind:
                    raise EngineeringError("Load type cannot be empty.")
                preview = self.model_builder.preview_update(engineering, "load", row, dialog.changes())
            elif key == "probes":
                dialog = ProbeEditorDialog(engineering.probes[row], total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self._require_name(dialog.record(), "Probe")
                preview = self.model_builder.preview_update(engineering, "probe", row, dialog.changes())
            else:
                self.status_message.emit(f"{self.EDITOR_TITLES.get(key, key)} editing is not qualified")
                return
            audit = self.model_builder.commit(engineering, preview)
        except (EngineeringError, ValueError) as exc:
            self.status_message.emit(f"Model edit rejected: {exc}")
            return
        self._after_model_commit(key, audit, selected_row=row)

    def _add_entity(self, key: str) -> None:
        engineering = self.project.engineering
        if engineering is None:
            self.status_message.emit("Model add rejected: engineering domain is not loaded")
            return
        try:
            if key == "disks":
                chooser = MassTypeDialog(self)
                if chooser.exec() != QDialog.DialogCode.Accepted:
                    return
                kind = chooser.selected_kind()
                if kind == "distributed_mass":
                    dialog = DistributedMassEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                elif kind == "disk":
                    dialog = DiskEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                elif kind == "point_mass":
                    dialog = PointMassEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                else:
                    raise EngineeringError(f"Unsupported disk/mass kind {kind!r}.")
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, self.EDITOR_TITLES[key])
                preview = self.model_builder.preview_add(engineering, kind, record)
                audit = self.model_builder.commit(engineering, preview)
                index = len(getattr(engineering, {
                    "distributed_mass": "distributed_masses",
                    "disk": "disks",
                    "point_mass": "point_masses",
                }[kind])) - 1
                selected_row = self._disk_table_row(engineering, kind, index)
            elif key == "seals":
                dialog = SealEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, "Seal")
                preview = self.model_builder.preview_add(engineering, "seal", record)
                audit = self.model_builder.commit(engineering, preview)
                selected_row = len(engineering.seals) - 1
            elif key == "couplings":
                dialog = CouplingEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, "Coupling")
                preview = self.model_builder.preview_add(engineering, "coupling", record)
                audit = self.model_builder.commit(engineering, preview)
                selected_row = len(engineering.couplings) - 1
            elif key == "loads":
                dialog = LoadEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, "Load")
                if not record.kind:
                    raise EngineeringError("Load type cannot be empty.")
                preview = self.model_builder.preview_add(engineering, "load", record)
                audit = self.model_builder.commit(engineering, preview)
                selected_row = len(engineering.loads) - 1
            elif key == "probes":
                dialog = ProbeEditorDialog(total_length_mm=engineering.total_length_mm, parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                record = dialog.record()
                self._require_name(record, "Probe")
                preview = self.model_builder.preview_add(engineering, "probe", record)
                audit = self.model_builder.commit(engineering, preview)
                selected_row = len(engineering.probes) - 1
            else:
                self.status_message.emit(f"Add is not qualified for {self.EDITOR_TITLES.get(key, key)}")
                return
        except (EngineeringError, ValueError) as exc:
            self.status_message.emit(f"Model add rejected: {exc}")
            return
        self._after_model_commit(key, audit, selected_row=selected_row)

    def _delete_entity(self, key: str) -> None:
        engineering = self.project.engineering
        if engineering is None:
            self.status_message.emit("Model delete rejected: engineering domain is not loaded")
            return
        row = self._selected_row(key)
        if row < 0:
            self.status_message.emit(f"Select a {key} row before Delete")
            return

        try:
            if key == "disks":
                kind, index = self._disk_target(row)
                collection = getattr(engineering, {
                    "distributed_mass": "distributed_masses",
                    "disk": "disks",
                    "point_mass": "point_masses",
                }[kind])
                record = collection[index]
            elif key == "seals":
                kind, index, record = "seal", row, engineering.seals[row]
            elif key == "couplings":
                kind, index, record = "coupling", row, engineering.couplings[row]
            elif key == "loads":
                kind, index, record = "load", row, engineering.loads[row]
            elif key == "probes":
                kind, index, record = "probe", row, engineering.probes[row]
            else:
                self.status_message.emit(f"Delete is not qualified for {self.EDITOR_TITLES.get(key, key)}")
                return

            position = getattr(record, "position_mm", getattr(record, "center_mm", None))
            position_text = "" if position is None else f" at {position:g} mm"
            answer = QMessageBox.question(
                self,
                f"Delete {self.EDITOR_TITLES.get(key, key)}",
                f"Delete {record.name!r}{position_text}? The candidate model will be qualified again before commit.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            preview = self.model_builder.preview_delete(engineering, kind, index)
            audit = self.model_builder.commit(engineering, preview)
        except (EngineeringError, ValueError) as exc:
            self.status_message.emit(f"Model delete rejected: {exc}")
            return

        if key == "disks":
            target_row = min(row, len(self._disk_row_targets) - 2)
        else:
            collection = getattr(engineering, {
                "seals": "seals",
                "couplings": "couplings",
                "loads": "loads",
                "probes": "probes",
            }[key])
            target_row = min(row, len(collection) - 1)
        self._after_model_commit(key, audit, selected_row=target_row)

    def _rebuild_editors(self, active_key: str, selected_row: int = -1) -> None:
        self._mesh_edit_guard = True
        while self.editor_stack.count():
            widget = self.editor_stack.widget(0)
            self.editor_stack.removeWidget(widget)
            widget.deleteLater()
        self.editor_tables.clear()
        self.editor_pages.clear()
        self.editor_action_buttons.clear()
        self._table_ref_builders.clear()
        self._disk_row_targets.clear()
        self._populate_editors()
        self._mesh_edit_guard = False
        self.select_editor(active_key)
        if selected_row >= 0:
            self._select_table_row(active_key, selected_row)

    def _after_model_commit(self, key: str, audit: MutationAudit, *, selected_row: int = -1) -> None:
        self.project.touch()
        self.physical_label.setText(f"Physical Sections  {self.project.physical_sections}")
        self.fem_label.setText(f"ROSS ShaftElements  {self.project.ross_shaft_elements}")
        self._rebuild_editors(key, selected_row)
        self.sketch.update()
        if self.native_view is not None:
            self.native_view._loaded = False
        self.status_message.emit(
            f"{audit.entity_kind} {audit.operation} committed after strict ROSS qualification · "
            f"{audit.shaft_elements} ShaftElements / {audit.shaft_nodes} shaft nodes"
        )

    def select_editor(self, key: str) -> None:
        normalized = "shaft" if key in {"rotor", "home"} else key
        page = self.editor_pages.get(normalized)
        if page is None:
            normalized = "shaft"
            page = self.editor_pages[normalized]
        self._current_editor_key = normalized
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
            text = cell.text().strip()
            value = int(text)
            if str(value) != text and not (text.startswith("+") and str(value) == text[1:]):
                raise ValueError(f"FE element count must be an integer; received {text!r}.")
            preview = self.model_builder.preview_update(
                self.project.engineering,
                "shaft",
                row,
                {"fe_elements": value},
            )
            audit = self.model_builder.commit(self.project.engineering, preview)
        except (ValueError, EngineeringError) as exc:
            self._mesh_edit_guard = True
            cell.setText(str(previous))
            self._mesh_edit_guard = False
            self.status_message.emit(f"FE discretization rejected: {exc}")
            return

        self._after_model_commit("shaft", audit, selected_row=row)
