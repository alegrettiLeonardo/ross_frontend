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


@dataclass(slots=True, frozen=True)
class BearingStationElement:
    """One physical bearing element owned by a Bearing Studio station."""

    element_index: int
    role: str
    name: str
    position_mm: float
    ross_class: str
    source_model: str
    group: BearingGroup

    @property
    def axial(self) -> bool:
        return self.role == "axial_auxiliary"


@dataclass(slots=True, frozen=True)
class BearingStationInventory:
    """Traceable radial anchor plus any auxiliary elements at one shaft station."""

    station: BearingStation
    elements: tuple[BearingStationElement, ...]

    @property
    def radial_anchor(self) -> BearingStationElement:
        anchors = [element for element in self.elements if element.role == "radial_anchor"]
        if len(anchors) != 1:
            raise EngineeringError(
                f"Bearing station #{self.station.index + 1} must own exactly one radial anchor; received {len(anchors)}."
            )
        return anchors[0]

    @property
    def axial_auxiliaries(self) -> tuple[BearingStationElement, ...]:
        return tuple(element for element in self.elements if element.role == "axial_auxiliary")


class BearingWorkspaceService:
    """Resolve physical bearing-station identity independently from model class.

    Bearing Studio 2.0 treats the physical radial station as the first selection and
    the ROSS calculation class as a second, independent choice. Axial ThrustPad
    elements created by Apply are auxiliary elements at an existing station; they
    must never appear as a new DE/NDE station or become an implicit editing anchor.
    """

    POSITION_TOLERANCE_MM = 1e-9

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

        A radial element maps to itself. A ThrustPad auxiliary maps to the unique
        radial station at the same exact axial coordinate, so selecting an auxiliary
        never changes the editing identity to a non-selectable axial BearingSpec.
        """

        resolved = cls._raw_index(project, element_index)
        bearing = project.bearings[resolved]
        if cls._is_station_anchor(bearing):
            return resolved
        matches = [
            station.index
            for station in cls.stations(project)
            if abs(station.position_mm - float(bearing.position_mm)) <= cls.POSITION_TOLERANCE_MM
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

    @classmethod
    def station_elements(cls, project: RotorProject, index: int) -> tuple[BearingStationElement, ...]:
        """Return every bearing element physically owned by one station.

        The radial station anchor is always first. Auxiliary axial elements are then
        listed in engineering-domain order. Ownership is established through the same
        exact-position mapping used by ``anchor_index``; no nearest-node or nearest-
        coordinate association is permitted.
        """

        station = cls.station(project, index)
        rows: list[BearingStationElement] = []
        for element_index, bearing in enumerate(project.bearings):
            if element_index == station.index:
                role = "radial_anchor"
            elif cls._is_station_anchor(bearing):
                continue
            else:
                owner = cls.anchor_index(project, element_index)
                if owner != station.index:
                    continue
                role = "axial_auxiliary"

            rows.append(
                BearingStationElement(
                    element_index=element_index,
                    role=role,
                    name=bearing.name,
                    position_mm=float(bearing.position_mm),
                    ross_class=bearing.ross_class,
                    source_model=str(bearing.metadata.get("source_model", bearing.ross_class)),
                    group=bearing.group,
                )
            )

        inventory = BearingStationInventory(station=station, elements=tuple(rows))
        _ = inventory.radial_anchor
        return inventory.elements

    @classmethod
    def inventory(cls, project: RotorProject, index: int) -> BearingStationInventory:
        station = cls.station(project, index)
        inventory = BearingStationInventory(
            station=station,
            elements=cls.station_elements(project, station.index),
        )
        _ = inventory.radial_anchor
        return inventory


__all__ = [
    "BearingStation",
    "BearingStationElement",
    "BearingStationInventory",
    "BearingWorkspaceService",
]
