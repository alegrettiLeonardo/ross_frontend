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

    @property
    def mesh_node(self) -> bool:
        return any(reason.startswith("mesh:") for reason in self.reasons)


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

    @property
    def mesh_positions_mm(self) -> tuple[float, ...]:
        return tuple(item.position_mm for item in self.insertions if item.mesh_node)

    def node_for(self, position_mm: float, *, tolerance_mm: float = 1e-7) -> int | None:
        for node, x in enumerate(self.positions_mm):
            if abs(x - position_mm) <= tolerance_mm:
                return node
        return None


class NodeInsertionService:
    """Build the ROSS shaft topology without snapping physical entities.

    Each physical shaft section first receives its user-requested base finite-element
    discretization (``ShaftSection.fe_elements``). Exact physical coordinates required
    by bearings, masses, disks, seals, couplings, loads and probes are then unioned with
    that base mesh. Consequently ``fe_elements`` is a minimum mesh density per physical
    section; mandatory engineering stations may split those elements further, but they
    are never shifted to a nearest node.
    """

    @staticmethod
    def plan(project: "RotorProject") -> NodeInsertionPlan:
        boundaries = {round(x, 10) for x in project.section_boundaries_mm()}
        reasons: dict[float, list[str]] = defaultdict(list)
        base_mesh: set[float] = set(boundaries)

        def request(position_mm: float, reason: str) -> None:
            x = round(float(position_mm), 10)
            if reason not in reasons[x]:
                reasons[x].append(reason)

        start = 0.0
        for section in project.shaft_sections:
            count = int(section.fe_elements)
            for local_node in range(1, count):
                x = round(start + section.length_mm * local_node / count, 10)
                base_mesh.add(x)
                request(x, f"mesh:S{section.section}:{local_node}/{count}")
            start += section.length_mm

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

        positions = tuple(sorted(base_mesh | set(reasons)))
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
