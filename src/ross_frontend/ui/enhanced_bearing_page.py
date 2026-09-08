from __future__ import annotations

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QTableWidgetItem

from ..domain import (
    BallBearingSpec,
    CoefficientBearingSpec,
    CylindricalBearingSpec,
    RollerBearingSpec,
)
from .bearing_page import BearingPage, BearingWorker


class EnhancedBearingPage(BearingPage):
    """Bearing Studio editor for every bearing type shown in the approved UI.

    The base page owns the approved visual composition and native ROSS result views.
    This subclass only changes field semantics and the domain object built from them,
    keeping the visual contract stable while all six selectors become functional.
    """

    def __init__(self, project):
        super().__init__(project)
        self._states: dict[str, dict] = {"tilting": self._capture_state()}

    @staticmethod
    def _configure_input(widget, label, unit, decimals, minimum, maximum):
        widget.label.setText(label)
        widget.unit.setText(unit)
        widget.edit.setDecimals(decimals)
        widget.edit.setRange(minimum, maximum)

    def _set_visibility(
        self,
        *,
        diameter=True,
        length=True,
        clearance=True,
        arc=True,
        preload=True,
        count=True,
        speed=True,
        loadx=True,
        loady=True,
        temp=True,
        pressure=True,
        lubrication=True,
    ):
        for widget, visible in (
            (self.diameter, diameter),
            (self.length, length),
            (self.clearance, clearance),
            (self.arc, arc),
            (self.preload, preload),
            (self.count_row, count),
            (self.speed_row, speed),
            (self.loadx, loadx),
            (self.loady, loady),
            (self.temp, temp),
            (self.pressure, pressure),
            (self.lub_card, lubrication),
        ):
            widget.setVisible(visible)

    def _table_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            values = []
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is None or not item.text().strip():
                    raise ValueError(f"K/C table row {r + 1} has an empty value.")
                values.append(float(item.text().replace(",", "")))
            rows.append(tuple(values))
        return rows

    def _capture_state(self):
        state = {
            "diameter": self.diameter.edit.value(),
            "length": self.length.edit.value(),
            "clearance": self.clearance.edit.value(),
            "arc": self.arc.edit.value(),
            "preload": self.preload.edit.value(),
            "count": self.npads.value(),
            "speed0": self.speed0.value(),
            "speed1": self.speed1.value(),
            "loadx": self.loadx.edit.value(),
            "loady": self.loady.edit.value(),
            "temp": self.temp.edit.value(),
            "pressure": self.pressure.edit.value(),
            "lube": self.lube.currentIndex(),
            "thermal": self.thermal.currentIndex(),
            "viscosity": self.viscosity.currentIndex(),
            "mesh": self.mesh.currentIndex(),
        }
        if getattr(self, "_selected_type", "") == "coefficient":
            try:
                state["rows"] = self._table_rows()
            except ValueError:
                pass
        return state

    def _restore_state(self, state):
        if not state:
            return
        for name, widget in (
            ("diameter", self.diameter),
            ("length", self.length),
            ("clearance", self.clearance),
            ("arc", self.arc),
            ("preload", self.preload),
            ("loadx", self.loadx),
            ("loady", self.loady),
            ("temp", self.temp),
            ("pressure", self.pressure),
        ):
            if name in state:
                widget.edit.setValue(state[name])
        if "count" in state:
            self.npads.setValue(int(state["count"]))
        if "speed0" in state:
            self.speed0.setValue(state["speed0"])
        if "speed1" in state:
            self.speed1.setValue(state["speed1"])
        for name, combo in (("lube", self.lube), ("thermal", self.thermal), ("viscosity", self.viscosity), ("mesh", self.mesh)):
            if name in state:
                combo.setCurrentIndex(int(state[name]))

    @staticmethod
    def _default_state(key):
        defaults = {
            "ball": dict(diameter=12.0, arc=0.0, loadx=5000.0, count=8),
            "roller": dict(length=20.0, arc=0.0, loadx=5000.0, count=8),
            "cylindrical": dict(diameter=100.0, length=80.0, clearance=0.10, preload=0.03, loadx=5000.0, speed0=500.0, speed1=10000.0),
            "plain": dict(diameter=100.0, length=80.0, clearance=0.10, arc=176.0, preload=0.0, count=2, loadx=5000.0, loady=0.0, temp=40.0, pressure=2.0),
            "tilting": dict(diameter=100.0, length=80.0, clearance=0.10, arc=60.0, preload=0.5, count=5, loadx=5000.0, loady=0.0, temp=40.0, pressure=2.0),
        }
        return defaults.get(key, {})

    def _set_table(self, rows, editable=False):
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = f"{value:,.0f}" if c == 0 else f"{value:.3e}"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _load_coefficient_editor(self):
        state = self._states.get("coefficient")
        if state and state.get("rows"):
            rows = state["rows"]
        else:
            bearing = self.project.bearings[0] if self.project.bearings else None
            if isinstance(bearing, CoefficientBearingSpec):
                def seq(value):
                    return list(value) if isinstance(value, (list, tuple)) else [value]

                arrays = [seq(v) for v in (bearing.kxx, bearing.kxz, bearing.kzx, bearing.kzz, bearing.cxx, bearing.cxz, bearing.czx, bearing.czz)]
                n = max(len(values) for values in arrays)
                frequency = list(bearing.frequency_rpm or [0.0])
                if len(frequency) == 1 and n > 1:
                    frequency *= n
                rows = [tuple([frequency[min(i, len(frequency) - 1)]] + [values[min(i, len(values) - 1)] for values in arrays]) for i in range(n)]
            else:
                rows = [(0.0, 1.0e7, 0.0, 0.0, 1.0e7, 1.0e4, 0.0, 0.0, 1.0e4)]
        self._set_table(rows, editable=True)
        self._plot_rows(rows)

    def _configure_type(self, key):
        if key == "coefficient":
            self._set_visibility(diameter=False, length=False, clearance=False, arc=False, preload=False, count=False, speed=False, loadx=False, loady=False, temp=False, pressure=False, lubrication=False)
            self._load_coefficient_editor()
            return
        if key == "ball":
            self._set_visibility(length=False, clearance=False, preload=False, speed=False, loady=False, temp=False, pressure=False, lubrication=False)
            self._configure_input(self.diameter, "Ball Diameter (d)", "mm", 3, 0.001, 1000)
            self._configure_input(self.arc, "Contact Angle (α)", "deg", 2, 0, 89.9)
            self._configure_input(self.loadx, "Static Load (Fs)", "N", 0, 0.001, 1e12)
            self.count_label.setText("Number of Balls")
        elif key == "roller":
            self._set_visibility(diameter=False, clearance=False, preload=False, speed=False, loady=False, temp=False, pressure=False, lubrication=False)
            self._configure_input(self.length, "Roller Length (L)", "mm", 3, 0.001, 5000)
            self._configure_input(self.arc, "Contact Angle (α)", "deg", 2, 0, 89.9)
            self._configure_input(self.loadx, "Static Load (Fs)", "N", 0, 0.001, 1e12)
            self.count_label.setText("Number of Rollers")
        elif key == "cylindrical":
            self._set_visibility(arc=False, count=False, loady=False, temp=False, pressure=False, lubrication=False)
            self._configure_input(self.diameter, "Journal Diameter (D)", "mm", 3, 0.001, 5000)
            self._configure_input(self.length, "Bearing Length (L)", "mm", 3, 0.001, 5000)
            self._configure_input(self.clearance, "Radial Clearance (c)", "mm", 4, 0.0001, 100)
            self._configure_input(self.preload, "Oil Viscosity", "Pa·s", 5, 1e-6, 10)
            self._configure_input(self.loadx, "Bearing Load (W)", "N", 0, 0.001, 1e12)
        else:
            self._set_visibility()
            self._configure_input(self.diameter, "Shaft Diameter (D)", "mm", 2, 0.001, 5000)
            self._configure_input(self.length, "Pad Length (L)", "mm", 2, 0.001, 5000)
            self._configure_input(self.clearance, "Radial Clearance (c)", "mm", 3, 0.0001, 100)
            self._configure_input(self.arc, "Pad Arc (α)", "deg", 1, 1, 360)
            self._configure_input(self.preload, "Preload", "-", 2, 0, 1)
            self._configure_input(self.loadx, "Load X (Fx)", "N", 0, -1e12, 1e12)
            self.count_label.setText("Number of Pads")
        self._restore_state(self._states.get(key, self._default_state(key)))

    def _type_changed(self, key):
        previous = getattr(self, "_selected_type", None)
        if previous:
            self._states[previous] = self._capture_state()
        self._selected_type = key
        self._configure_type(key)
        self.bearing_info["Bearing Type"].setText(self.type_buttons[key].text())
        self.statusMessage.emit(f"Bearing type: {self.type_buttons[key].text()}", "Input panel selected", True)

    def _build_coefficient_spec(self):
        rows = self._table_rows()
        if not rows:
            raise ValueError("Add at least one K/C row before calculating a coefficient bearing.")
        return CoefficientBearingSpec(
            position_mm=self._bearing_position(),
            frequency_rpm=[row[0] for row in rows],
            kxx=[row[1] for row in rows],
            kxz=[row[2] for row in rows],
            kzx=[row[3] for row in rows],
            kzz=[row[4] for row in rows],
            cxx=[row[5] for row in rows],
            cxz=[row[6] for row in rows],
            czx=[row[7] for row in rows],
            czz=[row[8] for row in rows],
            tag="DE Bearing K/C",
        )

    def _build_spec(self):
        if self._selected_type in {"plain", "tilting"}:
            return self._build_fluid_spec()
        if self._selected_type == "coefficient":
            return self._build_coefficient_spec()
        if self._selected_type == "ball":
            return BallBearingSpec(self._bearing_position(), self.npads.value(), self.diameter.edit.value(), self.loadx.edit.value(), self.arc.edit.value(), tag="DE Ball Bearing")
        if self._selected_type == "roller":
            return RollerBearingSpec(self._bearing_position(), self.npads.value(), self.length.edit.value(), self.loadx.edit.value(), self.arc.edit.value(), tag="DE Roller Bearing")
        if self._selected_type == "cylindrical":
            return CylindricalBearingSpec(self._bearing_position(), self._speed_grid(), self.loadx.edit.value(), self.length.edit.value(), self.diameter.edit.value(), self.clearance.edit.value(), self.preload.edit.value(), tag="DE Cylindrical Bearing")
        raise ValueError(f"Unsupported bearing type: {self._selected_type}")

    def calculate(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            spec = self._build_spec()
            spec.validate()
        except Exception as exc:
            self.statusMessage.emit("Bearing input invalid", str(exc), False)
            return
        self.calc_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.calc_button.setText("Calculating...")
        self.statusMessage.emit("Bearing calculation running", "ROSS bearing solver active", True)
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

    def apply_to_rotor(self):
        try:
            bearing = self._build_spec()
            bearing.validate()
        except Exception as exc:
            self.statusMessage.emit("Bearing input invalid", str(exc), False)
            return
        if self.project.bearings:
            self.project.bearings[0] = bearing
        else:
            self.project.bearings.append(bearing)
        self.projectChanged.emit(self.project)
        self.bearing_info["Bearing Type"].setText(self.type_buttons[self._selected_type].text())
        if self._selected_type in {"plain", "tilting"}:
            self.bearing_info["Number of Pads"].setText(str(self.npads.value()))
            self.bearing_info["Preload"].setText(f"{self.preload.edit.value():.2f}")
            self.bearing_info["Clearance"].setText(f"{self.clearance.edit.value():.3f} mm")
            self.bearing_info["Pad Arc"].setText(f"{self.arc.edit.value():.1f} deg")
        self.statusMessage.emit("Bearing applied to rotor", "DE bearing model updated", True)
