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
from ..domain import (
    BallBearingSpec,
    CoefficientBearingSpec,
    CylindricalBearingSpec,
    PlainJournalBearingSpec,
    RollerBearingSpec,
    RotorProject,
    TiltingPadBearingSpec,
)
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
    def __init__(
        self,
        label: str,
        value: float,
        unit: str = "",
        decimals: int = 2,
        minimum: float = -1e12,
        maximum: float = 1e12,
    ):
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

    def configure(self, label=None, unit=None, value=None, decimals=None, minimum=None, maximum=None):
        if label is not None:
            self.label.setText(label)
        if unit is not None:
            self.unit.setText(unit)
        if decimals is not None:
            self.edit.setDecimals(decimals)
        lo = self.edit.minimum() if minimum is None else minimum
        hi = self.edit.maximum() if maximum is None else maximum
        self.edit.setRange(lo, hi)
        if value is not None:
            self.edit.setValue(value)


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
        self._initialized_types = {"tilting"}

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
        for widget in (self.loadx, self.loady, self.temp, self.pressur):
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
            ("attitude", "Attitude Angle (φ