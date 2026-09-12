from __future__ import annotations

from copy import deepcopy
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain import EngineeringError, SealSpec
from ..model_builder_service import RotorModelMutationService
from ..models import ProjectModel
from ..plotly_native_view import NativeRossFigureView
from ..seal_models import (
    HolePatternSealSpec,
    HolePatternStageSpec,
    HybridSealSpec,
    LabyrinthSealSpec,
    LabyrinthStageSpec,
    SealModel,
    seal_model,
)
from ..seal_studio import SealCalculationPreview, SealStudioService
from ..topology import NodeInsertionService
from ..widgets import Card, SectionCard


_MODEL_LABELS = {
    SealModel.DIRECT: "Direct K/C",
    SealModel.LABYRINTH: "Labyrinth",
    SealModel.HOLE_PATTERN: "Hole Pattern / Honeycomb",
    SealModel.HYBRID: "Hybrid · Hole Pattern + Labyrinth",
}


def _number(value: float = 0.0, *, minimum: float = -1.0e18, maximum: float = 1.0e18, decimals: int = 8) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(decimals)
    box.setRange(minimum, maximum)
    box.setValue(float(value))
    box.setKeyboardTracking(False)
    return box


def _csv(values) -> str:
    return ", ".join(f"{float(value):g}" for value in values)


def _air_json(values: dict[str, float] | None = None) -> str:
    composition = values or {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092}
    return json.dumps(composition, ensure_ascii=False)


