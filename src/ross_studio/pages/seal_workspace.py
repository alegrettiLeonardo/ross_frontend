from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..domain import SealModel
from ..models import ProjectModel
from ..plotly_native_view import NativeRossFigureView
from ..ross_backend import RossBackend
from ..seal_studio_service import SealCalculationResult, SealStudioService
from ..widgets import Card, SectionCard, configure_table


_DEFAULTS: dict[SealModel, dict[str, Any]] = {
    SealModel.DIRECT: {
        "kxx": 1.0e6, "kyy": 1.0e6, "kxy": 0.0, "kyx": 0.0,
        "cxx": 1.0e3, "cyy": 1.0e3, "cxy": 0.0, "cyx": 0.0,
    },
    SealModel.LABYRINTH: {
        "shaft_diameter_mm": 145.0, "radial_clearance_mm": 0.30, "n_teeth": 16,
        "pitch_mm": 3.175, "tooth_height_mm": 3.175, "tooth_width_mm": 0.1524,
        "seal_type": "inter", "inlet_pressure_pa": 308000.0, "outlet_pressure_pa": 94300.0,
        "inlet_temperature_k": 283.15, "frequency_rpm": [5000.0, 8000.0, 11000.0],
        "preswirl": 0.98, "gas_composition": {"Nitrogen": 0.79, "Oxygen": 0.21},
        "use_jenny_kanki": False,
    },
    SealModel.HOLE_PATTERN: {
        "shaft_diameter_mm": 196.5, "radial_clearance_mm": 0.18, "axial_length_mm": 84.9,
        "relative_roughness": 1.0e-4, "cell_length_mm": 2.2946, "cell_width_mm": 2.1,
        "cell_depth_mm": 2.8, "inlet_pressure_pa": 1_830_000.0, "outlet_pressure_pa": 823_500.0,
        "inlet_temperature_k": 300.0, "frequency_rpm": [5000.0], "preswirl": 1.0,
        "entrance_loss_coefficient": 0.1, "exit_loss_coefficient": 0.5, "excitation_ratio": 1.0,
        "nz": 40, "max_iterations": 180, "tolerance": 1e-4, "first_step_size": 0.01,
        "relaxation_factor": 0.1,
        "gas_composition": {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092},
    },
    SealModel.HYBRID: {
        "shaft_diameter_mm": 50.0, "inlet_pressure_pa": 500000.0, "outlet_pressure_pa": 100000.0,
        "inlet_temperature_k": 300.0, "frequency_rpm": [2000.0, 3000.0, 5000.0],
        "gas_composition": {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092},
        "hole_radial_clearance_mm": 0.30, "hole_axial_length_mm": 40.0,
        "hole_relative_roughness": 1e-4, "hole_cell_length_mm": 3.0, "hole_cell_width_mm": 3.0,
        "hole_cell_depth_mm": 2.0, "hole_preswirl": 0.8,
        "hole_entrance_loss_coefficient": 0.5, "hole_exit_loss_coefficient": 1.0,
        "lab_radial_clearance_mm": 0.25, "lab_n_teeth": 10, "lab_pitch_mm": 3.0,
        "lab_tooth_height_mm": 3.0, "lab_tooth_width_mm": 0.15, "lab_seal_type": "inter",
        "lab_preswirl": 0.9, "tolerance": 1e-6, "max_iterations": 100,
    },
}


