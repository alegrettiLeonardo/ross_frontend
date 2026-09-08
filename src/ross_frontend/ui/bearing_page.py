from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..backends.ross.bearing_calculator import BearingCalculationResult
from ..domain import PlainJournalBearingSpec, RotorProject, TiltingPadBearingSpec
from .bearing_views import BearingFieldView, JournalPositionView
from .drawing import SimpleLineChart
from .icons import studio_icon
from .theme import P
from .widgets import BearingTypeButton, Card


class BearingWorker(QObject):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, spec):
        super().__init__()
        self.spec = spec

    @Slot()
    def run(self):
        try:
            from ..backends.ross.bearing_calculator import RossBearingCalculator

            result = RossBearingCalculator().calculate(self.spec, progress=self.progress.emit)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class LabeledInput(QWidget):
    def __init__(self, label: str, value: float, unit: str = "", decimals: int = 2, minimum=-1e12, maximum=1e12):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.label = QLabel(label)
        self.label.setMinimumWidth(105)
        lay.addWidget(self.label)
        self.edit = QDoubleSpinBox()
        self.edit.setDecimals(decimals)
        self.edit.setRange(minimum, maximum)
        self.edit.setValue(value)
        self.edit.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.edit.setMinimumWidth(82)
        lay.addWidget(self.edit, 1)
        self.unit = QLabel(unit)
        self.unit.setObjectName("Muted")
        self.unit.setFixedWidth(42)
        lay.addWidget(self.unit)


