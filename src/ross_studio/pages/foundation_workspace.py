from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import (
    AdapterStatus,
    EngineeringError,
    FoundationCoefficientPoint,
    FoundationModel,
    FoundationSpec,
)
from ..model_builder_service import RotorModelMutationService
from ..models import ProjectModel
from ..widgets import Card, SectionCard


_COEFF_HEADERS = ("Hz", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy")
_MODEL_LABELS = {
    FoundationModel.RIGID: "Rigid / legacy ground",
    FoundationModel.LUMPED_KC: "Lumped K/C",
    FoundationModel.LUMPED_KCM: "Lumped K/C/M",
    FoundationModel.FREQUENCY_DEPENDENT_KC: "Frequency-dependent K/C",
}


def _number(value: float = 0.0, *, minimum: float = -1.0e18, maximum: float = 1.0e18) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(6)
    box.setRange(minimum, maximum)
    box.setValue(float(value))
    box.setKeyboardTracking(False)
    return box


def _float_item(value: float) -> QTableWidgetItem:
    item = QTableWidgetItem(f"{float(value):.12g}")
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class FoundationEditorDialog(QDialog):
    """Edit one qualified 2-DOF FoundationSpec without hiding unsupported physics."""

    def __init__(
        self,
        project: ProjectModel,
        foundation: FoundationSpec | None = None,
        *,
        default_support_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if project.engineering is None:
            raise EngineeringError("Foundation Studio requires an engineering RotorProject.")
        self.project = project
        engineering = project.engineering
        source = deepcopy(foundation) if foundation is not None else FoundationSpec(
            name="Foundation",
            support_index=default_support_index,
            model_type=FoundationModel.RIGID,
        )
        self.setWindowTitle("Add Foundation" if foundation is None else f"Edit Foundation — {source.name}")
        self.resize(1040, 650)

        root = QVBoxLayout(self)
        note = QLabel(
            "Foundation is attached to an explicit flexible-support owner. The editor exposes only the qualified "
            "2-DOF contracts; reduced matrices and 6-DOF truncation are not offered. Apply is transactional: domain "
            "validation and a strict ROSS assembly must succeed before the live project is changed."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.support = QComboBox()
        for index, support in enumerate(engineering.supports):
            bearing = engineering.bearings[support.bearing_index]
            self.support.addItem(f"{index}: {support.name} → {bearing.name} @ {bearing.position_mm:g} mm", index)
        support_row = max(0, self.support.findData(source.support_index))
        self.support.setCurrentIndex(support_row)

        self.model = QComboBox()
        for value, label in _MODEL_LABELS.items():
            self.model.addItem(label, value)
        self.model.setCurrentIndex(max(0, self.model.findData(source.model_type)))

        self.mass = _number(source.mass_kg, minimum=0.0)
        self.kxx = _number(source.kxx)
        self.kxy = _number(source.kxy)
        self.kyx = _number(source.kyx)
        self.kyy = _number(source.kyy)
        self.cxx = _number(source.cxx)
        self.cxy = _number(source.cxy)
        self.cyx = _number(source.cyx)
        self.cyy = _number(source.cyy)
        form.addRow("Name", self.name)
        form.addRow("Support owner", self.support)
        form.addRow("Foundation model", self.model)
        form.addRow("Foundation mass (kg)", self.mass)
        form.addRow("Kxx (N/m)", self.kxx)
        form.addRow("Kxy (N/m)", self.kxy)
        form.addRow("Kyx (N/m)", self.kyx)
        form.addRow("Kyy (N/m)", self.kyy)
        form.addRow("Cxx (N·s/m)", self.cxx)
        form.addRow("Cxy (N·s/m)", self.cxy)
        form.addRow("Cyx (N·s/m)", self.cyx)
        form.addRow("Cyy (N·s/m)", self.cyy)
        root.addLayout(form)

        freq_title = QLabel("Frequency-dependent K/C table — engineering input in Hz; ROSS assembly converts to rad/s")
        freq_title.setObjectName("subHeader")
        root.addWidget(freq_title)
        self.coefficients = QTableWidget(0, len(_COEFF_HEADERS))
        self.coefficients.setHorizontalHeaderLabels(_COEFF_HEADERS)
        self.coefficients.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.coefficients.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.coefficients.setAlternatingRowColors(True)
        root.addWidget(self.coefficients, 1)

        row_actions = QHBoxLayout()
        self.add_frequency_row = QPushButton("Add frequency row")
        self.remove_frequency_row = QPushButton("Remove selected row")
        row_actions.addWidget(self.add_frequency_row)
        row_actions.addWidget(self.remove_frequency_row)
        row_actions.addStretch(1)
        root.addLayout(row_actions)
        self.add_frequency_row.clicked.connect(self._add_frequency_row)
        self.remove_frequency_row.clicked.connect(self._remove_frequency_row)
        for point in source.coefficients:
            self._append_point(point)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_if_parseable)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.model.currentIndexChanged.connect(self._sync_model_controls)
        self._sync_model_controls()

    def _append_point(self, point: FoundationCoefficientPoint) -> None:
        row = self.coefficients.rowCount()
        self.coefficients.insertRow(row)
        values = (
            point.frequency_hz, point.kxx, point.kxy, point.kyx, point.kyy,
            point.cxx, point.cxy, point.cyx, point.cyy,
        )
        for column, value in enumerate(values):
            self.coefficients.setItem(row, column, _float_item(value))

    def _add_frequency_row(self) -> None:
        if self.coefficients.rowCount():
            previous = self._row_values(self.coefficients.rowCount() - 1)
            previous[0] = previous[0] + max(1.0, 0.1 * max(previous[0], 1.0))
        else:
            previous = [0.0, 1.0e8, 0.0, 0.0, 1.0e8, 1.0e4, 0.0, 0.0, 1.0e4]
        row = self.coefficients.rowCount()
        self.coefficients.insertRow(row)
        for column, value in enumerate(previous):
            self.coefficients.setItem(row, column, _float_item(value))
        self.coefficients.selectRow(row)

    def _remove_frequency_row(self) -> None:
        rows = sorted({index.row() for index in self.coefficients.selectedIndexes()}, reverse=True)
        for row in rows:
            self.coefficients.removeRow(row)

    def _row_values(self, row: int) -> list[float]:
        values: list[float] = []
        for column, header in enumerate(_COEFF_HEADERS):
            item = self.coefficients.item(row, column)
            text = "" if item is None else item.text().strip()
            try:
                values.append(float(text))
            except ValueError as exc:
                raise EngineeringError(f"Foundation frequency row {row + 1}, {header}: expected a finite numeric value, received {text!r}.") from exc
        return values

    def _points(self) -> list[FoundationCoefficientPoint]:
        points: list[FoundationCoefficientPoint] = []
        for row in range(self.coefficients.rowCount()):
            values = self._row_values(row)
            points.append(FoundationCoefficientPoint(*values))
        return points

    def _sync_model_controls(self) -> None:
        model = self.model.currentData()
        scalar = model in {FoundationModel.LUMPED_KC, FoundationModel.LUMPED_KCM}
        mass = model == FoundationModel.LUMPED_KCM
        frequency = model == FoundationModel.FREQUENCY_DEPENDENT_KC
        self.mass.setEnabled(mass)
        for widget in (self.kxx, self.kxy, self.kyx, self.kyy, self.cxx, self.cxy, self.cyx, self.cyy):
            widget.setEnabled(scalar)
        self.coefficients.setEnabled(frequency)
        self.add_frequency_row.setEnabled(frequency)
        self.remove_frequency_row.setEnabled(frequency)

    def record(self) -> FoundationSpec:
        model = self.model.currentData()
        if not isinstance(model, FoundationModel):
            model = FoundationModel(str(model))
        scalar = model in {FoundationModel.LUMPED_KC, FoundationModel.LUMPED_KCM}
        record = FoundationSpec(
            name=self.name.text().strip(),
            support_index=int(self.support.currentData()),
            model_type=model,
            mass_kg=self.mass.value() if model == FoundationModel.LUMPED_KCM else 0.0,
            dof=2,
            kxx=self.kxx.value() if scalar else 0.0,
            kyy=self.kyy.value() if scalar else 0.0,
            kxy=self.kxy.value() if scalar else 0.0,
            kyx=self.kyx.value() if scalar else 0.0,
            cxx=self.cxx.value() if scalar else 0.0,
            cyy=self.cyy.value() if scalar else 0.0,
            cxy=self.cxy.value() if scalar else 0.0,
            cyx=self.cyx.value() if scalar else 0.0,
            coefficients=self._points() if model == FoundationModel.FREQUENCY_DEPENDENT_KC else [],
            metadata={"source": "Foundation Studio 0.24"},
            status=AdapterStatus.VALIDATED,
        )
        record.validate()
        return record

    def _accept_if_parseable(self) -> None:
        try:
            self.record()
        except EngineeringError as exc:
            QMessageBox.critical(self, "Foundation input rejected", str(exc))
            return
        self.accept()


class FoundationWorkspacePage(QWidget):
    """Editable Foundation Studio using strict preview→commit transactions."""

    status_message = Signal(str)

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.mutations = RotorModelMutationService()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = Card()
        header_layout = QVBoxLayout(header)
        title = QLabel("Foundation Studio 0.24")
        title.setObjectName("cardHeader")
        header_layout.addWidget(title)
        subtitle = QLabel(
            "Model the structural path below each flexible support. Every Add/Edit/Delete is validated as a complete "
            "RotorProject and assembled by ROSS before commit. No nearest-node mapping and no silent 6-DOF reduction."
        )
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        topology = SectionCard("Physical topology")
        topology_label = QLabel(
            "shaft node → bearing → support node [Msupport] → support K/C → foundation node [Mfoundation] → foundation K/C → ground"
        )
        topology_label.setWordWrap(True)
        topology.root.addWidget(topology_label)
        root.addWidget(topology)

        action_row = QHBoxLayout()
        self.add_button = QPushButton("Add Foundation")
        self.edit_button = QPushButton("Edit")
        self.delete_button = QPushButton("Delete")
        action_row.addWidget(self.add_button)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Support owner", "Bearing station", "Model", "Mass (kg)", "Kxx", "Kyy", "Cxx", "Frequency rows"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.audit = QLabel()
        self.audit.setObjectName("muted")
        self.audit.setWordWrap(True)
        root.addWidget(self.audit)

        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._selection_state)
        self._refresh()

    @property
    def engineering(self):
        if self.project.engineering is None:
            raise EngineeringError("Foundation Studio requires an engineering RotorProject.")
        return self.project.engineering

    def _selected_index(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _unused_support(self, *, excluding_foundation_index: int | None = None) -> int | None:
        used = {
            foundation.support_index
            for index, foundation in enumerate(self.engineering.foundations)
            if index != excluding_foundation_index
        }
        return next((index for index in range(len(self.engineering.supports)) if index not in used), None)

    def _refresh(self) -> None:
        project = self.engineering
        self.table.setRowCount(len(project.foundations))
        for row, foundation in enumerate(project.foundations):
            support = project.supports[foundation.support_index]
            bearing = project.bearings[support.bearing_index]
            scalar = foundation.model_type in {FoundationModel.LUMPED_KC, FoundationModel.LUMPED_KCM}
            values = [
                foundation.name,
                support.name,
                f"{bearing.name} @ {bearing.position_mm:g} mm",
                _MODEL_LABELS.get(foundation.model_type, foundation.model_type.value),
                f"{foundation.mass_kg:.6g}",
                f"{foundation.kxx:.6g}" if scalar else "—",
                f"{foundation.kyy:.6g}" if scalar else "—",
                f"{foundation.cxx:.6g}" if scalar else "—",
                str(len(foundation.coefficients)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if self.table.rowCount():
            self.table.selectRow(min(self.table.currentRow() if self.table.currentRow() >= 0 else 0, self.table.rowCount() - 1))
        self.audit.setText(
            f"Supports: {len(project.supports)} · Foundations: {len(project.foundations)} · "
            f"schema contract: 2-DOF only · exact ownership by support_index · strict ROSS preview required"
        )
        self._selection_state()

    def _selection_state(self) -> None:
        selected = self._selected_index() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)
        self.add_button.setEnabled(self._unused_support() is not None)
        if not self.add_button.isEnabled():
            self.add_button.setToolTip("Every flexible support already owns one FoundationSpec.")
        else:
            self.add_button.setToolTip("")

    @staticmethod
    def _changes(record: FoundationSpec) -> dict[str, object]:
        return {
            "name": record.name,
            "support_index": record.support_index,
            "model_type": record.model_type,
            "mass_kg": record.mass_kg,
            "dof": record.dof,
            "kxx": record.kxx,
            "kyy": record.kyy,
            "kxy": record.kxy,
            "kyx": record.kyx,
            "cxx": record.cxx,
            "cyy": record.cyy,
            "cxy": record.cxy,
            "cyx": record.cyx,
            "coefficients": deepcopy(record.coefficients),
            "metadata": deepcopy(record.metadata),
            "status": record.status,
        }

    def _commit_preview(self, preview) -> None:
        audit = self.mutations.commit(self.engineering, preview)
        self.project.touch()
        self._refresh()
        text = (
            f"Foundation {audit.operation} committed · foundations {audit.before_count}→{audit.after_count} · "
            f"ROSS shaft elements {audit.shaft_elements} · support links {dict(audit.support_links)}"
        )
        self.audit.setText(text)
        self.status_message.emit(text)

    def _add(self) -> None:
        support_index = self._unused_support()
        if support_index is None:
            QMessageBox.information(self, "Foundation Studio", "Every flexible support already owns a foundation.")
            return
        dialog = FoundationEditorDialog(self.project, default_support_index=support_index, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            preview = self.mutations.preview_add(self.engineering, "foundation", dialog.record())
            self._commit_preview(preview)
        except Exception as exc:
            QMessageBox.critical(self, "Foundation transaction rejected", str(exc))

    def _edit(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        source = self.engineering.foundations[index]
        dialog = FoundationEditorDialog(self.project, source, default_support_index=source.support_index, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            preview = self.mutations.preview_update(self.engineering, "foundation", index, self._changes(dialog.record()))
            self._commit_preview(preview)
            self.table.selectRow(index)
        except Exception as exc:
            QMessageBox.critical(self, "Foundation transaction rejected", str(exc))

    def _delete(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        foundation = self.engineering.foundations[index]
        answer = QMessageBox.question(
            self,
            "Delete Foundation",
            f"Delete {foundation.name!r}? The owning flexible support is preserved and returns to its qualified direct-to-ground topology.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            preview = self.mutations.preview_delete(self.engineering, "foundation", index)
            self._commit_preview(preview)
        except Exception as exc:
            QMessageBox.critical(self, "Foundation transaction rejected", str(exc))


__all__ = ["FoundationEditorDialog", "FoundationWorkspacePage"]