def _encode(value: Any) -> str:
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _decode(text: str) -> Any:
    value = text.strip()
    if not value:
        return ""
    if value[0] in "[{" or value.casefold() in {"true", "false", "null"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    try:
        if any(token in value.casefold() for token in (".", "e")):
            return float(value)
        return int(value)
    except ValueError:
        return value


class SealStudioPage(QWidget):
    """Preview → Apply workspace for native ROSS seal models."""

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = SealStudioService()
        self.preview: SealCalculationResult | None = None
        self.figures: dict[str, Any] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = Card()
        h = QVBoxLayout(header)
        title = QLabel("Seal Studio · Native ROSS")
        title.setObjectName("cardHeader")
        h.addWidget(title)
        note = QLabel(
            "Direct K/C, LabyrinthSeal, HolePatternSeal and HybridSeal. Calculate is preview-only; "
            "Apply persists the native-model origin and engineering inputs, then qualifies a strict ROSS Rotor."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        h.addWidget(note)
        root.addWidget(header)

        setup = SectionCard("Seal model and physical inputs")
        row = QHBoxLayout()
        row.addWidget(QLabel("Physical seal"))
        self.seal = QComboBox()
        engineering = self.project.engineering
        if engineering is not None:
            for index, spec in enumerate(engineering.seals):
                self.seal.addItem(f"#{index + 1} {spec.name} · x={spec.position_mm:g} mm", index)
        row.addWidget(self.seal, 1)
        row.addWidget(QLabel("ROSS model"))
        self.model = QComboBox()
        for model in SealModel:
            self.model.addItem(model.value.replace("_", " ").title(), model.value)
        row.addWidget(self.model)
        setup.root.addLayout(row)

        self.parameters = QTableWidget(0, 2)
        self.parameters.setHorizontalHeaderLabels(["Engineering parameter", "Value"])
        configure_table(self.parameters, row_height=30)
        setup.root.addWidget(self.parameters)

        actions = QHBoxLayout()
        self.calculate = QPushButton("Calculate / Preview")
        self.calculate.setObjectName("primaryButton")
        self.apply = QPushButton("Apply to Rotor")
        self.apply.setEnabled(False)
        actions.addWidget(self.calculate)
        actions.addWidget(self.apply)
        actions.addStretch(1)
        self.state = QLabel("Preview: empty")
        self.state.setObjectName("muted")
        actions.addWidget(self.state)
        setup.root.addLayout(actions)
        root.addWidget(setup, 2)

        results = SectionCard("Native ROSS outputs")
        self.tabs = QTabWidget()
        summary = QWidget()
        summary_layout = QVBoxLayout(summary)
        self.summary = QLabel("Calculate a seal to expose K/C, leakage, pressure and convergence outputs.")
        self.summary.setWordWrap(True)
        summary_layout.addWidget(self.summary)
        self.kc = QTableWidget(0, 10)
        self.kc.setHorizontalHeaderLabels(["rpm", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy", "Leakage kg/s"])
        configure_table(self.kc, row_height=28)
        summary_layout.addWidget(self.kc)
        self.tabs.addTab(summary, "Summary / K-C / Leakage")

        plot_page = QWidget()
        plot_layout = QVBoxLayout(plot_page)
        chooser = QHBoxLayout()
        chooser.addWidget(QLabel("Native plot"))
        self.plot_choice = QComboBox()
        chooser.addWidget(self.plot_choice, 1)
        plot_layout.addLayout(chooser)
        self.plot = NativeRossFigureView()
        plot_layout.addWidget(self.plot, 1)
        self.tabs.addTab(plot_page, "Pressure / Convergence / Coefficients")
        results.root.addWidget(self.tabs)
        root.addWidget(results, 3)

        self.model.currentIndexChanged.connect(self._load_inputs)
        self.seal.currentIndexChanged.connect(self._load_existing)
        self.calculate.clicked.connect(self._calculate)
        self.apply.clicked.connect(self._apply)
        self.plot_choice.currentIndexChanged.connect(self._show_plot)
        self._load_existing()

    def _engineering(self):
        if self.project.engineering is None:
            raise RuntimeError("Seal Studio requires a loaded engineering RotorProject.")
        return self.project.engineering

    def _current_model(self) -> SealModel:
        return SealModel(str(self.model.currentData()))

    def _load_existing(self) -> None:
        engineering = self.project.engineering
        if engineering is None or not engineering.seals:
            self.parameters.setRowCount(0)
            self.calculate.setEnabled(False)
            self.apply.setEnabled(False)
            self.state.setText("No physical seal exists in the rotor model.")
            return
        self.calculate.setEnabled(True)
        spec = engineering.seals[int(self.seal.currentData() or 0)]
        row = self.model.findData(spec.model.value if isinstance(spec.model, SealModel) else str(spec.model))
        if row >= 0:
            self.model.blockSignals(True)
            self.model.setCurrentIndex(row)
            self.model.blockSignals(False)
        self._load_inputs()

    def _load_inputs(self) -> None:
        engineering = self.project.engineering
        if engineering is None or not engineering.seals:
            return
        spec = engineering.seals[int(self.seal.currentData() or 0)]
        model = self._current_model()
        existing = spec.metadata.get("engineering_input") if getattr(spec, "model", None) == model else None
        values = dict(existing) if isinstance(existing, dict) else dict(_DEFAULTS[model])
        if model is SealModel.DIRECT:
            values.update({key: getattr(spec, key) for key in ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx")})
        self.parameters.setRowCount(len(values))
        for row, (key, value) in enumerate(values.items()):
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.parameters.setItem(row, 0, key_item)
            self.parameters.setItem(row, 1, QTableWidgetItem(_encode(value)))
        self.parameters.resizeColumnsToContents()
        self.preview = None
        self.apply.setEnabled(False)
        self.state.setText("Preview: inputs changed")

    def _input_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in range(self.parameters.rowCount()):
            key = self.parameters.item(row, 0).text().strip()
            result[key] = _decode(self.parameters.item(row, 1).text())
        return result

    def _calculate(self) -> None:
        try:
            engineering = self._engineering()
            index = int(self.seal.currentData())
            result = self.service.calculate(deepcopy(engineering), index, self._current_model(), self._input_values())
        except Exception as exc:
            self.preview = None
            self.apply.setEnabled(False)
            self.state.setText(f"Preview failed: {exc}")
            return
        self.preview = result
        self.apply.setEnabled(True)
        self.state.setText(f"Preview ready · {result.source_model.value}")
        interface = "" if result.interface_pressure_pa is None else f" · interface={result.interface_pressure_pa:,.3f} Pa"
        iterations = "" if result.iterations is None else f" · iterations={result.iterations}"
        self.summary.setText(result.note + interface + iterations)
        self.kc.setRowCount(len(result.coefficients))
        for row, point in enumerate(result.coefficients):
            leakage = result.leakage_kg_s[min(row, len(result.leakage_kg_s) - 1)] if result.leakage_kg_s else float("nan")
            values = (point.rpm, point.kxx, point.kxy, point.kyx, point.kyy, point.cxx, point.cxy, point.cyx, point.cyy, leakage)
            for col, value in enumerate(values):
                self.kc.setItem(row, col, QTableWidgetItem(f"{value:.8g}"))
        self.kc.resizeColumnsToContents()
        self._collect_figures(result.native_element)

    def _collect_figures(self, native: Any) -> None:
        self.figures.clear()
        self.plot_choice.clear()
        for label, coefficients in (("Stiffness K vs frequency", ["kxx", "kyy", "kxy", "kyx"]), ("Damping C vs frequency", ["cxx", "cyy", "cxy", "cyx"])):
            try:
                self.figures[label] = native.plot(coefficients=coefficients, frequency_units="RPM")
            except Exception:
                pass
        if hasattr(native, "plot_pressure_distribution"):
            try:
                self.figures["Pressure distribution"] = native.plot_pressure_distribution(pressure_units="MPa", length_units="mm")
            except Exception:
                pass
        if hasattr(native, "plot_convergence"):
            try:
                self.figures["Hybrid convergence"] = native.plot_convergence()
            except Exception:
                pass
        self.plot_choice.addItems(list(self.figures))
        if self.figures:
            self._show_plot()
        else:
            self.plot.set_unavailable("This native ROSS seal exposes no compatible plot for the solved preview.")

    def _show_plot(self) -> None:
        figure = self.figures.get(self.plot_choice.currentText())
        if figure is not None:
            self.plot.set_figure(figure)

    def _apply(self) -> None:
        if self.preview is None:
            return
        try:
            engineering = self._engineering()
            index = int(self.seal.currentData())
            candidate = deepcopy(engineering)
            self.service.apply(candidate, index, self.preview)
            RossBackend().build_rotor(candidate, strict=True)
            engineering.seals[index] = deepcopy(candidate.seals[index])
        except Exception as exc:
            self.state.setText(f"Apply rejected by strict ROSS build: {exc}")
            return
        self.apply.setEnabled(False)
        self.state.setText("Applied · native seal reconstruction passed strict ROSS build")


__all__ = ["SealStudioPage"]
