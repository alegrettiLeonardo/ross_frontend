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

    Foundation ownership is always ``bearing -> support -> foundation -> ground`` at
    the engineering-model level, but the ROSS realization depends on whether the
    Foundation owns physical inertia:

    * RIGID keeps the previously qualified support-to-ground element unchanged.
    * LUMPED_KC with zero damping is statically condensed onto the support node.
      This is an exact Schur complement and therefore does not invent an epsilon
      mass or leave a zero-mass algebraic node in the ROSS mass matrix.
    * FREQUENCY_DEPENDENT_KC is condensed as complex dynamic stiffness at every
      supplied frequency and realized as a native frequency-dependent ROSS bearing.
    * LUMPED_KCM keeps an explicit Foundation node because its mass is physical.

    A massless constant-K/C two-stage chain with non-zero damping has a rational,
    frequency-dependent equivalent impedance. It cannot be represented exactly by a
    single constant ROSS BearingElement, so that contract fails closed rather than
    silently approximating the physics.
    """

    @staticmethod
    def _support_matrices(support: Any) -> tuple[np.ndarray, np.ndarray]:
        k = np.asarray(
            [
                [support.kxx, support.kxy],
                [support.kyx, support.kyy or support.kxx],
            ],
            dtype=float,
        )
        c = np.asarray(
            [
                [support.cxx, support.cxy],
                [support.cyx, support.cyy or support.cxx],
            ],
            dtype=float,
        )
        return k, c

    @staticmethod
    def _foundation_matrices(spec: FoundationSpec) -> tuple[np.ndarray, np.ndarray]:
        k = np.asarray([[spec.kxx, spec.kxy], [spec.kyx, spec.kyy]], dtype=float)
        c = np.asarray([[spec.cxx, spec.cxy], [spec.cyx, spec.cyy]], dtype=float)
        return k, c

    @staticmethod
    def _solve_series_impedance(z_support: np.ndarray, z_foundation: np.ndarray, *, name: str) -> np.ndarray:
        """Condense the internal Foundation DOF exactly in the frequency domain."""

        total = z_support + z_foundation
        try:
            solved = np.linalg.solve(total, z_support)
        except np.linalg.LinAlgError as exc:
            raise EngineeringError(
                f"Foundation {name!r} cannot be condensed because support + foundation impedance is singular."
            ) from exc
        equivalent = z_support - z_support @ solved
        if not np.all(np.isfinite(equivalent)):
            raise EngineeringError(f"Foundation {name!r} condensation produced non-finite coefficients.")
        return equivalent

    @classmethod
    def _static_series_stiffness(cls, k_support: np.ndarray, k_foundation: np.ndarray, *, name: str) -> np.ndarray:
        return np.asarray(
            cls._solve_series_impedance(
                np.asarray(k_support, dtype=complex),
                np.asarray(k_foundation, dtype=complex),
                name=name,
            ).real,
            dtype=float,
        )

    @classmethod
    def _zero_frequency_series_damping(
        cls,
        k_support: np.ndarray,
        c_support: np.ndarray,
        k_foundation: np.ndarray,
        c_foundation: np.ndarray,
        *,
        name: str,
    ) -> np.ndarray:
        """Return d(Im(Zeq))/dω at ω=0 without finite differencing."""

        total_k = k_support + k_foundation
        total_c = c_support + c_foundation
        try:
            a_inv_ks = np.linalg.solve(total_k, k_support)
            a_inv_cs = np.linalg.solve(total_k, c_support)
            a_inv_b_a_inv_ks = np.linalg.solve(total_k, total_c @ a_inv_ks)
        except np.linalg.LinAlgError as exc:
            raise EngineeringError(
                f"Foundation {name!r} zero-frequency condensation is singular."
            ) from exc
        equivalent = (
            c_support
            - c_support @ a_inv_ks
            - k_support @ a_inv_cs
            + k_support @ a_inv_b_a_inv_ks
        )
        if not np.all(np.isfinite(equivalent)):
            raise EngineeringError(f"Foundation {name!r} zero-frequency damping condensation produced non-finite coefficients.")
        return np.asarray(equivalent, dtype=float)

    @staticmethod
    def _matrix_coefficients(matrix: np.ndarray) -> tuple[float, float, float, float]:
        return (
            float(matrix[0, 0]),
            float(matrix[1, 1]),
            float(matrix[0, 1]),
            float(matrix[1, 0]),
        )

    def _foundation_ground_element(self, rs: Any, spec: FoundationSpec, node: int) -> Any:
        """Ground element for a physical-mass LUMPED_KCM Foundation node."""

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

    def _massless_lumped_element(self, rs: Any, support: Any, spec: FoundationSpec, node: int) -> Any:
        k_support, c_support = self._support_matrices(support)
        k_foundation, c_foundation = self._foundation_matrices(spec)
        if np.any(c_support != 0.0) or np.any(c_foundation != 0.0):
            raise EngineeringError(
                f"Foundation {spec.name!r} is massless LUMPED_KC with non-zero damping. "
                "Eliminating its internal DOF produces a frequency-dependent rational impedance, "
                "which cannot be represented exactly by one constant ROSS BearingElement. "
                "Use LUMPED_KCM with physical mass or FREQUENCY_DEPENDENT_KC; no epsilon mass or constant-K/C approximation is applied."
            )
        equivalent_k = self._static_series_stiffness(k_support, k_foundation, name=spec.name)
        kxx, kyy, kxy, kyx = self._matrix_coefficients(equivalent_k)
        return rs.BearingElement(
            n=node,
            kxx=kxx,
            kyy=kyy,
            kxy=kxy,
            kyx=kyx,
            cxx=0.0,
            cyy=0.0,
            cxy=0.0,
            cyx=0.0,
            tag=f"{spec.name} / condensed ground",
        )

    def _frequency_dependent_condensed_element(self, rs: Any, support: Any, spec: FoundationSpec, node: int) -> Any:
        k_support, c_support = self._support_matrices(support)
        frequency = np.asarray([point.frequency_hz for point in spec.coefficients], dtype=float) * 2.0 * pi
        equivalent_k: list[np.ndarray] = []
        equivalent_c: list[np.ndarray] = []

        for omega, point in zip(frequency, spec.coefficients):
            k_foundation = np.asarray([[point.kxx, point.kxy], [point.kyx, point.kyy]], dtype=float)
            c_foundation = np.asarray([[point.cxx, point.cxy], [point.cyx, point.cyy]], dtype=float)
            if abs(float(omega)) <= np.finfo(float).eps:
                k_eq = self._static_series_stiffness(k_support, k_foundation, name=spec.name)
                c_eq = self._zero_frequency_series_damping(
                    k_support,
                    c_support,
                    k_foundation,
                    c_foundation,
                    name=spec.name,
                )
            else:
                z_support = k_support.astype(complex) + 1j * float(omega) * c_support
                z_foundation = k_foundation.astype(complex) + 1j * float(omega) * c_foundation
                z_eq = self._solve_series_impedance(z_support, z_foundation, name=spec.name)
                k_eq = np.asarray(z_eq.real, dtype=float)
                c_eq = np.asarray(z_eq.imag / float(omega), dtype=float)
            equivalent_k.append(k_eq)
            equivalent_c.append(c_eq)

        k_arrays = np.asarray(equivalent_k, dtype=float)
        c_arrays = np.asarray(equivalent_c, dtype=float)
        return rs.BearingElement(
            n=node,
            kxx=k_arrays[:, 0, 0],
            kyy=k_arrays[:, 1, 1],
            kxy=k_arrays[:, 0, 1],
            kyx=k_arrays[:, 1, 0],
            cxx=c_arrays[:, 0, 0],
            cyy=c_arrays[:, 1, 1],
            cxy=c_arrays[:, 0, 1],
            cyx=c_arrays[:, 1, 0],
            frequency=frequency,
            tag=f"{spec.name} / condensed ground",
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

            if foundation.model_type == FoundationModel.LUMPED_KC:
                foundation_elements.append(self._massless_lumped_element(rs, support, foundation, support_node))
                continue

            if foundation.model_type == FoundationModel.FREQUENCY_DEPENDENT_KC:
                foundation_elements.append(
                    self._frequency_dependent_condensed_element(rs, support, foundation, support_node)
                )
                continue

            if foundation.model_type != FoundationModel.LUMPED_KCM:
                raise EngineeringError(
                    f"Foundation {foundation.name!r} model {foundation.model_type.value} has no qualified ROSS realization."
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