class BearingPage(QWidget):
    statusMessage = Signal(str, str, bool)
    projectChanged = Signal(object)

    def __init__(self, project: RotorProject):
        super().__init__()
        self.project = project
        self._selected_type = "tilting"
        self._thread: QThread | None = None
        self._worker: BearingWorker | None = None
        self._result: BearingCalculationResult | None = None
        self._result_row = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 0, 12, 12)
        root.setSpacing(12)
        center = QVBoxLayout()
        center.setSpacing(10)
        root.addLayout(center, 1)

        header = Card(margins=(12, 8, 12, 8))
        hh = QHBoxLayout()
        title = QLabel("Bearing Studio")
        title.setObjectName("CardTitle")
        hh.addWidget(title)
        crumb = QLabel("Model  /  Bearings  /  DE Journal Bearing")
        crumb.setObjectName("Muted")
        hh.addWidget(crumb)
        hh.addStretch(1)
        header.layout.addLayout(hh)
        center.addWidget(header)

        types = Card(margins=(12, 8, 12, 10))
        label = QLabel("Bearing Type")
        label.setObjectName("SmallHeader")
        types.layout.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(8)
        specs = [
            ("coefficient", "Coefficient K/C", "coefficient"),
            ("ball", "Ball Bearing", "ball"),
            ("roller", "Roller Bearing", "roller"),
            ("cylindrical", "Cylindrical", "cylindrical"),
            ("journal", "Plain Journal", "plain"),
            ("tilting", "Tilting Pad", "tilting"),
        ]
        self.type_buttons = {}
        for icon, text, key in specs:
            button = BearingTypeButton(icon, text)
            button.clicked.connect(lambda checked=False, k=key: self._type_changed(k))
            row.addWidget(button)
            self.type_buttons[key] = button
        self.type_buttons["tilting"].setChecked(True)
        types.layout.addLayout(row)
        center.addWidget(types)

        top = QHBoxLayout()
        top.setSpacing(10)
        center.addLayout(top)
        input_host = QWidget()
        igrid = QGridLayout(input_host)
        igrid.setContentsMargins(0, 0, 0, 0)
        igrid.setSpacing(10)
        top.addWidget(input_host, 1)
        geom = Card("Geometry")
        op = Card("Operation")
        self.lub_card = Card("Lubrication / Model")
        igrid.addWidget(geom, 0, 0)
        igrid.addWidget(op, 0, 1)
        igrid.addWidget(self.lub_card, 0, 2)

        self.diameter = LabeledInput("Shaft Diameter (D)", 100, "mm", 2, 0.001)
        self.length = LabeledInput("Pad Length (L)", 80, "mm", 2, 0.001)
        self.clearance = LabeledInput("Radial Clearance (c)", 0.10, "mm", 3, 0.0001)
        self.arc = LabeledInput("Pad Arc (α)", 60, "deg", 1, 1, 360)
        self.preload = LabeledInput("Preload", 0.50, "-", 2, 0, 1)
        for widget in (self.diameter, self.length, self.clearance, self.arc, self.preload):
            geom.layout.addWidget(widget)

        self.count_row = QWidget()
        pl = QHBoxLayout(self.count_row)
        pl.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel("Number of Pads")
        pl.addWidget(self.count_label)
        pl.addStretch(1)
        self.npads = QSpinBox()
        self.npads.setRange(2, 16)
        self.npads.setValue(5)
        pl.addWidget(self.npads)
        geom.layout.addWidget(self.count_row)

        self.speed_row = QWidget()
        sl = QHBoxLayout(self.speed_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(QLabel("Speed Range"))
        self.speed0 = QDoubleSpinBox()
        self.speed0.setRange(1, 100000)
        self.speed0.setValue(500)
        self.speed0.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.speed1 = QDoubleSpinBox()
        self.speed1.setRange(1, 100000)
        self.speed1.setValue(10000)
        self.speed1.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        sl.addWidget(self.speed0)
        sl.addWidget(QLabel("to"))
        sl.addWidget(self.speed1)
        sl.addWidget(QLabel("rpm"))
        op.layout.addWidget(self.speed_row)
        self.loadx = LabeledInput("Load X (Fx)", 5000, "N", 0)
        self.loady = LabeledInput("Load Y (Fy)", 0, "N", 0)
        self.temp = LabeledInput("Oil Inlet Temperature", 40, "°C", 1)
        self.pressure = LabeledInput("Supply Pressure", 2.0, "bar", 1, 0)
        for widget in (self.loadx, self.loady, self.temp, self.pressure):
            op.layout.addWidget(widget)

        self.lube = QComboBox()
        self.lube.addItems(["ISO VG 32", "ISO VG 46", "ISO VG 68"])
        self._combo_row(self.lub_card, "Lubricant Grade", self.lube)
        self.thermal = QComboBox()
        self.thermal.addItems(["Energy Equation", "Isothermal", "Full THD"])
        self._combo_row(self.lub_card, "Thermal Model", self.thermal)
        self.viscosity = QComboBox()
        self.viscosity.addItems(["Roelands", "Vogel", "Constant"])
        self._combo_row(self.lub_card, "Viscosity Model", self.viscosity)
        self.mesh = QComboBox()
        self.mesh.addItems(["Medium (60 × 30)", "Coarse (30 × 15)", "Fine (100 × 50)"])
        self._combo_row(self.lub_card, "Mesh / Discretization", self.mesh)

        self.operating_card = Card(margins=(12, 10, 12, 12))
        self.operating_card.setFixedWidth(285)
        top.addWidget(self.operating_card)
        self.operating_title = QLabel("Operating Point (at 6,000 rpm)")
        self.operating_title.setObjectName("CardTitle")
        self.operating_card.layout.addWidget(self.operating_title)
        self.operating_values = {}
        for key, name, value, unit in [
            ("eccentricity", "Eccentricity Ratio (ε)", "—", "-"),
            ("attitude", "Attitude Angle (φ)", "—", "deg"),
            ("film", "Minimum Film Thickness (hmin)", "—", "mm"),
            ("loss", "Power Loss", "—", "kW"),
            ("flow", "Flow Rate", "—", "L/min"),
            ("temperature", "Max Temperature (Pad)", "—", "°C"),
        ]:
            widget = QWidget()
            rl = QHBoxLayout(widget)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(QLabel(name), 1)
            val = QLabel(value)
            val.setStyleSheet(f"color:{P.text_dark};")
            val.setMinimumWidth(55)
            rl.addWidget(val)
            u = QLabel(unit)
            u.setObjectName("Muted")
            u.setFixedWidth(38)
            rl.addWidget(u)
            self.operating_card.layout.addWidget(widget)
            self.operating_values[key] = val

        results = Card(margins=(0, 0, 0, 0))
        center.addWidget(results, 1)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        results.layout.addWidget(self.tabs)

        kc = QWidget()
        kl = QHBoxLayout(kc)
        kl.setContentsMargins(12, 8, 12, 12)
        kl.setSpacing(10)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["RPM", "Kxx\n(N/m)", "Kxy\n(N/m)", "Kyx\n(N/m)", "Kyy\n(N/m)", "Cxx\n(N·s/m)", "Cxy\n(N·s/m)", "Cyx\n(N·s/m)", "Cyy\n(N·s/m)"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.currentCellChanged.connect(self._select_result_row)
        kl.addWidget(self.table, 3)
        chart_card = QFrame()
        chart_card.setObjectName("FlatCard")
        chl = QVBoxLayout(chart_card)
        chl.setContentsMargins(10, 8, 10, 8)
        cht = QHBoxLayout()
        lab = QLabel("Stiffness and Damping Coefficients")
        lab.setObjectName("SmallHeader")
        cht.addWidget(lab)
        cht.addStretch(1)
        self.coefficient_view = QComboBox()
        self.coefficient_view.addItems(["Stiffness (K)", "Damping (C)"])
        self.coefficient_view.currentIndexChanged.connect(self._refresh_coefficient_chart)
        cht.addWidget(self.coefficient_view)
        chl.addLayout(cht)
        self.chart = SimpleLineChart()
        chl.addWidget(self.chart, 1)
        kl.addWidget(chart_card, 2)
        self.tabs.addTab(kc, "K & C Coefficients")

        self.pressure_view = BearingFieldView("Pressure", "Pa")
        self.temperature_view = BearingFieldView("Temperature", "°C")
        self.film_view = BearingFieldView("Film Thickness", "mm")
        self.journal_view = JournalPositionView()
        self.convergence_page = QWidget()
        conv_lay = QVBoxLayout(self.convergence_page)
        conv_lay.setContentsMargins(20, 18, 20, 18)
        self.convergence_title = QLabel("Run Calculate Bearing to obtain native ROSS convergence information.")
        self.convergence_title.setWordWrap(True)
        self.convergence_title.setObjectName("SmallHeader")
        conv_lay.addWidget(self.convergence_title)
        self.convergence_details = QLabel("")
        self.convergence_details.setWordWrap(True)
        self.convergence_details.setObjectName("Muted")
        conv_lay.addWidget(self.convergence_details)
        conv_lay.addStretch(1)
        self.tabs.addTab(self.pressure_view, "Pressure")
        self.tabs.addTab(self.temperature_view, "Temperature")
        self.tabs.addTab(self.film_view, "Film Thickness")
        self.tabs.addTab(self.journal_view, "Journal Position")
        self.tabs.addTab(self.convergence_page, "Convergence")
        self._fill_presentation_seed()

        right_host = QWidget()
        right_host.setFixedWidth(320)
        right = QVBoxLayout(right_host)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        root.addWidget(right_host)
        info = Card("Project Information")
        right.addWidget(info)
        for name, val in [("Project Name", project.reference or "WGM20"), ("Description", str(project.metadata.get("description", "Wind generator main rotor\n(20 MW class)"))), ("Created", str(project.metadata.get("created", "Apr 25, 2025  10:24"))), ("Last Modified", str(project.metadata.get("last_modified", "Apr 25, 2025  14:17")))]:
            self._info_row(info, name, val)
        bi = Card("Bearing Information")
        right.addWidget(bi)
        self.bearing_info = {}
        for name, val in [("Bearing Name", "DE Journal Bearing"), ("Bearing Type", "Tilting Pad"), ("Node Position", "Node 2 (Disk 1 - Left)"), ("Connected Shaft", "Shaft 1"), ("Number of Pads", "5"), ("Preload", "0.50"), ("Clearance", "0.10 mm"), ("Pad Arc", "60 deg")]:
            self.bearing_info[name] = self._info_row(bi, name, val)
        qa = Card("Quick Actions")
        right.addWidget(qa)
        self.calc_button = QPushButton("Calculate Bearing")
        self.calc_button.setObjectName("PrimaryButton")
        self.calc_button.setIcon(studio_icon("gear", "#FFFFFF", 20))
        self.calc_button.setMinimumHeight(44)
        self.calc_button.clicked.connect(self.calculate)
        qa.layout.addWidget(self.calc_button)
        self.apply_button = QPushButton("Apply to Rotor")
        self.apply_button.setObjectName("SuccessButton")
        self.apply_button.setIcon(studio_icon("check", P.success, 20))
        self.apply_button.clicked.connect(self.apply_to_rotor)
        qa.layout.addWidget(self.apply_button)
        export = QPushButton("Export Curves")
        export.setIcon(studio_icon("export", P.text, 19))
        export.clicked.connect(self.export_curves)
        qa.layout.addWidget(export)
        right.addStretch(1)

    @staticmethod
    def _combo_row(card: Card, label: str, combo: QComboBox):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(label)
        lab.setMinimumWidth(105)
        layout.addWidget(lab)
        layout.addWidget(combo, 1)
        card.layout.addWidget(widget)

    @staticmethod
    def _info_row(card: Card, name: str, value: str) -> QLabel:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(name)
        label.setMinimumWidth(112)
        layout.addWidget(label)
        val = QLabel(value)
        val.setWordWrap(True)
        val.setStyleSheet(f"color:{P.text_dark};font-weight:500;")
        layout.addWidget(val, 1)
        card.layout.addWidget(widget)
        return val

    @staticmethod
    def _lube_key(text: str) -> str:
        return {"ISO VG 32": "ISOVG32", "ISO VG 46": "ISOVG46", "ISO VG 68": "ISOVG68"}.get(text, "ISOVG32")

    def _thermal_type(self):
        return {"Energy Equation": "adiabatic", "Isothermal": None, "Full THD": "full"}[self.thermal.currentText()]

    def _mesh_values(self) -> tuple[int, int, int]:
        if self.mesh.currentText().startswith("Coarse"):
            return 30, 16, 10
        if self.mesh.currentText().startswith("Fine"):
            return 100, 50, 24
        return 60, 30, 16

    def _speed_grid(self) -> list[float]:
        start = float(self.speed0.value())
        stop = float(self.speed1.value())
        if stop <= start:
            raise ValueError("Final bearing speed must be greater than initial speed.")
        if abs(start - 500.0) < 1e-9 and abs(stop - 10000.0) < 1e-9:
            return [500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 10000.0]
        step = (stop - start) / 6.0
        return [start + i * step for i in range(7)]

    def _bearing_position(self) -> float:
        if self.project.bearings:
            return float(self.project.bearings[0].position_mm)
        return min(80.0, self.project.shaft_length_mm)

    def _pivots(self) -> list[float]:
        n = self.npads.value()
        pitch = 360.0 / n
        return [pitch * (i + 0.25) for i in range(n)]

    def _build_fluid_spec(self):
        speeds = self._speed_grid()
        ex, ez, ey_pad = self._mesh_values()
        common = dict(position_mm=self._bearing_position(), journal_diameter_mm=self.diameter.edit.value(), radial_clearance_mm=self.clearance.edit.value(), pad_axial_length_mm=self.length.edit.value(), pad_arc_deg=self.arc.edit.value(), frequency_rpm=speeds, oil_supply_temperature_c=self.temp.edit.value(), lubricant=self._lube_key(self.lube.currentText()), preload=self.preload.edit.value(), load_x_n=self.loadx.edit.value(), load_y_n=self.loady.edit.value(), oil_supply_pressure_pa=self.pressure.edit.value() * 1e5, thermal_type=self._thermal_type(), equilibrium_type="match_load", film_elements_circumferential=ex, film_elements_axial=ez, tag="DE Journal Bearing")
        if self._selected_type == "plain":
            return PlainJournalBearingSpec(n_pads=self.npads.value(), **common)
        if self._selected_type == "tilting":
            previous = self.project.bearings[0] if self.project.bearings else None
            thickness = getattr(previous, "pad_thickness_mm", None)
            if thickness is None:
                thickness = float(self.project.metadata.get("tilting_pad_thickness_mm", 15.0))
            self.project.metadata["tilting_pad_thickness_mm"] = thickness
            return TiltingPadBearingSpec(pad_thickness_mm=thickness, pivot_angle_deg=self._pivots(), pad_elements_radial=ey_pad, **common)
        raise ValueError("The approved compact editor currently calculates Plain Journal and Tilting Pad bearings. Select one of these fluid-film types; dedicated rolling/K-C editors are the next Bearing Studio slice.")

    def _type_changed(self, key: str):
        self._selected_type = key
        self.bearing_info["Bearing Type"].setText(self.type_buttons[key].text())
        self.statusMessage.emit(f"Bearing type: {self.type_buttons[key].text()}", "Input panel selected", True)

    def _fill_presentation_seed(self):
        rows = [(500, 1.20e7, -0.32e7, 0.28e7, 1.10e7, 3.10e4, -0.20e4, 0.18e4, 2.90e4), (1000, 1.35e7, -0.38e7, 0.34e7, 1.28e7, 3.80e4, -0.28e4, 0.25e4, 3.60e4), (2000, 1.72e7, -0.51e7, 0.48e7, 1.64e7, 5.60e4, -0.42e4, 0.39e4, 5.10e4), (4000, 2.28e7, -0.71e7, 0.66e7, 2.18e7, 8.40e4, -0.63e4, 0.58e4, 7.90e4), (6000, 2.85e7, -0.92e7, 0.86e7, 2.74e7, 1.10e5, -0.82e4, 0.77e4, 1.05e5), (8000, 3.41e7, -1.10e7, 1.03e7, 3.28e7, 1.34e5, -1.00e4, 0.95e4, 1.29e5), (10000, 3.95e7, -1.27e7, 1.19e7, 3.80e7, 1.56e5, -1.16e4, 1.10e4, 1.50e5)]
        self._set_coefficient_table(rows)
        self._plot_rows(rows)

    def _set_coefficient_table(self, rows):
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                text = f"{val:,.0f}" if c == 0 else f"{val:.3e}"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _result_rows(self):
        if self._result is None:
            return []
        return [(r.rpm, r.kxx, r.kxy, r.kyx, r.kyy, r.cxx, r.cxy, r.cyx, r.cyy) for r in self._result.coefficients]

    def _plot_rows(self, rows):
        if not rows:
            self.chart.set_series([])
            return
        xs = [r[0] for r in rows]
        self.chart.xmax = max(xs) if max(xs) > 0 else 1.0
        if self.coefficient_view.currentIndex() == 0:
            series_idx = [("Kxx", 1, "blue", False), ("Kyy", 4, "red", False), ("Kxy", 2, "green", True), ("Kyx", 3, "orange", True)]
        else:
            series_idx = [("Cxx", 5, "blue", False), ("Cyy", 8, "red", False), ("Cxy", 6, "green", True), ("Cyx", 7, "orange", True)]
        vals = [r[i] for _, i, _, _ in series_idx for r in rows]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            hi = lo + 1.0
        pad = 0.08 * (hi - lo)
        self.chart.ymin = lo - pad
        self.chart.ymax = hi + pad
        self.chart.set_series([(name, list(zip(xs, [r[i] for r in rows])), color, dashed) for name, i, color, dashed in series_idx])

    def _refresh_coefficient_chart(self):
        rows = self._result_rows()
        if not rows:
            rows = []
            for r in range(self.table.rowCount()):
                try:
                    rows.append(tuple(float(self.table.item(r, c).text().replace(",", "")) for c in range(9)))
                except Exception:
                    return
        self._plot_rows(rows)

    def calculate(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            spec = self._build_fluid_spec()
            spec.validate()
        except Exception as exc:
            self.statusMessage.emit("Bearing input invalid", str(exc), False)
            return
        self.calc_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.calc_button.setText("Calculating...")
        self.statusMessage.emit("Bearing calculation running", "ROSS Reynolds/THD solver active", True)
        self._thread = QThread(self)
        self._worker = BearingWorker(spec)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_calculation_progress)
        self._worker.completed.connect(self._on_calculation_completed)
        self._worker.failed.connect(self._on_calculation_failed)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_calculation_finished)
        self._thread.start()

    @Slot(str)
    def _on_calculation_progress(self, message: str):
        self.statusMessage.emit("Bearing calculation running", message, True)

    @Slot(object)
    def _on_calculation_completed(self, result: BearingCalculationResult):
        self._apply_calculation_result(result)
        all_converged = all(p.converged for p in result.operating_points) if result.operating_points else True
        detail = f"{len(result.coefficients)} operating speeds solved"
        if result.execution_time_s is not None:
            detail += f" in {result.execution_time_s:.2f} s"
        self.statusMessage.emit("Bearing solution converged" if all_converged else "Bearing calculation completed", detail, all_converged)

    @Slot(str)
    def _on_calculation_failed(self, message: str):
        self.statusMessage.emit("Bearing calculation failed", message, False)
        self.convergence_title.setText("ROSS bearing calculation failed")
        self.convergence_details.setText(message)

    def _on_calculation_finished(self):
        self.calc_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.calc_button.setText("Calculate Bearing")
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def _apply_calculation_result(self, result: BearingCalculationResult):
        self._result = result
        rows = self._result_rows()
        self._set_coefficient_table(rows)
        self._plot_rows(rows)
        self.journal_view.set_points(result.operating_points)
        target = 0
        if result.coefficients:
            target = min(range(len(result.coefficients)), key=lambda i: abs(result.coefficients[i].rpm - 6000.0))
            self.table.selectRow(target)
        self._select_result_row(target, 0, -1, -1)

    def _select_result_row(self, current_row: int, current_col: int, previous_row: int, previous_col: int):
        del current_col, previous_row, previous_col
        if self._result is None or current_row < 0:
            return
        self._result_row = min(current_row, max(len(self._result.coefficients) - 1, 0))
        rpm = self._result.coefficients[self._result_row].rpm if self._result.coefficients else 0.0
        self.operating_title.setText(f"Operating Point (at {rpm:,.0f} rpm)")
        point = self._result.operating_points[self._result_row] if self._result_row < len(self._result.operating_points) else None

        def fmt(value, pattern=".3f"):
            return "—" if value is None else format(value, pattern)

        self.operating_values["eccentricity"].setText(fmt(None if point is None else point.eccentricity_ratio, ".3f"))
        self.operating_values["attitude"].setText(fmt(None if point is None else point.attitude_deg, ".1f"))
        self.operating_values["film"].setText(fmt(None if point is None else point.min_film_thickness_mm, ".4f"))
        self.operating_values["loss"].setText(fmt(None if point is None else point.power_loss_kw, ".3f"))
        self.operating_values["flow"].setText(fmt(None if point is None else point.flow_l_min, ".2f"))
        self.operating_values["temperature"].setText(fmt(None if point is None else point.max_temperature_c, ".1f"))
        if self._result_row < len(self._result.pressure_fields_pa):
            theta = self._result.theta_grids_rad[self._result_row] if self._result_row < len(self._result.theta_grids_rad) else None
            self.pressure_view.set_field(self._result.pressure_fields_pa[self._result_row], theta)
            self.temperature_view.set_field(self._result.temperature_fields_c[self._result_row], theta)
            self.film_view.set_field(self._result.film_thickness_fields_mm[self._result_row], theta)
        else:
            self.pressure_view.set_field(None)
            self.temperature_view.set_field(None)
            self.film_view.set_field(None)
        if point is None:
            self.convergence_title.setText("Dynamic coefficients available; no fluid-film operating-point data for this bearing type.")
            self.convergence_details.setText("")
        else:
            self.convergence_title.setText("Converged" if point.converged else "Convergence warning")
            details = [f"Operating speed: {point.rpm:,.0f} rpm"]
            if point.max_pressure_pa is not None:
                details.append(f"Maximum pressure: {point.max_pressure_pa / 1e6:.3f} MPa")
            if self._result.execution_time_s is not None:
                details.append(f"Total bearing solve time: {self._result.execution_time_s:.2f} s")
            if point.convergence_message:
                details.append(point.convergence_message)
            self.convergence_details.setText("\n".join(details))

    def apply_to_rotor(self):
        try:
            bearing = self._build_fluid_spec()
            bearing.validate()
        except Exception as exc:
            self.statusMessage.emit("Bearing input invalid", str(exc), False)
            return
        if self.project.bearings:
            self.project.bearings[0] = bearing
        else:
            self.project.bearings.append(bearing)
        self.projectChanged.emit(self.project)
        self.bearing_info["Bearing Type"].setText("Tilting Pad" if isinstance(bearing, TiltingPadBearingSpec) else "Plain Journal")
        self.bearing_info["Number of Pads"].setText(str(self.npads.value()))
        self.bearing_info["Preload"].setText(f"{self.preload.edit.value():.2f}")
        self.bearing_info["Clearance"].setText(f"{self.clearance.edit.value():.3f} mm")
        self.bearing_info["Pad Arc"].setText(f"{self.arc.edit.value():.1f} deg")
        self.statusMessage.emit("Bearing applied to rotor", "DE Journal Bearing updated", True)

    def export_curves(self):
        if self._result is None:
            self.statusMessage.emit("No calculated bearing results", "Run Calculate Bearing before exporting curves", False)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export bearing coefficients", "bearing_coefficients.csv", "CSV files (*.csv)")
        if not path:
            return
        lines = ["rpm,kxx,kxy,kyx,kyy,cxx,cxy,cyx,cyy"]
        for row in self._result.coefficients:
            lines.append(",".join(f"{v:.12g}" for v in (row.rpm, row.kxx, row.kxy, row.kyx, row.kyy, row.cxx, row.cxy, row.cyx, row.cyy)))
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.statusMessage.emit("Bearing curves exported", Path(path).name, True)