class SealStudioEditorDialog(QDialog):
    """ROSS-native Calculate → Preview → Apply editor for all 0.25 seal families."""

    def __init__(self, project: ProjectModel, seal: SealSpec | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if project.engineering is None:
            raise EngineeringError("Seal Studio requires an engineering RotorProject.")
        self.project = project
        self.engineering = project.engineering
        self.service = SealStudioService()
        self._preview: SealCalculationPreview | None = None
        source = deepcopy(seal) if seal is not None else SealSpec(
            "Seal", 0.5 * self.engineering.total_length_mm, 0.0, 0.0, 0.0, 0.0
        )
        self._initial = source
        self.setWindowTitle("Add Seal" if seal is None else f"Edit Seal — {source.name}")
        self.resize(1180, 820)

        root = QVBoxLayout(self)
        note = QLabel(
            "Seal Studio does not implement a parallel seal solver. Calculate instantiates the native ROSS 2.3.0 "
            "SealElement, LabyrinthSeal, HolePatternSeal or HybridSeal. Preview retains native ROSS plots/results; "
            "Apply stores the physical inputs plus the calculated K/C/M table and then performs a strict full-rotor ROSS build."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        body = QHBoxLayout()
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_host = QWidget()
        editor_root = QVBoxLayout(editor_host)
        editor_scroll.setWidget(editor_host)
        body.addWidget(editor_scroll, 5)

        common = SectionCard("Seal definition")
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _number(source.position_mm, minimum=0.0, maximum=max(1.0, self.engineering.total_length_mm), decimals=4)
        self.model = QComboBox()
        for value, label in _MODEL_LABELS.items():
            self.model.addItem(label, value)
        current_model = seal_model(source)
        self.model.setCurrentIndex(max(0, self.model.findData(current_model)))
        frequencies = getattr(source, "frequency_rpm", [5000.0])
        self.frequency = QLineEdit(_csv(frequencies))
        self.frequency.setToolTip("Comma-separated shaft/whirl speed samples in RPM; converted to rad/s only at the ROSS boundary.")
        gas = getattr(source, "gas_composition", {})
        self.use_gas = QCheckBox("Use gas composition / ROSS thermodynamic backend")
        self.use_gas.setChecked(bool(gas) if seal is not None and current_model != SealModel.DIRECT else True)
        self.gas = QLineEdit(_air_json(gas or None))
        self.molar = _number(float(getattr(source, "molar_kg_kmol", None) or 28.96807), minimum=1e-9)
        self.gamma = _number(float(getattr(source, "gamma", None) or 1.4), minimum=1e-9)
        form.addRow("Name", self.name)
        form.addRow("Axial position (mm)", self.position)
        form.addRow("ROSS seal model", self.model)
        form.addRow("Frequency samples (RPM)", self.frequency)
        form.addRow("Gas property mode", self.use_gas)
        form.addRow("Gas composition JSON", self.gas)
        form.addRow("Manual molar (kg/kmol)", self.molar)
        form.addRow("Manual gamma", self.gamma)
        common.root.addLayout(form)
        editor_root.addWidget(common)

        self.panels = QStackedWidget()
        self.panels.addWidget(self._direct_panel(source))
        self.panels.addWidget(self._labyrinth_panel(source))
        self.panels.addWidget(self._hole_panel(source))
        self.panels.addWidget(self._hybrid_panel(source))
        editor_root.addWidget(self.panels)
        editor_root.addStretch(1)

        preview = QWidget()
        preview_root = QVBoxLayout(preview)
        self.summary = QLabel("No calculation yet. Calculate must succeed before Apply.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        preview_root.addWidget(self.summary)
        self.coefficients = QTableWidget(0, 13)
        self.coefficients.setHorizontalHeaderLabels(
            ["RPM", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy", "Mxx", "Mxy", "Myx", "Myy"]
        )
        self.coefficients.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.coefficients.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        preview_root.addWidget(self.coefficients, 2)
        self.plot_tabs = QTabWidget()
        self.k_view = NativeRossFigureView()
        self.c_view = NativeRossFigureView()
        self.aux_view = NativeRossFigureView()
        self.plot_tabs.addTab(self.k_view, "ROSS K")
        self.plot_tabs.addTab(self.c_view, "ROSS C")
        self.plot_tabs.addTab(self.aux_view, "Pressure / Convergence")
        preview_root.addWidget(self.plot_tabs, 5)
        body.addWidget(preview, 6)
        root.addLayout(body, 1)

        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.calculate_button = actions.addButton("Calculate with ROSS", QDialogButtonBox.ButtonRole.ActionRole)
        self.apply_button = actions.button(QDialogButtonBox.StandardButton.Ok)
        self.apply_button.setText("Apply")
        self.apply_button.setEnabled(False)
        self.calculate_button.clicked.connect(self._calculate)
        actions.accepted.connect(self._accept_preview)
        actions.rejected.connect(self.reject)
        root.addWidget(actions)

        self.model.currentIndexChanged.connect(self._sync_model)
        self.use_gas.toggled.connect(self._sync_gas)
        self._sync_model()
        self._sync_gas()

    def _direct_panel(self, source: SealSpec) -> QWidget:
        page = SectionCard("Direct SealElement K/C")
        self.kxx = _number(source.kxx)
        self.kyy = _number(source.kyy)
        self.kxy = _number(source.kxy)
        self.kyx = _number(source.kyx)
        self.cxx = _number(source.cxx)
        self.cyy = _number(source.cyy)
        self.cxy = _number(source.cxy)
        self.cyx = _number(source.cyx)
        form = QFormLayout()
        for label, widget in (
            ("Kxx (N/m)", self.kxx), ("Kyy (N/m)", self.kyy), ("Kxy (N/m)", self.kxy), ("Kyx (N/m)", self.kyx),
            ("Cxx (N·s/m)", self.cxx), ("Cyy (N·s/m)", self.cyy), ("Cxy (N·s/m)", self.cxy), ("Cyx (N·s/m)", self.cyx),
        ):
            form.addRow(label, widget)
        page.root.addLayout(form)
        return page

    def _labyrinth_panel(self, source: SealSpec) -> QWidget:
        value = source if isinstance(source, LabyrinthSealSpec) else LabyrinthSealSpec("Labyrinth", source.position_mm, 0, 0, 0, 0)
        page = SectionCard("LabyrinthSeal · native ROSS inputs")
        form = QFormLayout()
        self.lab_radius = _number(value.shaft_radius_m * 1000, minimum=1e-9)
        self.lab_clearance = _number(value.radial_clearance_m * 1000, minimum=1e-9)
        self.lab_teeth = QSpinBox(); self.lab_teeth.setRange(1, 30); self.lab_teeth.setValue(value.n_teeth)
        self.lab_pitch = _number(value.pitch_m * 1000, minimum=1e-9)
        self.lab_tooth_h = _number(value.tooth_height_m * 1000, minimum=1e-9)
        self.lab_tooth_w = _number(value.tooth_width_m * 1000, minimum=1e-9)
        self.lab_type = QComboBox(); [self.lab_type.addItem(item) for item in ("rotor", "stator", "inter")]; self.lab_type.setCurrentText(value.seal_type)
        self.lab_pin = _number(value.inlet_pressure_pa, minimum=1e-9)
        self.lab_pout = _number(value.outlet_pressure_pa, minimum=1e-9)
        self.lab_temp = _number(value.inlet_temperature_k, minimum=1e-9)
        self.lab_preswirl = _number(value.preswirl)
        tz = value.tz_k or (value.inlet_temperature_k, value.inlet_temperature_k - 0.5)
        mu = value.muz_pa_s or (1.85e-5, 1.84e-5)
        self.lab_tz1 = _number(tz[0], minimum=1e-9); self.lab_tz2 = _number(tz[1], minimum=1e-9)
        self.lab_mu1 = _number(mu[0], minimum=1e-12, decimals=12); self.lab_mu2 = _number(mu[1], minimum=1e-12, decimals=12)
        for label, widget in (
            ("Shaft radius (mm)", self.lab_radius), ("Radial clearance (mm)", self.lab_clearance), ("Number of teeth", self.lab_teeth),
            ("Pitch (mm)", self.lab_pitch), ("Tooth height (mm)", self.lab_tooth_h), ("Tooth width (mm)", self.lab_tooth_w),
            ("Seal type", self.lab_type), ("Inlet pressure (Pa)", self.lab_pin), ("Outlet pressure (Pa)", self.lab_pout),
            ("Inlet temperature (K)", self.lab_temp), ("Preswirl", self.lab_preswirl), ("Manual Tz inlet (K)", self.lab_tz1),
            ("Manual Tz outlet (K)", self.lab_tz2), ("Manual μ inlet (Pa·s)", self.lab_mu1), ("Manual μ outlet (Pa·s)", self.lab_mu2),
        ):
            form.addRow(label, widget)
        page.root.addLayout(form)
        return page

    def _hole_panel(self, source: SealSpec) -> QWidget:
        value = source if isinstance(source, HolePatternSealSpec) else HolePatternSealSpec("Hole Pattern", source.position_mm, 0, 0, 0, 0)
        page = SectionCard("HolePatternSeal · native ROSS inputs")
        form = QFormLayout()
        self.hp_radius = _number(value.shaft_radius_m * 1000, minimum=1e-9)
        self.hp_clearance = _number(value.radial_clearance_m * 1000, minimum=1e-9)
        self.hp_length = _number(value.length_m * 1000, minimum=1e-9)
        self.hp_roughness = _number(value.roughness, minimum=0.0)
        self.hp_cell_l = _number(value.cell_length_m * 1000, minimum=1e-9)
        self.hp_cell_w = _number(value.cell_width_m * 1000, minimum=1e-9)
        self.hp_cell_d = _number(value.cell_depth_m * 1000, minimum=1e-9)
        self.hp_pin = _number(value.inlet_pressure_pa, minimum=1e-9)
        self.hp_pout = _number(value.outlet_pressure_pa, minimum=1e-9)
        self.hp_temp = _number(value.inlet_temperature_k, minimum=1e-9)
        self.hp_preswirl = _number(value.preswirl)
        self.hp_entr = _number(value.entr_coef); self.hp_exit = _number(value.exit_coef)
        self.hp_nz = QSpinBox(); self.hp_nz.setRange(4, 1000); self.hp_nz.setValue(value.nz)
        self.hp_b = _number(value.b_suther or 1.458e-6, minimum=1e-12, decimals=12)
        self.hp_s = _number(value.s_suther or 110.4, minimum=1e-9)
        for label, widget in (
            ("Shaft radius (mm)", self.hp_radius), ("Radial clearance (mm)", self.hp_clearance), ("Seal length (mm)", self.hp_length),
            ("Roughness E/D", self.hp_roughness), ("Cell length (mm)", self.hp_cell_l), ("Cell width (mm)", self.hp_cell_w),
            ("Cell depth (mm)", self.hp_cell_d), ("Inlet pressure (Pa)", self.hp_pin), ("Outlet pressure (Pa)", self.hp_pout),
            ("Inlet temperature (K)", self.hp_temp), ("Preswirl", self.hp_preswirl), ("Entrance coefficient", self.hp_entr),
            ("Exit coefficient", self.hp_exit), ("Axial grid nz", self.hp_nz), ("Manual Sutherland B", self.hp_b), ("Manual Sutherland S", self.hp_s),
        ):
            form.addRow(label, widget)
        page.root.addLayout(form)
        return page

    def _hybrid_panel(self, source: SealSpec) -> QWidget:
        value = source if isinstance(source, HybridSealSpec) else HybridSealSpec("Hybrid", source.position_mm, 0, 0, 0, 0)
        page = SectionCard("HybridSeal · native ROSS series stages")
        form = QFormLayout()
        self.hy_radius = _number(value.shaft_radius_m * 1000, minimum=1e-9)
        self.hy_pin = _number(value.inlet_pressure_pa, minimum=1e-9); self.hy_pout = _number(value.outlet_pressure_pa, minimum=1e-9)
        self.hy_temp = _number(value.inlet_temperature_k, minimum=1e-9)
        hp = value.hole_pattern; lab = value.labyrinth
        self.hy_hp_clearance = _number(hp.radial_clearance_m * 1000, minimum=1e-9); self.hy_hp_length = _number(hp.length_m * 1000, minimum=1e-9)
        self.hy_hp_rough = _number(hp.roughness, minimum=0.0); self.hy_hp_cell_l = _number(hp.cell_length_m * 1000, minimum=1e-9)
        self.hy_hp_cell_w = _number(hp.cell_width_m * 1000, minimum=1e-9); self.hy_hp_cell_d = _number(hp.cell_depth_m * 1000, minimum=1e-9)
        self.hy_hp_preswirl = _number(hp.preswirl); self.hy_hp_entr = _number(hp.entr_coef); self.hy_hp_exit = _number(hp.exit_coef)
        self.hy_hp_nz = QSpinBox(); self.hy_hp_nz.setRange(4, 1000); self.hy_hp_nz.setValue(hp.nz)
        self.hy_hp_b = _number(hp.b_suther or 1.458e-6, minimum=1e-12, decimals=12); self.hy_hp_s = _number(hp.s_suther or 110.4, minimum=1e-9)
        self.hy_lab_clearance = _number(lab.radial_clearance_m * 1000, minimum=1e-9)
        self.hy_lab_teeth = QSpinBox(); self.hy_lab_teeth.setRange(1, 30); self.hy_lab_teeth.setValue(lab.n_teeth)
        self.hy_lab_pitch = _number(lab.pitch_m * 1000, minimum=1e-9); self.hy_lab_h = _number(lab.tooth_height_m * 1000, minimum=1e-9); self.hy_lab_w = _number(lab.tooth_width_m * 1000, minimum=1e-9)
        self.hy_lab_type = QComboBox(); [self.hy_lab_type.addItem(item) for item in ("rotor", "stator", "inter")]; self.hy_lab_type.setCurrentText(lab.seal_type)
        self.hy_lab_preswirl = _number(lab.preswirl)
        tz = lab.tz_k or (value.inlet_temperature_k, value.inlet_temperature_k - 0.5); mu = lab.muz_pa_s or (1.85e-5, 1.84e-5)
        self.hy_lab_tz1 = _number(tz[0], minimum=1e-9); self.hy_lab_tz2 = _number(tz[1], minimum=1e-9)
        self.hy_lab_mu1 = _number(mu[0], minimum=1e-12, decimals=12); self.hy_lab_mu2 = _number(mu[1], minimum=1e-12, decimals=12)
        self.hy_tol = _number(value.pressure_match_tolerance, minimum=1e-12, maximum=1.0, decimals=12)
        self.hy_iter = QSpinBox(); self.hy_iter.setRange(1, 10000); self.hy_iter.setValue(value.pressure_match_max_iterations)
        for label, widget in (
            ("Shaft radius (mm)", self.hy_radius), ("Global inlet pressure (Pa)", self.hy_pin), ("Global outlet pressure (Pa)", self.hy_pout), ("Inlet temperature (K)", self.hy_temp),
            ("HP radial clearance (mm)", self.hy_hp_clearance), ("HP length (mm)", self.hy_hp_length), ("HP roughness E/D", self.hy_hp_rough), ("HP cell length (mm)", self.hy_hp_cell_l),
            ("HP cell width (mm)", self.hy_hp_cell_w), ("HP cell depth (mm)", self.hy_hp_cell_d), ("HP preswirl", self.hy_hp_preswirl), ("HP entrance coef.", self.hy_hp_entr),
            ("HP exit coef.", self.hy_hp_exit), ("HP axial grid nz", self.hy_hp_nz), ("HP manual Sutherland B", self.hy_hp_b), ("HP manual Sutherland S", self.hy_hp_s),
            ("Lab radial clearance (mm)", self.hy_lab_clearance), ("Lab teeth", self.hy_lab_teeth), ("Lab pitch (mm)", self.hy_lab_pitch), ("Lab tooth height (mm)", self.hy_lab_h),
            ("Lab tooth width (mm)", self.hy_lab_w), ("Lab seal type", self.hy_lab_type), ("Lab preswirl", self.hy_lab_preswirl), ("Lab manual Tz inlet (K)", self.hy_lab_tz1),
            ("Lab manual Tz outlet (K)", self.hy_lab_tz2), ("Lab manual μ inlet", self.hy_lab_mu1), ("Lab manual μ outlet", self.hy_lab_mu2),
            ("Pressure-match tolerance", self.hy_tol), ("Pressure-match max iterations", self.hy_iter),
        ):
            form.addRow(label, widget)
        page.root.addLayout(form)
        return page

    def _sync_model(self) -> None:
        model = self.model.currentData()
        order = [SealModel.DIRECT, SealModel.LABYRINTH, SealModel.HOLE_PATTERN, SealModel.HYBRID]
        self.panels.setCurrentIndex(order.index(model))
        advanced = model != SealModel.DIRECT
        for widget in (self.frequency, self.use_gas, self.gas, self.molar, self.gamma):
            widget.setEnabled(advanced)
        self._preview = None
        self.apply_button.setEnabled(False)
        self.summary.setText("Inputs changed. Calculate with ROSS before Apply.")

    def _sync_gas(self) -> None:
        gas = self.use_gas.isChecked()
        self.gas.setEnabled(gas and self.model.currentData() != SealModel.DIRECT)
        self.molar.setEnabled(not gas and self.model.currentData() != SealModel.DIRECT)
        self.gamma.setEnabled(not gas and self.model.currentData() != SealModel.DIRECT)

    def _frequencies(self) -> list[float]:
        try:
            values = [float(token.strip()) for token in self.frequency.text().split(",") if token.strip()]
        except ValueError as exc:
            raise EngineeringError("Frequency samples must be comma-separated numeric RPM values.") from exc
        return values

    def _composition(self) -> dict[str, float]:
        if not self.use_gas.isChecked():
            return {}
        try:
            raw = json.loads(self.gas.text())
            if not isinstance(raw, dict):
                raise TypeError
            return {str(key): float(value) for key, value in raw.items()}
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise EngineeringError("Gas composition must be a JSON object such as {\"Nitrogen\": 0.79, \"Oxygen\": 0.21}.") from exc

    def record(self) -> SealSpec:
        name = self.name.text().strip()
        position = self.position.value()
        model = self.model.currentData()
        if model == SealModel.DIRECT:
            return SealSpec(name, position, self.kxx.value(), self.kyy.value(), self.cxx.value(), self.cyy.value(), self.kxy.value(), self.kyx.value(), self.cxy.value(), self.cyx.value())
        freq = self._frequencies(); gas = self._composition()
        molar = None if gas else self.molar.value(); gamma = None if gas else self.gamma.value()
        if model == SealModel.LABYRINTH:
            record = LabyrinthSealSpec(
                name, position, 0, 0, 0, 0,
                shaft_radius_m=self.lab_radius.value() / 1000.0, radial_clearance_m=self.lab_clearance.value() / 1000.0,
                n_teeth=self.lab_teeth.value(), pitch_m=self.lab_pitch.value() / 1000.0, tooth_height_m=self.lab_tooth_h.value() / 1000.0,
                tooth_width_m=self.lab_tooth_w.value() / 1000.0, seal_type=self.lab_type.currentText(), inlet_pressure_pa=self.lab_pin.value(),
                outlet_pressure_pa=self.lab_pout.value(), inlet_temperature_k=self.lab_temp.value(), frequency_rpm=freq, preswirl=self.lab_preswirl.value(),
                gas_composition=gas, molar_kg_kmol=molar, gamma=gamma,
                tz_k=None if gas else (self.lab_tz1.value(), self.lab_tz2.value()),
                muz_pa_s=None if gas else (self.lab_mu1.value(), self.lab_mu2.value()),
            )
        elif model == SealModel.HOLE_PATTERN:
            record = HolePatternSealSpec(
                name, position, 0, 0, 0, 0,
                shaft_radius_m=self.hp_radius.value() / 1000.0, radial_clearance_m=self.hp_clearance.value() / 1000.0,
                length_m=self.hp_length.value() / 1000.0, roughness=self.hp_roughness.value(), cell_length_m=self.hp_cell_l.value() / 1000.0,
                cell_width_m=self.hp_cell_w.value() / 1000.0, cell_depth_m=self.hp_cell_d.value() / 1000.0, inlet_pressure_pa=self.hp_pin.value(),
                outlet_pressure_pa=self.hp_pout.value(), inlet_temperature_k=self.hp_temp.value(), frequency_rpm=freq, gas_composition=gas,
                molar_kg_kmol=molar, gamma=gamma, b_suther=None if gas else self.hp_b.value(), s_suther=None if gas else self.hp_s.value(),
                preswirl=self.hp_preswirl.value(), entr_coef=self.hp_entr.value(), exit_coef=self.hp_exit.value(), nz=self.hp_nz.value(),
            )
        else:
            hp = HolePatternStageSpec(
                radial_clearance_m=self.hy_hp_clearance.value() / 1000.0, length_m=self.hy_hp_length.value() / 1000.0,
                roughness=self.hy_hp_rough.value(), cell_length_m=self.hy_hp_cell_l.value() / 1000.0, cell_width_m=self.hy_hp_cell_w.value() / 1000.0,
                cell_depth_m=self.hy_hp_cell_d.value() / 1000.0, preswirl=self.hy_hp_preswirl.value(), entr_coef=self.hy_hp_entr.value(), exit_coef=self.hy_hp_exit.value(),
                nz=self.hy_hp_nz.value(), b_suther=None if gas else self.hy_hp_b.value(), s_suther=None if gas else self.hy_hp_s.value(),
            )
            lab = LabyrinthStageSpec(
                radial_clearance_m=self.hy_lab_clearance.value() / 1000.0, n_teeth=self.hy_lab_teeth.value(), pitch_m=self.hy_lab_pitch.value() / 1000.0,
                tooth_height_m=self.hy_lab_h.value() / 1000.0, tooth_width_m=self.hy_lab_w.value() / 1000.0, seal_type=self.hy_lab_type.currentText(),
                preswirl=self.hy_lab_preswirl.value(), tz_k=None if gas else (self.hy_lab_tz1.value(), self.hy_lab_tz2.value()),
                muz_pa_s=None if gas else (self.hy_lab_mu1.value(), self.hy_lab_mu2.value()),
            )
            record = HybridSealSpec(
                name, position, 0, 0, 0, 0,
                shaft_radius_m=self.hy_radius.value() / 1000.0, inlet_pressure_pa=self.hy_pin.value(), outlet_pressure_pa=self.hy_pout.value(),
                inlet_temperature_k=self.hy_temp.value(), frequency_rpm=freq, gas_composition=gas, molar_kg_kmol=molar, gamma=gamma,
                hole_pattern=hp, labyrinth=lab, pressure_match_tolerance=self.hy_tol.value(), pressure_match_max_iterations=self.hy_iter.value(),
            )
        record.validate_inputs()
        return record

    def _fill_preview(self, preview: SealCalculationPreview) -> None:
        rows = preview.coefficients
        self.coefficients.setRowCount(len(rows))
        for row_index, point in enumerate(rows):
            values = (point.rpm, point.kxx, point.kxy, point.kyx, point.kyy, point.cxx, point.cxy, point.cyx, point.cyy, point.mxx, point.mxy, point.myx, point.myy)
            for column, value in enumerate(values):
                item = QTableWidgetItem(f"{value:.8g}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.coefficients.setItem(row_index, column, item)
        if preview.model == SealModel.DIRECT:
            self.summary.setText(f"ROSS SealElement · exact node {preview.node} · direct K/C ready for strict Apply")
            self.k_view.set_unavailable("Direct SealElement uses the entered constant K matrix.")
            self.c_view.set_unavailable("Direct SealElement uses the entered constant C matrix.")
            self.aux_view.set_unavailable("Direct K/C seal has no pressure/leakage flow solve.")
            return
        leakage = preview.leakage_kg_s
        leakage_text = "—" if not leakage else ", ".join(f"{value:.6g}" for value in leakage)
        extra = ""
        if preview.model == SealModel.HYBRID:
            extra = f" · Pint={preview.summary.get('interface_pressure_pa', 0):.6g} Pa · iterations={preview.summary.get('n_iterations', 0)}"
        self.summary.setText(
            f"{type(preview.native).__name__} · exact node {preview.node} · {len(rows)} frequency point(s) · leakage={leakage_text} kg/s{extra}"
        )
        self.k_view.set_figure(preview.native.plot(coefficients=["kxx", "kyy", "kxy", "kyx"], frequency_units="RPM"))
        self.c_view.set_figure(preview.native.plot(coefficients=["cxx", "cyy", "cxy", "cyx"], frequency_units="RPM"))
        if preview.model == SealModel.HYBRID:
            self.aux_view.set_figure(preview.native.plot_convergence())
        else:
            self.aux_view.set_figure(preview.native.plot_pressure_distribution(pressure_units="MPa", length_units="mm"))

    def _calculate(self) -> None:
        self.calculate_button.setEnabled(False)
        self.summary.setText("Running native ROSS seal calculation…")
        try:
            source = self.record()
            preview = self.service.calculate(self.engineering, source)
            self._fill_preview(preview)
        except Exception as exc:
            self._preview = None
            self.apply_button.setEnabled(False)
            self.summary.setText(f"ROSS calculation failed: {exc}")
            QMessageBox.critical(self, "Seal calculation failed", str(exc))
        else:
            self._preview = preview
            self.apply_button.setEnabled(True)
        finally:
            self.calculate_button.setEnabled(True)

    def _accept_preview(self) -> None:
        if self._preview is None:
            QMessageBox.warning(self, "Seal not calculated", "Calculate with ROSS before Apply.")
            return
        try:
            current = self.record()
        except EngineeringError as exc:
            QMessageBox.critical(self, "Seal input rejected", str(exc))
            return
        if current != self._preview.source:
            self._preview = None
            self.apply_button.setEnabled(False)
            QMessageBox.warning(self, "Preview stale", "Seal inputs changed after Calculate. Recalculate before Apply.")
            return
        self.accept()

    def prepared_record(self) -> SealSpec:
        if self._preview is None:
            raise EngineeringError("Seal Studio has no calculated preview to Apply.")
        return deepcopy(self._preview.prepared)

    @property
    def native_preview(self) -> SealCalculationPreview | None:
        return self._preview


class SealStudioWorkspacePage(QWidget):
    """Dedicated 0.25 workspace for native ROSS seal models."""

    status_message = Signal(str)

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.mutations = RotorModelMutationService()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = Card()
        hroot = QVBoxLayout(header)
        title = QLabel("Seal Studio 0.25 · Native ROSS")
        title.setObjectName("cardHeader")
        hroot.addWidget(title)
        subtitle = QLabel(
            "Direct K/C, LabyrinthSeal, HolePatternSeal and HybridSeal. Advanced models use the native ROSS flow solver only on Calculate; "
            "the project preserves both source inputs and native-derived K/C/M/leakage/convergence evidence."
        )
        subtitle.setWordWrap(True)
        hroot.addWidget(subtitle)
        root.addWidget(header)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add / Calculate Seal")
        self.edit_button = QPushButton("Edit / Recalculate")
        self.delete_button = QPushButton("Delete")
        actions.addWidget(self.add_button); actions.addWidget(self.edit_button); actions.addWidget(self.delete_button); actions.addStretch(1)
        root.addLayout(actions)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Name", "Model", "x (mm)", "ROSS Node", "Frequency rows", "Leakage (kg/s)", "Native source", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.audit = QLabel()
        self.audit.setWordWrap(True)
        self.audit.setObjectName("muted")
        root.addWidget(self.audit)

        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._selection_state)
        self._refresh()

    @property
    def engineering(self):
        if self.project.engineering is None:
            raise EngineeringError("Seal Studio requires an engineering RotorProject.")
        return self.project.engineering

    def _selected_index(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _refresh(self) -> None:
        engineering = self.engineering
        plan = NodeInsertionService.plan(engineering)
        self.table.setRowCount(len(engineering.seals))
        for row, spec in enumerate(engineering.seals):
            model = seal_model(spec)
            calculated = list(getattr(spec, "calculated_coefficients", []))
            calculation = getattr(spec, "calculation", {})
            leakage = calculation.get("leakage_kg_s", []) if isinstance(calculation, dict) else []
            leakage_text = "—" if not leakage else ", ".join(f"{float(value):.6g}" for value in leakage)
            values = [
                spec.name,
                _MODEL_LABELS[model],
                f"{spec.position_mm:g}",
                str(plan.node_for(spec.position_mm)),
                str(len(calculated)) if model != SealModel.DIRECT else "constant",
                leakage_text,
                "ROSS SealElement" if model == SealModel.DIRECT else str(calculation.get("ross_class", _MODEL_LABELS[model])),
                "Applied",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        if self.table.rowCount():
            self.table.selectRow(min(max(self.table.currentRow(), 0), self.table.rowCount() - 1))
        self.audit.setText(
            "Calculate → native ROSS object → Preview native K/C + pressure/convergence → strict transactional Apply. "
            "Advanced flow models are never silently rerun during unrelated rotor analyses."
        )
        self._selection_state()

    def _selection_state(self) -> None:
        selected = self._selected_index() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _apply_dialog(self, dialog: SealStudioEditorDialog, index: int | None) -> None:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            record = dialog.prepared_record()
            if index is None:
                preview = self.mutations.preview_add(self.engineering, "seal", record)
            else:
                preview = self.mutations.preview_replace(self.engineering, "seal", index, record)
            audit = self.mutations.commit(self.engineering, preview)
        except Exception as exc:
            QMessageBox.critical(self, "Seal Apply rejected", str(exc))
            self.status_message.emit(f"Seal Apply rejected: {exc}")
            return
        self.project.touch()
        self._refresh()
        row = len(self.engineering.seals) - 1 if index is None else index
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        self.status_message.emit(
            f"Seal {audit.operation} committed after native ROSS calculation and strict rotor assembly · {audit.shaft_elements} ShaftElements"
        )

    def _add(self) -> None:
        self._apply_dialog(SealStudioEditorDialog(self.project, parent=self), None)

    def _edit(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self._apply_dialog(SealStudioEditorDialog(self.project, self.engineering.seals[index], self), index)

    def _delete(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        spec = self.engineering.seals[index]
        answer = QMessageBox.question(
            self,
            "Delete Seal",
            f"Delete {spec.name!r}? The candidate rotor will be strictly rebuilt before commit.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            preview = self.mutations.preview_delete(self.engineering, "seal", index)
            self.mutations.commit(self.engineering, preview)
        except Exception as exc:
            QMessageBox.critical(self, "Seal delete rejected", str(exc))
            return
        self.project.touch()
        self._refresh()
        self.status_message.emit(f"Seal {spec.name!r} deleted after strict ROSS reassembly.")


__all__ = ["SealStudioEditorDialog", "SealStudioWorkspacePage"]
