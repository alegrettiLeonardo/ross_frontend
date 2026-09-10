from __future__ import annotations

from dataclasses import dataclass

from .domain import BearingGroup, EngineeringError, RotorProject
from .topology import NodeInsertionService


@dataclass(slots=True, frozen=True)
class BearingStation:
    """One selectable physical bearing station in the engineering model."""

    index: int
    name: str
    position_mm: float
    ross_node: int | None
    source_model: str
    group: BearingGroup
    support_names: tuple[str, ...]

    @property
    def display_label(self) -> str:
        support = f" · support: {', '.join(self.support_names)}" if self.support_names else ""
        return f"{self.name} · x={self.position_mm:g} mm · node {self.ross_node} · {self.source_model}{support}"


class BearingWorkspaceService:
    """Resolve bearing identity independently from the selected calculation class.

    Bearing Studio 2.0 treats the physical station as the first selection. The
    selected ROSS calculation class is a second, independent choice. This avoids the
    previous implicit ``bearing_index=0`` contract and makes Calculate/Preview/Apply
    transactions traceable to one explicit DE/NDE (or future) bearing station.
    """

    @staticmethod
    def resolve_index(project: RotorProject, index: int) -> int:
        try:
            resolved = int(index)
        except (TypeError, ValueError) as exc:
            raise EngineeringError(f"Bearing index must be an integer; received {index!r}.") from exc
        if resolved < 0 or resolved >= len(project.bearings):
            raise EngineeringError(
                f"Bearing index {resolved} is outside the project range 0..{max(len(project.bearings) - 1, 0)}."
            )
        return resolved

    @classmethod
    def stations(cls, project: RotorProject) -> tuple[BearingStation, ...]:
        if not project.bearings:
            return ()
        plan = NodeInsertionService.plan(project)
        rows: list[BearingStation] = []
        for index, bearing in enumerate(project.bearings):
            support_names = tuple(
                support.name for support in project.supports if support.bearing_index == index
            )
            source_model = str(bearing.metadata.get("source_model", bearing.ross_class))
            rows.append(
                BearingStation(
                    index=index,
                    name=bearing.name,
                    position_mm=float(bearing.position_mm),
                    ross_node=plan.node_for(bearing.position_mm),
                    source_model=source_model,
                    group=bearing.group,
                    support_names=support_names,
                )
            )
        return tuple(rows)

    @classmethod
    def station(cls, project: RotorProject, index: int) -> BearingStation:
        resolved = cls.resolve_index(project, index)
        return cls.stations(project)[resolved]


__all__ = ["BearingStation", "BearingWorkspaceService"]
