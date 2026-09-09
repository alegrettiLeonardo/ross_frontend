from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..backends.ross.response_calculator import RotorResponseResult
from .theme import P


class ResponseCurveView(QWidget):
    """Native Qt response chart matching the approved ROSS Studio visual language."""

    COLORS = ["#137FF1", "#E2575A", "#16A66B", "#E9A23B", "#7B61C9", "#0FA3B1", "#D66A9C", "#60768E"]

    def __init__(self):
        super().__init__()
        self.result: RotorResponseResult | None = None
        self.mode = "magnitude"
        self.message = "Select a response analysis."
        self.setMinimumHeight(390)

    def set_result(self, result: RotorResponseResult | None, mode: str = "magnitude"):
        self.result = result
        self.mode = mode
        self.update()

    def set_message(self, text: str):
        self.result = None
        self.message = text
        self.update()

    def _series(self):
        if self.result is None:
            return []
        output = []
        for curve in self.result.curves:
            if self.mode == "phase":
                values = curve.phase_deg
                unit = "deg"
            else:
                # Response displacement is kept scientifically in metres in the
                # backend and displayed as micrometres for engineering readability.
                if curve.magnitude_unit == "m":
                    values = [v * 1e6 for v in curve.magnitude]
                    unit = "µm"
                else:
                    values = curve.magnitude
                    unit = curve.magnitude_unit
            output.append((curve.label, list(curve.x), list(values), unit))
        return output

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("white"))
        width, height = self.width(), self.height()
        left, top, right, bottom = 72, 58, width - 28, height - 58

        title = "Response Amplitude" if self.mode == "magnitude" else "Response Phase"
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QColor(P.text_dark))
        painter.drawText(14, 27, title)
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)

        series = self._series()
        if not series:
            painter.setPen(QColor(P.muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            painter.end()
            return

        xs = [x for _, xvals, _, _ in series for x in xvals]
        ys = [y for _, _, yvals, _ in series for y in yvals]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax <= xmin:
            xmax = xmin + 1.0
        if ymax <= ymin:
            pad = max(abs(ymax), 1.0) * 0.1
            ymin -= pad
            ymax += pad
        else:
            pad = (ymax - ymin) * 0.08
            ymin -= pad
            ymax += pad

        painter.setPen(QPen(QColor("#DCE6EF"), 1))
        for i in range(6):
            x = left + (right - left) * i / 5
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.setPen(QColor(P.muted))
            value = xmin + (xmax - xmin) * i / 5
            painter.drawText(QRectF(x - 38, bottom + 7, 76, 18), Qt.AlignmentFlag.AlignCenter, f"{value:,.0f}")
            painter.setPen(QPen(QColor("#DCE6EF"), 1))
        for i in range(6):
            y = top + (bottom - top) * i / 5
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            value = ymax - (ymax - ymin) * i / 5
            painter.setPen(QColor(P.muted))
            painter.drawText(QRectF(4, y - 9, 60, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{value:.3g}")
            painter.setPen(QPen(QColor("#DCE6EF"), 1))

        painter.setPen(QPen(QColor("#688096"), 1.2))
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))
        painter.drawLine(QPointF(left, bottom), QPointF(right, bottom))

        def sx(value):
            return left + (right - left) * (value - xmin) / (xmax - xmin)

        def sy(value):
            return bottom - (bottom - top) * (value - ymin) / (ymax - ymin)

        legend_x = left
        for index, (label, xvals, yvals, _unit) in enumerate(series):
            color = QColor(self.COLORS[index % len(self.COLORS)])
            painter.setPen(QPen(color, 2.0))
            path = QPainterPath()
            for point_index, (xv, yv) in enumerate(zip(xvals, yvals)):
                point = QPointF(sx(float(xv)), sy(float(yv)))
                if point_index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)
            painter.drawLine(QPointF(legend_x, 45), QPointF(legend_x + 23, 45))
            painter.setPen(QColor(P.text))
            painter.drawText(legend_x + 29, 49, label)
            legend_x += min(180, max(115, 42 + len(label) * 7))

        unit = series[0][3]
        painter.setPen(QColor(P.text))
        painter.drawText(QRectF(left, bottom + 30, right - left, 20), Qt.AlignmentFlag.AlignCenter, "Rotational Speed (rpm)")
        painter.save()
        painter.translate(10, (top + bottom) / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-100, -4, 200, 18), Qt.AlignmentFlag.AlignCenter, f"{'Amplitude' if self.mode == 'magnitude' else 'Phase'} ({unit})")
        painter.restore()
        painter.end()


__all__ = ["ResponseCurveView"]
