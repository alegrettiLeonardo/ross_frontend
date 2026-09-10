from __future__ import annotations

from typing import Any

from .domain import EngineeringError, RotorProject
from .ross_backend_base import *  # noqa: F401,F403
from .ross_backend_base import RossBackend as _BaseRossBackend
from .ross_backend_base import RossBuildResult, RossModelBuilder as _BaseRossModelBuilder


class RossModelBuilder(_BaseRossModelBuilder):
    """Qualified builder extension that realizes first-class seal dynamics.

    ROSS Studio 0.14 keeps the previously qualified builder byte-for-byte in
    ``ross_backend_base`` and adds only the explicit ROSS ``SealElement`` contract.
    Couplings and loads remain engineering/analysis inputs until their own physical
    assembly contracts are complete; they are never silently converted here.
    """

    def build(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        result = super().build(project, strict=strict)
        if not project.seals:
            return result

        rs = self._ross()
        seals: list[Any] = []
        for spec in project.seals:
            mapping = self.map_position(project, spec.position_mm)
            if mapping.node is None:
                if strict:
                    raise EngineeringError(
                        f"Seal {spec.name!r} is not located at an exact FE node."
                    )
                continue
            seals.append(
                rs.SealElement(
                    n=mapping.node,
                    kxx=spec.kxx,
                    kyy=spec.kyy,
                    kxy=spec.kxy,
                    kyx=spec.kyx,
                    cxx=spec.cxx,
                    cyy=spec.cyy,
                    cxy=spec.cxy,
                    cyx=spec.cyx,
                    tag=spec.name,
                )
            )

        # Rebuild the ROSS Rotor once with the newly qualified seal elements. The
        # existing shaft, disk, bearing/support and point-mass objects come from the
        # already qualified base builder; no coefficients are regenerated or altered.
        existing_bearings = list(result.rotor.bearing_elements)
        rotor = rs.Rotor(
            shaft_elements=list(result.rotor.shaft_elements),
            disk_elements=list(result.rotor.disk_elements) or None,
            bearing_elements=[*existing_bearings, *seals] or None,
            point_mass_elements=list(result.rotor.point_mass_elements) or None,
            tag=project.name,
        )
        result.rotor = rotor
        return result


class RossBackend(_BaseRossBackend):
    """Application boundary using the 0.14 seal-aware strict builder."""

    def __init__(self, ross_module: Any | None = None) -> None:
        self.builder = RossModelBuilder(ross_module)


__all__ = [
    "EquivalentDiskPlan",
    "EquivalentPointMassPlan",
    "NodeMapping",
    "RossBackend",
    "RossBuildResult",
    "RossModelBuilder",
    "ShaftElementPlan",
]
