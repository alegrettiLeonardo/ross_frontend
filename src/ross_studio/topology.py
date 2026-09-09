from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .domain import RotorProject


@dataclass(slots=True, frozen=True)
class NodeInsertion:
    position_mm: float
    reasons: tuple[str, ...]
    section_boundary: bool


@dataclass(slots=True, frozen=True)
class NodeInsertionPlan:
    positions_mm: tuple[float, ...]
    insertions: tuple[NodeInsertion, ...]

    @property
    def shaft_element_count(self) -> int:
        return max(0, len(self.positions_mm) - 1)

    @property
    def inserted_positions_mm(self) -> tuple[float, ...]:
        return tuple(item.position_mm for item in self.insertions if not item.section_boundary)

    def node_for(self, position_mm: float, *, tolerance_mm: float = 1e-7) -> int | None:
        for node, x in enumerate(self.positions_mm):
            if abs(x - position_mm) <= tolerance_mm:
                return node
        return None


class NodeInsertionService:
    """Create the FE node topology from physical coordinates without nearest-node snapping.

    Physical shaft-section boundaries are kept exactly. Every point entity that needs a
    ROSS node requests its physical axial coordinate explicitly. Legacy ``[Massas]``
    additionally request start/end boundaries plus the rigid-equivalent disk center.
    """

    @staticmethod
    def plan(project: "RotorProject") -> NodeInsertionPlan:
        boundaries = {round(x, 10) for x in project.section_boundaries_mm()}
        reasons: dict[float, list[str]] = defaultdict(list)

        def request(position_mm: float, reason: str) -> None:
            x = round(float(position_mm), 10)
            if reason not in reasons[x]:
                reasons[x].append(reason)

        for index, bearing in enumerate(project.bearings, 1):
            request(bearing.position_mm, f"bearing:{index}:{bearing.name}")

        for index, mass in enumerate(project.distributed_masses, 1):
            request(mass.start_mm, f"legacy-mass-start:{index}:{mass.name}")
            request(mass.center_mm, f"legacy-mass-center:{index}:{mass.name}")
            request(mass.end_mm, f"legacy-mass-end:{index}:{mass.name}")

        for index, mass in enumerate(project.point_masses, 1):
            request(mass.position_mm, f"point-mass:{index}:{mass.name}")

        for index, disk in enumerate(project.disks, 1):
            request(disk.position_mm, f"disk:{index}:{disk.name}")

        for index, seal in enumerate(project.seals, 1):
            request(seal.position_mm, f"seal:{index}:{seal.name}")

        for index, coupling in enumerate(project.couplings, 1):
            request(coupling.position_mm, f"coupling:{index}:{coupling.name}")

        for index, load in enumerate(project.loads, 1):
            request(load.position_mm, f"load:{index}:{load.name}")

        for index, probe in enumerate(project.probes, 1):
            request(probe.position_mm, f"probe:{index}:{probe.name}")

        positions = tuple(sorted(boundaries | set(reasons)))
        insertions = tuple(
            NodeInsertion(
                position_mm=x,
                reasons=tuple(reasons.get(x, ())),
                section_boundary=x in boundaries,
            )
            for x in positions
        )
        return NodeInsertionPlan(positions_mm=positions, insertions=insertions)


__all__ = ["NodeInsertion", "NodeInsertionPlan", "NodeInsertionService"]
