from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..domain import RotorProject
from .model_page import ModelPage


class IndustrialModelPage(ModelPage):
    """Approved Rotor Model workspace enriched with real component tables."""

    def __init__(self, project: RotorProject):
        super().__init__(project)
        self.disk_table = self._replace_stub(1, "Disks", ["Name", "Position (mm)", "Mass (kg)", "Id (kg·m²)", "Ip (kg·m²)"])
        self.bearing_table = self._replace_stub(2, "Bearings", ["Name", "Position (mm)", "Model", "K/C points", "Flexible support"])
        self.support_table = self._replace_stub(3, "Supports", ["Bearing", "Kxx (N/m)", "Kyy (N/m)", "Cxx (N·s/m)", "Cyy (N·s/m)", "Housing mass (kg)"])
        self.loads_table = self._append_table("Loads / Probes", ["Kind", "Name", "Position (mm)", "Value / Coordinate", "Phase / Orientation"])
        self._populate_component_tables()

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        return table

    def _replace_stub(self, index: int, title: str, headers: list[str]) -> QTableWidget:
        old = self.tabs.widget(index)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 10, 14, 12)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        table = self._table(headers)
        layout.addWidget(table, 1)
        self.tabs.removeTab(index)
        old.deleteLater()
        self.tabs.insertTab(index, widget, title)
        return table

    def _append_table(self, title: str, headers: list[str]) -> QTableWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 10, 14, 12)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        table = self._table(headers)
        layout.addWidget(table, 1)
        self.tabs.addTab(widget, title)
        return table

    @staticmethod
    def _put(table: QTableWidget, row: int, values) -> None:
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)

    def _populate_component_tables(self) -> None:
        self.disk_table.setRowCount(len(self.project.disks))
        for row, disk in enumerate(self.project.disks):
            self._put(
                self.disk_table,
                row,
                [disk.tag or f"Disk {row + 1}", f"{disk.position_mm:.1f}", f"{disk.mass_kg:.3f}", f"{disk.diametral_inertia_kg_m2:.6g}", f"{disk.polar_inertia_kg_m2:.6g}"],
            )

        support_indices = {s.bearing_index for s in self.project.supports}
        self.bearing_table.setRowCount(len(self.project.bearings))
        for row, bearing in enumerate(self.project.bearings):
            points = len(bearing.frequency_rpm) if getattr(bearing, "frequency_rpm", None) else 1
            self._put(
                self.bearing_table,
                row,
                [bearing.tag or f"Bearing {row + 1}", f"{bearing.position_mm:.1f}", getattr(bearing, "kind", "bearing"), points, "Yes" if row in support_indices else "No"],
            )

        self.support_table.setRowCount(len(self.project.supports))
        for row, support in enumerate(self.project.supports):
            self._put(
                self.support_table,
                row,
                [support.bearing_index + 1, f"{support.kxx:.4e}", f"{support.kzz:.4e}", f"{support.cxx:.4e}", f"{support.czz:.4e}", f"{support.mass_kg:.3f}"],
            )

        rows = []
        for item in self.project.unbalances:
            rows.append(("Unbalance", item.tag, item.position_mm, f"{item.magnitude_g_mm:g} g·mm", f"{item.phase_deg:g}°"))
        for item in self.project.probes:
            rows.append(("Probe", item.tag, item.position_mm, f"Coordinate {item.coordinate}", f"{item.orientation_deg:g}°"))
        self.loads_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            values = list(values)
            values[2] = f"{float(values[2]):.1f}"
            self._put(self.loads_table, row, values)

    def set_project(self, project: RotorProject):
        # Loading must be atomic.  The base page connects textChanged/editingFinished
        # callbacks that write widgets back into self.project.  If those callbacks run
        # while a new project is only partially reflected in the widgets, stale values
        # from the previous project (e.g. demo 1800 rpm) can overwrite imported data.
        blockers = [
            QSignalBlocker(self.project_name),
            QSignalBlocker(self.description),
            QSignalBlocker(self.speed),
            QSignalBlocker(self.material),
            QSignalBlocker(self.table),
        ]
        try:
            super().set_project(project)
            self.project_name.setText(project.reference or "Untitled")
            self.description.setPlainText(str(project.metadata.get("description", project.metadata.get("component", ""))))
            self.speed.setText(f"{float(project.metadata.get('rotor_speed_rpm', 0.0)):,.0f}")
            self.material.clear()
            self.material.addItems([m.name for m in project.materials])
            self._populate_component_tables()
        finally:
            # Keep blockers alive through the complete widget refresh; deleting them
            # restores the original signal state.
            del blockers


__all__ = ["IndustrialModelPage"]
