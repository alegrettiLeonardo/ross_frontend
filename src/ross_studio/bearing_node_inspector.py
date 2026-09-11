from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .bearing_workspace import BearingWorkspaceService
from .domain import BearingCoefficientPoint, BearingSpec
from .models import ProjectModel
from .rotor_selection import RotorEntityRef
from .theme import COLORS
from .widgets import SectionCard


THD_SOURCE_MODELS = {"PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"}


@dataclass(slots=True, frozen=True)
class _Series:
    name: str
    points: tuple[tuple[float, float], ...]


class _CoefficientCurve(QWidget):
    """Read-only plot of cached solver coefficients stored in RotorProject.

    This widget does not solve or re-fit a bearing. It is intentionally limited to
    previously committed THD coefficient stations and is labelled as cached data in
    the dialog. Bearing Studio remains the owner of native ROSS post-processing.
    """

    def __init__(self, series: Iterable[_Series], unit: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.series = tuple(series)
        self.unit = unit
        self.setMinimumSize(560, 330)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        plot = QRectF(82, 32, max(120, self.width() - 190), max(100, self.height() - 92))
        all_points = [point for series in self.series for point in series.points]
        if not all_points:
            painter.setPen(QColor(COLORS.text_muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No cached THD coefficient curve")
            painter.end()
            return
        xs = [point[0] for point in all_points]
        ys = [point[1] for point in all_points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if abs(xmax - xmin) <= 1e-12:
            xmin -= 1.0
            xmax += 1.0
        span = ymax - ymin
        pad = max(abs(ymax) * 0.03, abs(ymin) * 0.03, span * 0.06, 1e-12)
        if span <= 1e-15:
            ymin -= pad
            ymax += pad
        else:
            ymin -= pad
            ymax += pad

        def xy(x: float, y: float) -> QPointF:
            px = plot.left() + (x - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (y - ymin) / (ymax - ymin) * plot.height()
            return QPointF(px, py)

        for i in range(5):
            frac = i / 4.0
            y = plot.bottom() - frac * plot.height()
            x = plot.left() + frac * plot.width()
            painter.setPen(QPen(QColor(COLORS.grid), 1.0))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(COLORS.text_muted))
            painter.drawText(QRectF(2, y - 9, 74, 18), Qt.AlignmentFlag.AlignRight, f"{ymin + frac * (ymax - ymin):.2e}")
            painter.drawText(QRectF(x - 35, plot.bottom() + 5, 70, 18), Qt.AlignmentFlag.AlignCenter, f"{xmin + frac * (xmax - xmin):g}")

        colors = ("#147bd1", "#11995a", "#e69500", "#d64141", "#7758c7")
        for index, series in enumerate(self.series):
            color = QColor(colors[index % len(colors)])
            painter.setPen(QPen(color, 2.0))
            path = QPainterPath()
            for p_index, (rpm, value) in enumerate(series.points):
                point = xy(rpm, value)
                path.moveTo(point) if p_index == 0 else path.lineTo(point)
                painter.drawEllipse(point, 2.2, 2.2)
            painter.drawPath(path)
            painter.drawText(
                QRectF(plot.right() + 10, plot.top() + 22 * index, 88, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                series.name,
            )

        painter.setPen(QColor(COLORS.text))
        painter.drawText(QRectF(0, self.height() - 28, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "Speed (rpm)")
        painter.save()
        painter.translate(18, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignmentFlag.AlignCenter, self.unit)
        painter.restore()
        painter.end()


class THDCoefficientCurvesDialog(QDialog):
    def __init__(self, project: ProjectModel, station_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("THD Bearing K/C Curves")
        self.resize(920, 620)
        root = QVBoxLayout(self)
        note = QLabel(
            "Cached solved ROSS THD coefficients committed to the rotor model. "
            "Opening this view does not rerun the THD solver."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        k_series, c_series = self._series(project, station_index)
        tabs.addTab(_CoefficientCurve(k_series, "Stiffness (N/m)"), "K curves")
        tabs.addTab(_CoefficientCurve(c_series, "Damping (N·s/m)"), "C curves")
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        root.addLayout(buttons)

    @staticmethod
    def _series(project: ProjectModel, station_index: int) -> tuple[tuple[_Series, ...], tuple[_Series, ...]]:
        engineering = project.engineering
        if engineering is None:
            return (), ()
        workspace = BearingWorkspaceService()
        inventory = workspace.inventory(engineering, station_index)
        k: list[_Series] = []
        c: list[_Series] = []
        for element in inventory.elements:
            spec = engineering.bearings[element.element_index]
            source = str(spec.metadata.get("source_model", spec.ross_class))
            if source not in THD_SOURCE_MODELS:
                continue
            prefix = "" if element.role == "radial_anchor" else "Axial "
            if spec.coefficients:
                for name in ("kxx", "kxy", "kyx", "kyy"):
                    k.append(_Series(prefix + name.upper(), tuple((float(row.rpm), float(getattr(row, name))) for row in spec.coefficients)))
                for name in ("cxx", "cxy", "cyx", "cyy"):
                    c.append(_Series(prefix + name.upper(), tuple((float(row.rpm), float(getattr(row, name))) for row in spec.coefficients)))
            axial = spec.metadata.get("axial_coefficients")
            if isinstance(axial, list) and axial:
                k_points = tuple((float(row["rpm"]), float(row["kzz"])) for row in axial if isinstance(row, dict))
                c_points = tuple((float(row["rpm"]), float(row["czz"])) for row in axial if isinstance(row, dict))
                if k_points:
                    k.append(_Series("Axial KZZ", k_points))
                if c_points:
                    c.append(_Series("Axial CZZ", c_points))
        return tuple(k), tuple(c)


class BearingNodeInspector(QWidget):
    """Bearing information card shown while the user remains in the rotor-model flow."""

    open_bearing_studio_requested = Signal(int)

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.workspace = BearingWorkspaceService()
        self.station_index: int | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.card = SectionCard("Bearing Node")
        root.addWidget(self.card)
        self.message = QLabel("Select a bearing in the rotor sketch to inspect its applied K/C.")
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        self.card.root.addWidget(self.message)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(9)
        self.grid.setVerticalSpacing(6)
        self.card.root.addLayout(self.grid)
        self.value_labels: dict[str, QLabel] = {}
        for row, key in enumerate(("Station", "Node", "Model", "Support", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy", "Axial")):
            label = QLabel(key)
            label.setObjectName("muted")
            value = QLabel("—")
            value.setWordWrap(True)
            self.grid.addWidget(label, row, 0)
            self.grid.addWidget(value, row, 1)
            self.value_labels[key] = value
        self.grid.setColumnStretch(1, 1)
        self.curves_button = QPushButton("View THD K/C Curves")
        self.curves_button.setObjectName("softButton")
        self.curves_button.hide()
        self.curves_button.clicked.connect(self._open_curves)
        self.card.root.addWidget(self.curves_button)
        self.open_button = QPushButton("Open Bearing Studio")
        self.open_button.setObjectName("primaryButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_studio)
        self.card.root.addWidget(self.open_button)

    @staticmethod
    def _interpolate(points: list[BearingCoefficientPoint], rpm: float, name: str) -> float | None:
        if not points:
            return None
        rows = sorted(points, key=lambda row: row.rpm)
        if rpm < rows[0].rpm - 1e-9 or rpm > rows[-1].rpm + 1e-9:
            return None
        for row in rows:
            if abs(row.rpm - rpm) <= 1e-9:
                return float(getattr(row, name))
        for a, b in zip(rows, rows[1:]):
            if a.rpm <= rpm <= b.rpm:
                fraction = (rpm - a.rpm) / (b.rpm - a.rpm)
                return float(getattr(a, name) + fraction * (getattr(b, name) - getattr(a, name)))
        return None

    @staticmethod
    def _interpolate_axial(rows: list[dict], rpm: float, name: str) -> float | None:
        clean = sorted(
            (row for row in rows if isinstance(row, dict) and {"rpm", name}.issubset(row)),
            key=lambda row: float(row["rpm"]),
        )
        if not clean or rpm < float(clean[0]["rpm"]) - 1e-9 or rpm > float(clean[-1]["rpm"]) + 1e-9:
            return None
        for row in clean:
            if abs(float(row["rpm"]) - rpm) <= 1e-9:
                return float(row[name])
        for a, b in zip(clean, clean[1:]):
            ar, br = float(a["rpm"]), float(b["rpm"])
            if ar <= rpm <= br:
                f = (rpm - ar) / (br - ar)
                return float(a[name]) + f * (float(b[name]) - float(a[name]))
        return None

    @staticmethod
    def _fmt(value: float | None, unit: str) -> str:
        return "outside solved envelope" if value is None else f"{value:.4e} {unit}"

    def clear(self) -> None:
        self.station_index = None
        self.message.setText("Select a bearing in the rotor sketch to inspect its applied K/C.")
        for label in self.value_labels.values():
            label.setText("—")
        self.curves_button.hide()
        self.open_button.setEnabled(False)

    def set_selection(self, ref: RotorEntityRef | None) -> None:
        engineering = self.project.engineering
        if ref is None or ref.kind != "bearings" or engineering is None:
            self.clear()
            return
        try:
            anchor = self.workspace.anchor_index(engineering, ref.index)
            inventory = self.workspace.inventory(engineering, anchor)
        except Exception as exc:
            self.clear()
            self.message.setText(f"Bearing selection unresolved: {exc}")
            return
        self.station_index = anchor
        station = inventory.station
        spec = engineering.bearings[anchor]
        source = str(spec.metadata.get("source_model", spec.ross_class))
        rated = float(engineering.operating_cases[0].rated_speed_rpm)
        support = ", ".join(station.support_names) if station.support_names else "Grounded / rigid"
        self.message.setText(f"Applied coefficients at rated speed {rated:g} rpm")
        self.value_labels["Station"].setText(f"{station.name} · x={station.position_mm:g} mm")
        self.value_labels["Node"].setText("—" if station.ross_node is None else f"ROSS n{station.ross_node}")
        self.value_labels["Model"].setText(source)
        self.value_labels["Support"].setText(support)

        for name in ("kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy"):
            if spec.coefficients:
                value = self._interpolate(spec.coefficients, rated, name)
            else:
                value = float(getattr(spec, name))
            unit = "N/m" if name.startswith("k") else "N·s/m"
            self.value_labels[name.upper().replace("XX", "xx").replace("XY", "xy").replace("YX", "yx").replace("YY", "yy") if False else name[0].upper() + name[1:]].setText(self._fmt(value, unit))

        axial_texts: list[str] = []
        has_thd_curve = source in THD_SOURCE_MODELS and bool(spec.coefficients)
        for auxiliary in inventory.axial_auxiliaries:
            axial_spec = engineering.bearings[auxiliary.element_index]
            axial_source = str(axial_spec.metadata.get("source_model", axial_spec.ross_class))
            rows = axial_spec.metadata.get("axial_coefficients")
            if isinstance(rows, list) and rows:
                kzz = self._interpolate_axial(rows, rated, "kzz")
                czz = self._interpolate_axial(rows, rated, "czz")
                axial_texts.append(
                    f"{axial_source}: Kzz={self._fmt(kzz, 'N/m')} · Czz={self._fmt(czz, 'N·s/m')}"
                )
                has_thd_curve = has_thd_curve or axial_source in THD_SOURCE_MODELS
            else:
                axial_texts.append(axial_source)
        self.value_labels["Axial"].setText("; ".join(axial_texts) if axial_texts else "None")
        self.curves_button.setVisible(has_thd_curve)
        self.open_button.setEnabled(True)

    def refresh(self) -> None:
        if self.station_index is None:
            return
        engineering = self.project.engineering
        if engineering is None or self.station_index >= len(engineering.bearings):
            self.clear()
            return
        spec = engineering.bearings[self.station_index]
        self.set_selection(RotorEntityRef("bearings", self.station_index, spec.name, spec.position_mm))

    def _open_curves(self) -> None:
        if self.station_index is None:
            return
        THDCoefficientCurvesDialog(self.project, self.station_index, self).exec()

    def _open_studio(self) -> None:
        if self.station_index is not None:
            self.open_bearing_studio_requested.emit(self.station_index)


__all__ = ["BearingNodeInspector", "THDCoefficientCurvesDialog", "THD_SOURCE_MODELS"]
