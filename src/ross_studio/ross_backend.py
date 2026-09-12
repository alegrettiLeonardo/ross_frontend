from __future__ import annotations

from math import pi
from typing import Any

import numpy as np

from .domain import EngineeringError, FoundationModel, FoundationSpec, RotorProject
from .ross_backend_base import *  # noqa: F401,F403
from .ross_backend_base import RossBackend as _BaseRossBackend
from .ross_backend_base import RossBuildResult, RossModelBuilder as _BaseRossModelBuilder


class RossModelBuilder(_BaseRossModelBuilder):
    """Qualified builder extension for seals and Foundation Studio 0.24.

    The 0.23 base builder remains untouched. Foundation Studio only rebuilds the
    external support chain when a non-rigid FoundationSpec is explicitly present::

        shaft -> bearing -> support node -> support K/C -> foundation node
              -> foundation K/C -> ground

    Support mass stays on the support node. LUMPED_KCM adds Foundation mass on the
    foundation node; LUMPED_KC and FREQUENCY_DEPENDENT_KC retain an exact zero-mass
    algebraic node instead of inventing epsilon mass. RIGID and absent FoundationSpec
    leave the previously qualified support-to-ground topology byte-for-byte unchanged.
    """

    def _foundation_ground_element(self, rs: Any, spec: FoundationSpec, node: int) -> Any:
        if spec.model_type == FoundationModel.FREQUENCY_DEPENDENT_KC:
            frequency = np.asarray([point.frequency_hz for point in spec.coefficients], dtype=float) * 2.0 * pi
            return rs.BearingElement(
                n=node,
                kxx=np.asarray([point.kxx for point in spec.coefficients], dtype=float),
                kyy=np.asarray([point.kyy for point in spec.coefficients], dtype=float),
                kxy=np.asarray([point.kxy for point in spec.coefficients], dtype=float),
                kyx=np.asarray([point.kyx for point in spec.coefficients], dtype=float),
                cxx=np.asarray([point.cxx for point in spec.coefficients], dtype=float),
                cyy=np.asarray([point.cyy for point in spec.coefficients], dtype=float),
                cxy=np.asarray([point.cxy for point in spec.coefficients], dtype=float),
                cyx=np.asarray([point.cyx for point in spec.coefficients], dtype=float),
                frequency=frequency,
                tag=f"{spec.name} / ground",
            )
        return rs.BearingElement(
            n=node,
            kxx=spec.kxx,
            kyy=spec.kyy,
            kxy=spec.kxy,
            kyx=spec.kyx,
            cxx=spec.cxx,
            cyy=spec.cyy,
            cxy=spec.cxy,
            cyx=spec.cyx,
            tag=f"{spec.name} / ground",
        )

    def _apply_foundations(self, result: RossBuildResult, project: RotorProject) -> None:
        dynamic = [foundation for foundation in project.foundations if foundation.model_type != FoundationModel.RIGID]
        if not dynamic:
            return

        rs = self._ross()
        support_by_index = {index: support for index, support in enumerate(project.supports)}
        existing_bearings = list(result.rotor.bearing_elements)
        existing_point_masses = list(result.rotor.point_mass_elements)
        replaced_support_tags = {
            f"{support_by_index[foundation.support_index].name} / ground"
            for foundation in dynamic
        }
        retained_bearings = [
            element
            for element in existing_bearings
            if getattr(element, "tag", "") not in replaced_support_tags
        ]

        occupied_external_nodes = list(result.support_link_nodes.values())
        next_node = (max(occupied_external_nodes) + 1) if occupied_external_nodes else len(result.node_positions_mm)
        foundation_elements: list[Any] = []
        foundation_masses: list[Any] = []
        self.last_foundation_nodes = {}

        for foundation in dynamic:
            support = support_by_index[foundation.support_index]
            support_node = result.support_link_nodes.get(support.name)
            if support_node is None:
                raise EngineeringError(
                    f"Foundation {foundation.name!r} owns support {support.name!r}, but that support has no qualified ROSS n_link node."
                )
            foundation_node = next_node
            next_node += 1
            self.last_foundation_nodes[foundation.name] = foundation_node

            foundation_elements.append(
                rs.BearingElement(
                    n=support_node,
                    n_link=foundation_node,
                    kxx=support.kxx,
                    kyy=support.kyy or support.kxx,
                    kxy=support.kxy,
                    kyx=support.kyx,
                    cxx=support.cxx,
                    cyy=support.cyy or support.cxx,
                    cxy=support.cxy,
                    cyx=support.cyx,
                    tag=f"{support.name} / foundation",
                )
            )
            foundation_elements.append(self._foundation_ground_element(rs, foundation, foundation_node))
            foundation_masses.append(
                rs.PointMass(
                    n=foundation_node,
                    m=foundation.mass_kg,
                    tag=f"{foundation.name} mass",
                )
            )

        result.rotor = rs.Rotor(
            shaft_elements=list(result.rotor.shaft_elements),
            disk_elements=list(result.rotor.disk_elements) or None,
            bearing_elements=[*retained_bearings, *foundation_elements] or None,
            point_mass_elements=[*existing_point_masses, *foundation_masses] or None,
            tag=project.name,
        )

    def build(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        result = super().build(project, strict=strict)
        self.last_foundation_nodes: dict[str, int] = {}
        self._apply_foundations(result, project)

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
    """Application boundary using the 0.24 foundation/seal-aware strict builder."""

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
