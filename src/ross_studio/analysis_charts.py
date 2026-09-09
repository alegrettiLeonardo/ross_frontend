from __future__ import annotations

from math import ceil
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .theme import COLORS

if TYPE_CHECKING:
    from .analysis_pipeline import AnalysisPipelineResult


class RealCampbellChart(QWidget):
    """Lightweight Qt chart driven only by the latest ROSS Campbell result."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 390)
        self._speed_rpm: np.ndarray | None = None
        self._frequency_hz: np.ndarray | None = None
        self._whirl: np.ndarray | None = None
        self._critical: list[tuple[float, float]] = []

    def clear(self) -> None:
        self._speed_rpm = None
        self._frequency_hz = None
        self._whirl = None
        self._critical = []
        self.update()

    def set_result(self, result: "AnalysisPipelineResult") -> None:
        speed = np.asarray(result.campbell.speed_range, dtype=float)
        self._speed_rpm = speed * 60.0 / (2.0 * np.pi)
        self._frequency_hz = np.asarray(result.campbell.wd, dtype=float) / (2.0 * np.pi)
        self._whirl = np.asarray(result.campbell.whirl_values, dtype=float)
        self._critical = [(row.speed_rpm, row.frequency_hz) for row in result.critical_speeds]
        self.update()

    @staticmethod
    def _nice_max(value: float, *, base: float) -> float:
        if not np.isfinite(value) or value <= 0:
            return base
        return max(base, ceil(value / base) * base)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        lm, rm, tm, bm = 66, 22, 44, 56
        plot = QRectF(lm, tm, w - lm - rm, h - tm - bm)

        if self._speed_rpm is None or self._frequency_hz is None or self._frequency_hz.size == 0:
            xmax, ymax = 4500.0, 500.0
        else:
            xmax = self._nice_max(float(np.nanmax(self._speed_rpm)), base=500.0)
            ymax = self._nice_max(float(np.nanmax(self._frequency_hz)) * 1.08, base=50.0)

        painter.setPen(QPen(QColor(COLORS.grid), 1))
        for i in range(6):
            x = plot.left() + plot.width() * i / 5
            y = plot.bottom() - plot.height() * i / 5
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(COLORS.text_muted))
            painter.drawText(QRectF(x - 38, plot.bottom() + 8, 76, 18), Qt.AlignmentFlag.AlignCenter, f"{xmax * i / 5:,.0f}")
            painter.drawText(QRectF(2, y - 9, 56, 18), Qt.AlignmentFlag.AlignRight, f"{ymax * i / 5:.0f}")
            painter.setPen(QPen(QColor(COLORS.grid), 1))

        painter.setPen(QPen(QColor("#536f8f"), 1.3))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        painter.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))

        def pt(rpm: float, hz: float) -> QPointF:
            return QPointF(
                plot.left() + float(rpm) / xmax * plot.width(),
                plot.bottom() - float(hz) / ymax * plot.height(),
            )

        if self._speed_rpm is None or self._frequency_hz is None:
            painter.setPen(QColor(COLORS.text_muted))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Run the real ROSS pipeline to populate Campbell results")
        else:
            n_modes = self._frequency_hz.shape[1]
            for mode in range(n_modes):
                values = self._frequency_hz[:, mode]
                whirl = self._whirl[:, mode] if self._whirl is not None else np.zeros(len(values))
                for i in range(len(values) - 1):
                    if not np.isfinite(values[i]) or not np.isfinite(values[i + 1]):
                        continue
                    whirl_value = float(np.nanmean(whirl[i : i + 2]))
                    if whirl_value > 0.75:
                        color = "#ff3b30"
                        style = Qt.PenStyle.DashLine
                    elif whirl_value >= 0.25:
                        color = "#7a5ce6"
                        style = Qt.PenStyle.DotLine
                    else:
                        color = "#167ce1"
                        style = Qt.PenStyle.SolidLine
                    pen = QPen(QColor(color), 1.8)
                    pen.setStyle(style)
                    painter.setPen(pen)
                    painter.drawLine(pt(self._speed_rpm[i], values[i]), pt(self._speed_rpm[i + 1], values[i + 1]))

            sync_pen = QPen(QColor("#263f57"), 1.6)
            sync_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(sync_pen)
            painter.drawLine(pt(0.0, 0.0), pt(xmax, xmax / 60.0))

            for rpm, hz in self._critical:
                if rpm < 0 or rpm > xmax or hz < 0 or hz > ymax:
                    continue
                painter.setBrush(QColor("white"))
                painter.setPen(QPen(QColor("#ff3b30"), 2.0))
                painter.drawEllipse(pt(rpm, hz), 6.5, 6.5)

        painter.setPen(QColor(COLORS.text))
        painter.drawText(QRectF(plot.left(), h - 28, plot.width(), 20), Qt.AlignmentFlag.AlignCenter, "Rotational Speed (rpm)")
        painter.save()
        painter.translate(18, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignmentFlag.AlignCenter, "Damped Frequency (Hz)")
        painter.restore()

        legend_x, legend_y = plot.left() + 8, 18
        for label, color, style in [
            ("Forward", "#167ce1", Qt.PenStyle.SolidLine),
            ("Mixed", "#7a5ce6", Qt.PenStyle.DotLine),
            ("Backward", "#ff3b30", Qt.PenStyle.DashLine),
            ("1X", "#263f57", Qt.PenStyle.DashLine),
        ]:
            pen = QPen(QColor(color), 1.8)
            pen.setStyle(style)
            painter.setPen(pen)
            painter.drawLine(QPointF(legend_x, legend_y), QPointF(legend_x + 24, legend_y))
            painter.setPen(QColor(COLORS.text))
            painter.drawText(QRectF(legend_x + 30, legend_y - 9, 72, 18), Qt.AlignmentFlag.AlignLeft, label)
            legend_x += 95

        painter.end()


__all__ = ["RealCampbellChart"]
