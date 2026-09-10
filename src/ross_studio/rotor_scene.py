from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .rotor_scene_base import InteractiveRotorSketch as _BaseInteractiveRotorSketch
from .rotor_selection import RotorEntityRef
from .topology import NodeInsertionService


class InteractiveRotorSketch(_BaseInteractiveRotorSketch):
    """Engineering sketch with first-class interactive ``[Concent]`` bodies.

    The qualified 0.12 sketch remains the rendering base. ROSS Studio 0.14 overlays
    concentrated shaft-station bodies after the base paint pass so their identity,
    principal inertias and exact ROSS node are visible and selectable in the same
    composite ``disks`` index space used by the engineering table.
    """

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        engineering = self.project.engineering
        if engineering is None or not engineering.point_masses:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        plan = NodeInsertionService.plan(engineering)
        current = self.selection.current
        cy = self.height() * 0.43
        index_offset = len(engineering.distributed_masses) + len(engineering.disks)

        for local_index, mass in enumerate(engineering.point_masses):
            index = index_offset + local_index
            x = self._x(mass.position_mm)
            half = 10.0
            path = QPainterPath()
            path.moveTo(QPointF(x, cy - half))
            path.lineTo(QPointF(x + half, cy))
            path.lineTo(QPointF(x, cy + half))
            path.lineTo(QPointF(x - half, cy))
            path.closeSubpath()

            selected = self._selected(current, "disks", index)
            painter.setPen(QPen(QColor("#713fa3"), 3.0 if selected else 1.6))
            painter.setBrush(QColor("#eadcf7" if selected else "#f3eafb"))
            painter.drawPath(path)
            painter.setPen(QColor("#542b7a"))
            painter.drawText(
                QRectF(x - half, cy - half, 2.0 * half, 2.0 * half),
                Qt.AlignmentFlag.AlignCenter,
                "C",
            )

            node = plan.node_for(mass.position_mm)
            rect = QRectF(x - half - 3.0, cy - half - 3.0, 2.0 * half + 6.0, 2.0 * half + 6.0)
            tooltip = (
                f"{mass.name} — [Concent]\n"
                f"x = {mass.position_mm:g} mm · ROSS node {node}\n"
                f"mass = {mass.mass_kg:g} kg\n"
                f"Ix = {mass.ix_kg_m2:g} kg·m² · Iy = {mass.iy_kg_m2:g} kg·m² · Iz = {mass.iz_kg_m2:g} kg·m²\n"
                "ROSS realization = qualified concentrated DiskElement"
            )
            self._register(
                RotorEntityRef("disks", index, mass.name, mass.position_mm),
                rect,
                tooltip,
            )
        painter.end()


__all__ = ["InteractiveRotorSketch"]
