from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import numpy as np

from .domain import EngineeringError

if TYPE_CHECKING:
    from .domain import PointMassSpec, RotorProject
    from .ross_backend import RossBuildResult


@dataclass(slots=True, frozen=True)
class ConcentratedMassInertiaPlan:
    """Trace of one legacy ``[Concent]`` mass/inertia realization.

    RotorDin stores one concentrated body as ``x, mass, Ix, Iy, Iz`` where the
    shaft axis is the legacy y-axis. ROSS uses the axial z-axis and six DOFs per
    shaft node. The physical principal-inertia mapping used here is therefore::

        RotorDin mass -> ROSS x/y/z translations
        RotorDin Ix   -> ROSS alpha-alpha inertia
        RotorDin Iz   -> ROSS beta-beta inertia
        RotorDin Iy   -> ROSS theta-theta polar inertia and alpha/beta gyro pair

    The positive-rotation sign is handled separately by ``RotorDinConventionMixin``.
    """

    name: str
    node: int
    position_mm: float
    mass_kg: float
    ix_kg_m2: float
    iy_kg_m2: float
    iz_kg_m2: float
    source: str = "legacy iRdin [Concent]"


def validate_concentrated_spec(spec: "PointMassSpec") -> None:
    values = (
        spec.position_mm,
        spec.mass_kg,
        spec.ix_kg_m2,
        spec.iy_kg_m2,
        spec.iz_kg_m2,
    )
    if not all(np.isfinite(value) for value in values):
        raise EngineeringError(f"{spec.name}: concentrated mass/inertia input contains a non-finite value.")
    if spec.mass_kg < 0.0:
        raise EngineeringError(f"{spec.name}: concentrated mass cannot be negative.")
    if min(spec.ix_kg_m2, spec.iy_kg_m2, spec.iz_kg_m2) < 0.0:
        raise EngineeringError(f"{spec.name}: principal inertias Ix/Iy/Iz cannot be negative.")


def concentrated_disk_class(ross_module: Any) -> type[Any]:
    """Return a ROSS ``DiskElement`` subclass with independent principal inertias.

    Native ROSS ``DiskElement`` accepts one diametral inertia ``Id`` for both
    lateral rotations. RotorDin ``[Concent]`` permits ``Ix != Iz``. This adapter
    keeps ROSS' element/node integration and static-weight bookkeeping while
    overriding only the rigid-body mass matrix. ``Ip`` is set to ``Iy`` so the
    native ROSS gyroscopic and angular-acceleration terms remain physically
    consistent; the RotorDin-positive convention layer flips the gyro sign when
    required by an imported project.
    """

    base = ross_module.DiskElement

    class ConcentratedMassInertiaElement(base):
        def __init__(
            self,
            n: int,
            m: float,
            ix_kg_m2: float,
            iy_kg_m2: float,
            iz_kg_m2: float,
            *,
            tag: str | None = None,
        ) -> None:
            self.Ix = float(ix_kg_m2)
            self.Iy = float(iy_kg_m2)
            self.Iz = float(iz_kg_m2)
            if min(float(m), self.Ix, self.Iy, self.Iz) < 0.0:
                raise EngineeringError("Concentrated mass and principal inertias must be non-negative.")
            # Id is intentionally not used by M(); Ip=Iy keeps native ROSS G/Kdt.
            super().__init__(n=int(n), m=float(m), Id=0.0, Ip=self.Iy, tag=tag)

        def M(self) -> np.ndarray:
            return np.diag(
                [
                    self.m,
                    self.m,
                    self.m,
                    self.Ix,
                    self.Iz,
                    self.Iy,
                ]
            ).astype(float)

    ConcentratedMassInertiaElement.__name__ = "ConcentratedMassInertiaElement"
    ConcentratedMassInertiaElement.__qualname__ = "ConcentratedMassInertiaElement"
    ConcentratedMassInertiaElement.__module__ = __name__
    return ConcentratedMassInertiaElement


def adapted_disk_elements(
    ross_module: Any,
    project: "RotorProject",
    build: "RossBuildResult",
) -> tuple[list[Any], tuple[ConcentratedMassInertiaPlan, ...], bool]:
    """Replace scalar ``[Concent]`` placeholders with exact inertia elements.

    ``RossModelBuilder`` already creates one zero-inertia DiskElement per legacy
    concentrated mass to preserve static gravity and historical scalar cases. This
    function replaces only those tagged placeholders. A Rotor reconstruction is
    then required so ROSS recomputes its cached global matrices from the adapted
    elements.
    """

    element_cls = concentrated_disk_class(ross_module)
    replacements: dict[str, Any] = {}
    plans: list[ConcentratedMassInertiaPlan] = []

    for spec in project.point_masses:
        validate_concentrated_spec(spec)
        node = build.node_insertion_plan.node_for(spec.position_mm)
        if node is None:
            raise EngineeringError(
                f"{spec.name} at {spec.position_mm:g} mm has no exact node for concentrated inertia assembly."
            )
        tag = f"{spec.name} / shaft point mass"
        replacements[tag] = element_cls(
            node,
            spec.mass_kg,
            spec.ix_kg_m2,
            spec.iy_kg_m2,
            spec.iz_kg_m2,
            tag=tag,
        )
        plans.append(
            ConcentratedMassInertiaPlan(
                name=spec.name,
                node=node,
                position_mm=float(spec.position_mm),
                mass_kg=float(spec.mass_kg),
                ix_kg_m2=float(spec.ix_kg_m2),
                iy_kg_m2=float(spec.iy_kg_m2),
                iz_kg_m2=float(spec.iz_kg_m2),
            )
        )

    if not replacements:
        return list(build.rotor.disk_elements), tuple(), False

    found: set[str] = set()
    adapted: list[Any] = []
    for element in build.rotor.disk_elements:
        tag = str(getattr(element, "tag", ""))
        if tag in replacements:
            adapted.append(replacements[tag])
            found.add(tag)
        else:
            adapted.append(element)

    missing = sorted(set(replacements) - found)
    if missing:
        raise EngineeringError(
            "Concentrated inertia adapter could not find builder placeholder(s): " + ", ".join(missing)
        )
    return adapted, tuple(plans), True


__all__ = [
    "ConcentratedMassInertiaPlan",
    "adapted_disk_elements",
    "concentrated_disk_class",
    "validate_concentrated_spec",
]
