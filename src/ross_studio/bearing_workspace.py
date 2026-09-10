from __future__ import annotations

from dataclasses import dataclass

from .domain import BearingGroup, EngineeringError, RotorProject
from .topology import NodeInsertionService


@dataclass(slots=True, frozen=True)
class BearingStation:
    """One selectable physical radial-bearing station in the engineering model."""

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
        node = "unresolved" if self.ross_node is None else str(self.ross_node)
        return f"{self.name} · x={self.position_mm:g} mm · node {node} · {self.source_model}{support}"


class BearingWorkspaceService:
    """Resolve physical bearing-station identity independently from model class.

    Bearing Studio 2.0 treats the physical radial station as the first selection and
    the ROSS calculation class as a second, independent choice. Axial ThrustPad
    elements created by Apply are auxiliary elements at an existing station; they
    must never appear as a new DE/NDE station or become an implicit editing anchor.
    """

    @staticmethod
    def _is_station_anchor(bearing) -> bool:
        # The qualified ThrustPad adapter stores an axial Kzz/Czz table and adds a
        # separate BearingSpec at the selected radial station. That spec is physical
        # rotor content, but not a new selectable shaft station.
        return not bool(bearing.metadata.get("axial_coefficients"))

    @classmethod
    def resolve_index(cls, project: RotorProject, index: int) -> int:
        try:
            resolved = int(index)
        except (TypeError, ValueError) as exc:
            raise EngineeringError(f"Bearing index must be an integer; received {index!r}.") from exc
        if resolved < 0 or resolved >= len(project.bearings):
            raise EngineeringError(
                f"Bearing index {resolved} is outside the project range 0..{max(len(project.bearings) - 1, 0)}."
            )
        if not cls._is_station_anchor(project.bearings[resolved]):
            raise EngineeringError(
                f"Bearing index {resolved} is an axial auxiliary element, not a selectable physical radial station."
            )
        return resolved

    @classmethod
    def stations(cls, project: RotorProject) -> tuple[BearingStation, ...]:
        if not project.bearings:
            return ()
        plan = NodeInsertionService.plan(project)
        rows: list[BearingStation] = []
        for index, bearing in enumerate(project.bearings):
            if not cls._is_station_anchor(bearing):
                continue
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
        for station in cls.stations(project):
            if station.index == resolved:
                return station
        raise EngineeringError(f"Bearing index {resolved} did not resolve to a physical station.")


__all__ = ["BearingStation", "BearingWorkspaceService"]
