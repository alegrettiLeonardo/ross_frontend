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
        # A valid qualified ThrustPad auxiliary carries both source_model and the
        # solved axial table. Treat either marker as sufficient to avoid exposing a
        # malformed/partially migrated axial element as a new radial station.
        return not (
            str(bearing.metadata.get("source_model", "")) == "ThrustPad"
            or bool(bearing.metadata.get("axial_coefficients"))
        )

    @staticmethod
    def _raw_index(project: RotorProject, index: int) -> int:
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
    def resolve_index(cls, project: RotorProject, index: int) -> int:
        resolved = cls._raw_index(project, index)
        if not cls._is_station_anchor(project.bearings[resolved]):
            raise EngineeringError(
                f"Bearing index {resolved} is an axial auxiliary element, not a selectable physical radial station."
            )
        return resolved

    @classmethod
    def anchor_index(cls, project: RotorProject, element_index: int) -> int:
        """Map any visible bearing element back to its physical radial station.

        This is used by sketch hit-testing. A radial element maps to itself. A
        ThrustPad auxiliary maps to the unique radial station at the same axial
        coordinate, so clicking the auxiliary graphic never changes the editing
        identity to a non-selectable axial BearingSpec.
        """

        resolved = cls._raw_index(project, element_index)
        bearing = project.bearings[resolved]
        if cls._is_station_anchor(bearing):
            return resolved
        matches = [
            station.index
            for station in cls.stations(project)
            if abs(station.position_mm - float(bearing.position_mm)) <= 1e-9
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise EngineeringError(
                f"Axial bearing element #{resolved + 1} at {bearing.position_mm:g} mm has no physical radial station anchor."
            )
        raise EngineeringError(
            f"Axial bearing element #{resolved + 1} at {bearing.position_mm:g} mm maps to multiple radial stations {matches}."
        )

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
