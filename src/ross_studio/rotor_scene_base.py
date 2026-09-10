from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QToolTip, QWidget

from .models import ProjectModel
from .rotor_selection import RotorEntityRef, RotorSelectionModel, WORKSPACE_SELECTION
from .topology import NodeInsertionService
from .ump import project_ump_specs


@dataclass(slots=True)
class _HitRegion:
    ref: RotorEntityRef
    rect: QRectF
    tooltip: str


class InteractiveRotorSketch(QWidget):
    """Engineering rotor editor view derived entirely from the project domain.

    Interaction contract follows the approved RotorDin frontend: wheel zooms at the
    pointer, left-drag pans, double click fits, hover exposes engineering identity and
    click updates the shared selection model. The FE overlay comes from the exact
    ``NodeInsertionService`` topology, so what the user sees is the topology sent to
    the ROSS builder rather than a decorative approximation.
    """

    entity_activated = Signal(str, int)

    def __init__(
        self,
        project: ProjectModel,
        parent: QWidget | None = None,
        *,
        selection: RotorSelectionModel | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.selection = selection or WORKSPACE_SELECTION
        self._zoom = 1.0
        self._offset_x = 0.0
        self._drag_from: QPoint | None = None
        self._hits: list[_HitRegion] = []
        self._show_mesh = True
        self.setMinimumHeight(290)
        self.setMouseTracking(True)
        # Use a bound QObject slot instead of a lambda captured by the process-global
        # selection model. Qt can then disconnect it automatically when this widget
        # is destroyed; repeated desktop test/window construction cannot retain a
        # callback to a deleted C++ object.
        self.selection.selection_changed.connect(self._selection_changed)

    def _selection_changed(self, _ref: RotorEntityRef | None) -> None:
        self.update()

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def show_mesh(self) -> bool:
        return self._show_mesh

    def set_mesh_visible(self, visible: bool) -> None:
        self._show_mesh = bool(visible)
        self.update()

    def fit(self) -> None:
        self._zoom = 1.0
        self._offset_x = 0.0
        self.update()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * 1.20, self.width() / 2.0)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / 1.20, self.width() / 2.0)

    def _base_scale(self) -> float:
        engineering = self.project.engineering
        total = 0.0 if engineering is None else engineering.total_length_mm
        return max(self.width() - 120.0, 100.0) / max(total, 1.0)

    def _x(self, position_mm: float) -> float:
        engineering = self.project.engineering
        total = 0.0 if engineering is None else engineering.total_length_mm
        return self.width() / 2.0 + (position_mm - total / 2.0) * self._base_scale() * self._zoom + self._offset_x

    def _set_zoom(self, value: float, anchor_x: float) -> None:
        old = self._zoom
        new = min(10.0, max(0.20, float(value)))
        if abs(new - old) <= 1e-12:
            return
        # Keep the engineering point under the cursor visually stationary.
        center = self.width() / 2.0
        self._offset_x = anchor_x - center - (anchor_x - center - self._offset_x) * new / old
        self._zoom = new
        self.update()

    @staticmethod
    def _selected(current: RotorEntityRef | None, kind: str, index: int) -> bool:
        return current is not None and current.kind == kind and current.index == index

    def _register(self, ref: RotorEntityRef, rect: QRectF, tooltip: str) -> None:
        self._hits.append(_HitRegion(ref, rect.adjusted(-4, -4, 4, 4), tooltip))

    def _section_tooltip(self, index: int, x0: float, x1: float, effective: int) -> str:
        engineering = self.project.engineering
        assert engineering is not None
        section = engineering.shaft_sections[index]
        return (
            f"Shaft section {section.section}\n"
            f"x = {x0:.3f} … {x1:.3f} mm\n"
            f"L = {section.length_mm:g} mm\n"
            f"OD = {section.od_left_mm:g} → {section.odr_mm:g} mm\n"
            f"ID = {section.id_left_mm:g} → {section.idr_mm:g} mm\n"
            f"Base FE elements = {section.fe_elements}\n"
            f"Effective ROSS elements = {effective}\n"
            f"Material = {section.material}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        engineering = self.project.engineering
        if engineering is None or engineering.total_length_mm <= 0.0:
            painter.setPen(QColor("#61778d"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No engineering rotor model loaded")
            return

        self._hits.clear()
        current = self.selection.current
        plan = NodeInsertionService.plan(engineering)
        section_counts = {section.section: 0 for section in engineering.shaft_sections}
        boundaries = engineering.section_boundaries_mm()
        for x0, x1 in zip(plan.positions_mm, plan.positions_mm[1:]):
            midpoint = 0.5 * (x0 + x1)
            for i, section in enumerate(engineering.shaft_sections):
                if boundaries[i] - 1e-8 <= midpoint <= boundaries[i + 1] + 1e-8:
                    section_counts[section.section] += 1
                    break

        max_d = max(
            [100.0]
            + [max(s.od_left_mm, s.odr_mm) for s in engineering.shaft_sections]
            + [m.od_mm for m in engineering.distributed_masses if m.od_mm > 0]
        )
        cy = self.height() * 0.43
        sy = min(1.0, max(0.35, self.height() * 0.40 / max_d))

        painter.setPen(QPen(QColor("#9eb2c4"), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(18.0, cy), QPointF(self.width() - 18.0, cy))

        # Physical shaft sections: true coordinates and true taper/bore geometry.
        start = 0.0
        for index, section in enumerate(engineering.shaft_sections):
            end = start + section.length_mm
            x0, x1 = self._x(start), self._x(end)
            r0, r1 = 0.5 * section.od_left_mm * sy, 0.5 * section.odr_mm * sy
            poly = QPolygonF([
                QPointF(x0, cy - r0), QPointF(x1, cy - r1),
                QPointF(x1, cy + r1), QPointF(x0, cy + r0),
            ])
            selected = self._selected(current, "shaft", index)
            painter.setPen(QPen(QColor("#1585df" if selected else "#4e6276"), 2.6 if selected else 1.25))
            painter.setBrush(QColor("#e8f4ff" if selected else ("#f5f8fa" if index % 2 else "#f9fbfd")))
            painter.drawPolygon(poly)
            if section.id_left_mm > 0.0 or section.idr_mm > 0.0:
                painter.setPen(QPen(QColor("#71879a"), 1.0, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(x0, cy - section.id_left_mm * sy / 2), QPointF(x1, cy - section.idr_mm * sy / 2))
                painter.drawLine(QPointF(x0, cy + section.id_left_mm * sy / 2), QPointF(x1, cy + section.idr_mm * sy / 2))
            if abs(x1 - x0) >= 24:
                painter.setPen(QColor("#173b63"))
                painter.drawText(QRectF(min(x0, x1), cy - 16, abs(x1 - x0), 32), Qt.AlignmentFlag.AlignCenter, str(section.section))
            hit = QRectF(min(x0, x1), cy - max(r0, r1) - 2, abs(x1 - x0), 2 * max(r0, r1) + 4)
            ref = RotorEntityRef("shaft", index, f"Shaft section {section.section}", 0.5 * (start + end))
            self._register(ref, hit, self._section_tooltip(index, start, end, section_counts[section.section]))
            start = end

        # FE topology overlay: effective ROSS elements and nodes after mandatory insertion.
        if self._show_mesh:
            node_step = max(1, ceil(len(plan.positions_mm) / 32))
            element_step = max(1, ceil(plan.shaft_element_count / 36))
            mesh_y = min(self.height() - 35.0, cy + max_d * sy / 2 + 34.0)
            painter.setPen(QPen(QColor("#7c92a6"), 0.8))
            for node, x_mm in enumerate(plan.positions_mm):
                x = self._x(x_mm)
                painter.drawLine(QPointF(x, cy - 6), QPointF(x, cy + 6))
                painter.setBrush(QColor("#ffffff"))
                painter.drawEllipse(QRectF(x - 2.2, cy - 2.2, 4.4, 4.4))
                if node % node_step == 0 or node in (0, len(plan.positions_mm) - 1):
                    painter.setPen(QColor("#5d7388"))
                    painter.drawText(QRectF(x - 18, mesh_y, 36, 16), Qt.AlignmentFlag.AlignCenter, f"n{node}")
                    painter.setPen(QPen(QColor("#7c92a6"), 0.8))
            for element, (a, b) in enumerate(zip(plan.positions_mm, plan.positions_mm[1:])):
                if element % element_step:
                    continue
                xa, xb = self._x(a), self._x(b)
                painter.setPen(QColor("#8ca0b2"))
                painter.drawText(QRectF(min(xa, xb), mesh_y + 14, abs(xb - xa), 15), Qt.AlignmentFlag.AlignCenter, f"e{element}")

        # Distributed rigid rotor components ([Massas]) at their actual spans.
        for index, mass in enumerate(engineering.distributed_masses):
            x0, x1 = self._x(mass.start_mm), self._x(mass.end_mm)
            height = max(34.0, mass.od_mm * sy)
            rect = QRectF(min(x0, x1), cy - height / 2, max(abs(x1 - x0), 3.0), height)
            selected = self._selected(current, "disks", index)
            painter.setPen(QPen(QColor("#0967a8" if selected else "#184f7d"), 2.6 if selected else 1.4))
            painter.setBrush(QColor("#78b5e6" if mass.is_package else "#9cc9ec"))
            painter.drawRect(rect)
            label = "Rotor package" if mass.is_package else mass.name
            painter.drawText(QRectF(rect.left() - 30, rect.top() - 23, rect.width() + 60, 20), Qt.AlignmentFlag.AlignCenter, label)
            node = plan.node_for(mass.center_mm)
            tooltip = (
                f"{mass.name}\nx = {mass.start_mm:g} … {mass.end_mm:g} mm\n"
                f"center = {mass.center_mm:g} mm · ROSS node {node}\n"
                f"mass = {mass.mass_kg:g} kg · OD = {mass.od_mm:g} mm\n"
                f"ROSS realization = DiskElement"
            )
            self._register(RotorEntityRef("disks", index, mass.name, mass.center_mm), rect, tooltip)

        disk_offset = len(engineering.distributed_masses)
        for local_index, disk in enumerate(engineering.disks):
            index = disk_offset + local_index
            x = self._x(disk.position_mm)
            rect = QRectF(x - 8, cy - 62, 16, 124)
            selected = self._selected(current, "disks", index)
            painter.setPen(QPen(QColor("#0967a8"), 2.6 if selected else 1.4))
            painter.setBrush(QColor("#78b5e6"))
            painter.drawRect(rect)
            node = plan.node_for(disk.position_mm)
            self._register(
                RotorEntityRef("disks", index, disk.name, disk.position_mm), rect,
                f"{disk.name}\nx = {disk.position_mm:g} mm · ROSS node {node}\nm = {disk.mass_kg:g} kg\nId = {disk.id_kg_m2:g} kg·m²\nIp = {disk.ip_kg_m2:g} kg·m²",
            )

        # Bearings and their flexible support chain.
        support_by_bearing = {support.bearing_index: (i, support) for i, support in enumerate(engineering.supports)}
        for index, bearing in enumerate(engineering.bearings):
            x = self._x(bearing.position_mm)
            rect = QRectF(x - 15, cy - 42, 30, 84)
            selected = self._selected(current, "bearings", index)
            painter.setPen(QPen(QColor("#075b99"), 2.7 if selected else 1.6))
            painter.setBrush(QColor("#4698d8"))
            painter.drawRect(rect)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(x - 7, cy - 7, 14, 14))
            painter.drawLine(QPointF(x - 10, cy - 12), QPointF(x + 10, cy + 12))
            painter.drawLine(QPointF(x + 10, cy - 12), QPointF(x - 10, cy + 12))
            node = plan.node_for(bearing.position_mm)
            support_entry = support_by_bearing.get(index)
            support_text = "grounded bearing"
            if support_entry is not None:
                support_index, support = support_entry
                sy0 = cy + 47
                painter.setPen(QPen(QColor("#677f94"), 1.2))
                painter.drawLine(QPointF(x, cy + 42), QPointF(x, sy0))
                srect = QRectF(x - 10, sy0, 20, 14)
                s_selected = self._selected(current, "supports", support_index)
                painter.setPen(QPen(QColor("#e48a16"), 2.5 if s_selected else 1.2))
                painter.setBrush(QColor("#f6a623"))
                painter.drawRect(srect)
                painter.setPen(QPen(QColor("#6b7f91"), 1.0))
                painter.drawLine(QPointF(x, sy0 + 14), QPointF(x, sy0 + 42))
                painter.drawLine(QPointF(x - 22, sy0 + 42), QPointF(x + 22, sy0 + 42))
                support_text = f"support = {support.name} · n_link = {len(plan.positions_mm) + support_index}"
                self._register(
                    RotorEntityRef("supports", support_index, support.name, bearing.position_mm), srect,
                    f"{support.name}\nattached to {bearing.name}\n{support_text}\nmass = {support.mass_kg:g} kg\nKxx = {support.kxx:.4g} N/m · Kyy = {support.kyy:.4g} N/m",
                )
            tooltip = (
                f"{bearing.name}\nx = {bearing.position_mm:g} mm · ROSS node {node}\n"
                f"model = {bearing.metadata.get('source_model', bearing.ross_class)}\n{support_text}"
            )
            self._register(RotorEntityRef("bearings", index, bearing.name, bearing.position_mm), rect, tooltip)

        # Loads are rendered as engineering arrows at exact stations.
        for index, load in enumerate(engineering.loads):
            x = self._x(load.position_mm)
            top = max(12.0, cy - max_d * sy / 2 - 62.0)
            selected = self._selected(current, "loads", index)
            painter.setPen(QPen(QColor("#e23d3d"), 2.5 if selected else 1.5))
            painter.drawLine(QPointF(x, top + 34), QPointF(x, top))
            painter.drawLine(QPointF(x, top), QPointF(x - 5, top + 10))
            painter.drawLine(QPointF(x, top), QPointF(x + 5, top + 10))
            rect = QRectF(x - 14, top - 4, 28, 42)
            node = plan.node_for(load.position_mm)
            self._register(
                RotorEntityRef("loads", index, load.name, load.position_mm), rect,
                f"{load.name}\ntype = {load.kind}\nx = {load.position_mm:g} mm · ROSS node {node}\nmagnitude = {load.magnitude:g}\nphase = {load.phase_deg:g}°",
            )

        # UMP spans and probes use their real physical coordinates.
        for index, spec in enumerate(project_ump_specs(engineering)):
            x0, x1 = self._x(spec.start_mm), self._x(spec.end_mm)
            y = max(16.0, cy - max_d * sy / 2 - 18.0)
            selected = self._selected(current, "ump", index)
            painter.setPen(QPen(QColor("#ad35a5"), 3.0 if selected else 1.8))
            painter.drawLine(QPointF(x0, y), QPointF(x1, y))
            painter.drawLine(QPointF(x0, y - 5), QPointF(x0, y + 5))
            painter.drawLine(QPointF(x1, y - 5), QPointF(x1, y + 5))
            rect = QRectF(min(x0, x1), y - 8, max(abs(x1 - x0), 4), 16)
            self._register(
                RotorEntityRef("ump", index, spec.name, 0.5 * (spec.start_mm + spec.end_mm)), rect,
                f"{spec.name}\nspan = {spec.start_mm:g} … {spec.end_mm:g} mm\nk′ = {spec.stiffness_per_length_n_m2:.6g} N/m²",
            )

        for index, probe in enumerate(engineering.probes):
            x = self._x(probe.position_mm)
            y = cy + max_d * sy / 2 + 12
            path = QPainterPath()
            path.moveTo(x, y)
            path.lineTo(x - 6, y + 10)
            path.lineTo(x + 6, y + 10)
            path.closeSubpath()
            selected = self._selected(current, "probes", index)
            painter.setPen(QPen(QColor("#1f8f66"), 2.4 if selected else 1.3))
            painter.setBrush(QColor("#bdebd9"))
            painter.drawPath(path)
            rect = QRectF(x - 8, y - 2, 16, 14)
            node = plan.node_for(probe.position_mm)
            self._register(
                RotorEntityRef("probes", index, probe.name, probe.position_mm), rect,
                f"{probe.name}\nx = {probe.position_mm:g} mm · ROSS node {node}\ncoordinate = {probe.coordinate}\norientation = {probe.orientation_deg:g}°",
            )

        painter.setPen(QColor("#173b63"))
        painter.drawText(QRectF(20, self.height() - 28, self.width() - 40, 20), Qt.AlignmentFlag.AlignRight,
                         f"Physical length {engineering.total_length_mm:,.1f} mm · base mesh {engineering.requested_shaft_element_count} · effective ROSS ShaftElements {plan.shaft_element_count}")
        painter.end()

    def _hit_at(self, point: QPointF) -> _HitRegion | None:
        # Last painted item wins so point elements remain selectable over shaft regions.
        for hit in reversed(self._hits):
            if hit.rect.contains(point):
                return hit
        return None

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.16 if event.angleDelta().y() > 0 else 1.0 / 1.16
        self._set_zoom(self._zoom * factor, event.position().x())
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_at(event.position())
            if hit is not None:
                self.selection.select(hit.ref)
                self.entity_activated.emit(hit.ref.kind, hit.ref.index)
                event.accept()
                return
            self._drag_from = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            now = event.position().toPoint()
            self._offset_x += now.x() - self._drag_from.x()
            self._drag_from = now
            self.update()
            event.accept()
            return
        hit = self._hit_at(event.position())
        if hit is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            QToolTip.showText(event.globalPosition().toPoint(), hit.tooltip, self)
        else:
            self.unsetCursor()
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            self._drag_from = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.fit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


__all__ = ["InteractiveRotorSketch"]