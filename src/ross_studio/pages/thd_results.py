from __future__ import annotations

import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..thd_results import UNAVAILABLE, convergence, native_field


def shown(value, scale=1.0):
    return UNAVAILABLE if value is None else f"{value * scale:.8g}"


class THDResultTab(QWidget):
    """Speed/pad-selectable native field matrix with color scale and exact values."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.result = None
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Solved speed (rpm)"))
        self.speed = QComboBox()
        controls.addWidget(self.speed)
        controls.addWidget(QLabel("Pad"))
        self.pad = QComboBox()
        controls.addWidget(self.pad)
        controls.addStretch()
        root.addLayout(controls)
        self.summary = QLabel("Calculate a bearing to view native results.")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)
        self.speed.currentIndexChanged.connect(self._speed_changed)
        self.pad.currentIndexChanged.connect(self.render)

    def set_result(self, result, rated_rpm):
        self.result = result
        self.speed.blockSignals(True)
        self.speed.clear()
        self.speed.addItems([f"{p.rpm:.12g}" for p in result.operating_points])
        self.speed.setCurrentIndex(min(range(len(result.operating_points)), key=lambda i: abs(result.operating_points[i].rpm-rated_rpm)))
        self.speed.blockSignals(False)
        self._speed_changed()

    def _speed_changed(self):
        if self.result is None:
            return
        field = native_field(self.result, self.name, self.speed.currentIndex())
        n_pad = field.shape[2] if field is not None and field.ndim == 3 else 1
        self.pad.blockSignals(True)
        self.pad.clear()
        self.pad.addItems([str(i+1) for i in range(n_pad)])
        self.pad.setEnabled(n_pad > 1)
        self.pad.blockSignals(False)
        self.render()

    def _rows(self, headers, rows):
        self.table.clear()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def render(self):
        if self.result is None or self.speed.currentIndex() < 0:
            return
        index = self.speed.currentIndex()
        op = self.result.operating_points[index]
        prefix = f"{self.result.source_model} · {op.rpm:g} rpm · "
        field = native_field(self.result, self.name, index)
        if self.name in {"Pressure", "Temperature"}:
            unit, scale = ("MPa", 1e-6) if self.name == "Pressure" else ("°C", 1.)
            maximum = op.max_pressure_pa if self.name == "Pressure" else op.max_temperature_c
            self._rows([], [])
            if field is None:
                self.summary.setText(prefix + f"Maximum: {shown(maximum, scale)} {unit}. Field: {UNAVAILABLE}")
                return
            matrix = field[:, :, self.pad.currentIndex()] if field.ndim == 3 else field
            matrix = matrix * scale
            finite = matrix[np.isfinite(matrix)]
            if not finite.size:
                self.summary.setText(prefix + "Native field contains no finite values.")
                return
            lo, hi = float(finite.min()), float(finite.max())
            self.summary.setText(prefix + f"Field maximum: {np.nanmax(field)*scale:.8g} {unit}. Selected pad scale: {lo:.8g}–{hi:.8g} {unit}. Rows and columns are native ROSS grid indices.")
            self._rows([str(i) for i in range(matrix.shape[1])], [[f"{v:.8g}" for v in row] for row in matrix])
            for r in range(matrix.shape[0]):
                for c in range(matrix.shape[1]):
                    value = matrix[r, c]
                    if np.isfinite(value):
                        fraction = (value-lo)/(hi-lo) if hi > lo else 0.5
                        self.table.item(r, c).setBackground(QColor.fromHsvF((1-fraction)*0.62, 0.35, 1.))
        elif self.name == "Film Thickness":
            if self.result.source_model == "ThrustPad":
                self.summary.setText(
                    prefix
                    + f"h_min: {shown(op.min_film_thickness_m, 1e6)} µm · "
                    + f"h_pivot: {shown(op.pivot_film_thickness_m, 1e6)} µm · "
                    + f"h_max: {shown(op.max_film_thickness_m, 1e6)} µm. "
                    + f"Per-speed full film distribution: {UNAVAILABLE}."
                )
                self._rows(
                    ["rpm", "h_min (µm)", "h_pivot (µm)", "h_max (µm)"],
                    [
                        [
                            f"{p.rpm:g}",
                            shown(p.min_film_thickness_m, 1e6),
                            shown(p.pivot_film_thickness_m, 1e6),
                            shown(p.max_film_thickness_m, 1e6),
                        ]
                        for p in self.result.operating_points
                    ],
                )
                return
            self.summary.setText(prefix + f"Minimum film thickness: {shown(op.min_film_thickness_m, 1e6)} µm. Distribution: {UNAVAILABLE}.")
            rows = [[f"{p.rpm:g}", shown(p.min_film_thickness_m, 1e6)] for p in self.result.operating_points]
            self._rows(["rpm", "h_min (µm)"], rows)
            if self.result.source_model == "TiltingPad":
                values = self.result.native_element._results.minH_list
                self._rows(["rpm", "Selected pad pivot film (µm)"], [[f"{p.rpm:g}", shown(float(values[i]), 1e6)] for i,p in enumerate(self.result.operating_points)])
                self.summary.setText(prefix + f"Global h_min and distribution: {UNAVAILABLE}. ROSS minH_list contains selected-pad pivot film thickness; it is not h_min.")
        elif self.name == "Journal Position":
            if self.result.source_model == "ThrustPad":
                self._rows([], [])
                self.summary.setText(
                    prefix
                    + "Journal eccentricity and attitude are lateral-bearing quantities and are not part of the axial ThrustPad contract. "
                    + UNAVAILABLE
                )
                return
            self.summary.setText(prefix + "Native equilibrium by solved speed; missing quantities are explicitly unavailable.")
            self._rows(["rpm", "Eccentricity ratio (1)", "Attitude (deg)"], [[f"{p.rpm:g}", shown(p.eccentricity_ratio), shown(p.attitude_angle_rad, 180/np.pi)] for p in self.result.operating_points])
        else:
            info = convergence(self.result, index)
            self.summary.setText(prefix + f"Optimizer iterations: {info['iterations'] if info['iterations'] is not None else UNAVAILABLE}; recorded evaluations: {info['samples']}; final residual: {shown(info['residual_final'])}. {info['residual_contract']}. {info['message']}")
            self._rows(["Recorded evaluation", "Native residual"], [[i, shown(v)] for i,v in enumerate(info['history'])])
