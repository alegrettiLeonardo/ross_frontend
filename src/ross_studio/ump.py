from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import numpy as np

from .domain import EngineeringError, UmpSpec

if TYPE_CHECKING:
    from .domain import RotorProject
    from .ross_backend import RossBuildResult


@dataclass(slots=True, frozen=True)
class UMPSpanAssembly:
    """Traceable assembly record for one distributed UMP span."""

    name: str
    start_mm: float
    end_mm: float
    stiffness_per_length_n_m2: float
    shaft_element_indices: tuple[int, ...]
    integrated_stiffness_n_m: float


@dataclass(slots=True)
class UMPAssembly:
    """Global linearized UMP stiffness contribution.

    ``matrix_n_m`` is stored as a positive destabilizing stiffness magnitude.
    The physical rotor equation is assembled as::

        M qdd + (C + Omega G) qd + (K - K_UMP) q = F

    so the matrix is subtracted only by ``UMPRotorMixin.K``.
    """

    matrix_n_m: np.ndarray
    spans: tuple[UMPSpanAssembly, ...]

    @property
    def active(self) -> bool:
        return bool(self.spans) and bool(np.any(np.abs(self.matrix_n_m) > 0.0))

    @property
    def max_abs_entry_n_m(self) -> float:
        if self.matrix_n_m.size == 0:
            return 0.0
        return float(np.max(np.abs(self.matrix_n_m)))

    @property
    def total_integrated_stiffness_n_m(self) -> float:
        return float(sum(span.integrated_stiffness_n_m for span in self.spans))


def consistent_lateral_ump_matrix(length_m: float, stiffness_per_length_n_m2: float) -> np.ndarray:
    """Return the 12x12 consistent beam matrix for distributed linearized UMP.

    The UMP law is ``f_u = k'_u * u`` per unit axial length, where ``k'_u`` has
    units N/m². Integrating the cubic Euler-Bernoulli/Hermite interpolation gives
    the same translational shape-function matrix as the consistent beam mass
    matrix, with ``rho*A`` replaced by ``k'_u`` and *without* rotary inertia.

    The x/beta and y/alpha sign patterns follow the ROSS 6-DOF shaft convention.
    This is also the intended translational part documented by RotorDin's UMP
    assembly; the legacy source comment explicitly says the inertia term is zero.
    """

    L = float(length_m)
    kq = float(stiffness_per_length_n_m2)
    if not np.isfinite(L) or L <= 0.0:
        raise EngineeringError(f"UMP element length must be positive and finite; received {length_m!r}.")
    if not np.isfinite(kq) or kq < 0.0:
        raise EngineeringError(
            f"UMP stiffness per unit length must be finite and non-negative; received {stiffness_per_length_n_m2!r}."
        )

    h = np.array(
        [
            [156.0, 22.0 * L, 54.0, -13.0 * L],
            [22.0 * L, 4.0 * L**2, 13.0 * L, -3.0 * L**2],
            [54.0, 13.0 * L, 156.0, -22.0 * L],
            [-13.0 * L, -3.0 * L**2, -22.0 * L, 4.0 * L**2],
        ],
        dtype=float,
    ) * (kq * L / 420.0)

    local = np.zeros((12, 12), dtype=float)

    # ROSS local dofs per node:
    # [x, y, z, alpha, beta, theta].
    # x bending uses beta directly; y bending uses the opposite alpha sign.
    x_dofs = np.array([0, 4, 6, 10], dtype=int)
    y_dofs = np.array([1, 3, 7, 9], dtype=int)
    local[np.ix_(x_dofs, x_dofs)] = h

    y_sign = np.diag([1.0, -1.0, 1.0, -1.0])
    local[np.ix_(y_dofs, y_dofs)] = y_sign @ h @ y_sign
    return local


def assemble_ump(project: "RotorProject", build: "RossBuildResult") -> UMPAssembly:
    """Assemble all UMP spans into the ROSS global lateral stiffness basis."""

    ndof_total = int(build.rotor.ndof)
    number_dof = int(build.rotor.number_dof)
    if number_dof != 6:
        raise EngineeringError(
            f"Qualified UMP assembly requires the ROSS 6-DOF shaft formulation; received {number_dof} DOF/node."
        )

    matrix = np.zeros((ndof_total, ndof_total), dtype=float)
    records: list[UMPSpanAssembly] = []

    for spec in project.umps:
        spec.validate()
        if spec.stiffness_per_length_n_m2 <= 0.0:
            continue

        matched: list[int] = []
        for element in build.shaft_plan:
            # NodeInsertionService must place UMP start/end exactly, therefore an
            # element is either completely inside or completely outside the span.
            overlap = min(element.x1_mm, spec.end_mm) - max(element.x0_mm, spec.start_mm)
            if overlap <= 1e-9:
                continue
            if element.x0_mm < spec.start_mm - 1e-7 or element.x1_mm > spec.end_mm + 1e-7:
                raise EngineeringError(
                    f"UMP span {spec.name!r} partially intersects shaft element {element.n} "
                    f"[{element.x0_mm:g}, {element.x1_mm:g}] mm. Exact start/end node insertion is required."
                )

            local = consistent_lateral_ump_matrix(
                element.length_mm / 1000.0,
                spec.stiffness_per_length_n_m2,
            )
            n0 = int(element.n)
            n1 = n0 + 1
            dofs = np.array(
                [
                    *(n0 * number_dof + i for i in range(number_dof)),
                    *(n1 * number_dof + i for i in range(number_dof)),
                ],
                dtype=int,
            )
            matrix[np.ix_(dofs, dofs)] += local
            matched.append(element.n)

        if not matched:
            raise EngineeringError(
                f"UMP span {spec.name!r} [{spec.start_mm:g}, {spec.end_mm:g}] mm did not map to any shaft element."
            )

        records.append(
            UMPSpanAssembly(
                name=spec.name,
                start_mm=float(spec.start_mm),
                end_mm=float(spec.end_mm),
                stiffness_per_length_n_m2=float(spec.stiffness_per_length_n_m2),
                shaft_element_indices=tuple(matched),
                integrated_stiffness_n_m=float(spec.stiffness_per_length_n_m2 * spec.length_mm / 1000.0),
            )
        )

    if not np.allclose(matrix, matrix.T, rtol=0.0, atol=1e-10):
        raise EngineeringError("Assembled UMP stiffness matrix is not symmetric for the qualified isotropic model.")
    return UMPAssembly(matrix_n_m=matrix, spans=tuple(records))


class UMPRotorMixin:
    """ROSS Rotor mixin that activates linearized electromagnetic negative stiffness."""

    def set_ump_assembly(self, assembly: UMPAssembly) -> None:
        matrix = np.asarray(assembly.matrix_n_m, dtype=float)
        if matrix.shape != (self.ndof, self.ndof):
            raise EngineeringError(
                f"UMP matrix shape {matrix.shape} does not match rotor ndof={self.ndof}."
            )
        self.ump_assembly = assembly
        self.ump_stiffness_matrix = matrix.copy()

    def K(self, frequency):
        base = super().K(frequency)
        ku = getattr(self, "ump_stiffness_matrix", None)
        if ku is None:
            return base
        return base - ku


def ump_rotor_class(base_class: type[Any]) -> type[Any]:
    """Compose UMP behavior with either native ROSS or RotorDin-positive Rotor."""

    class UMPEnabledRotor(UMPRotorMixin, base_class):
        pass

    UMPEnabledRotor.__name__ = f"UMPEnabled{base_class.__name__}"
    UMPEnabledRotor.__qualname__ = UMPEnabledRotor.__name__
    UMPEnabledRotor.__module__ = __name__
    return UMPEnabledRotor


__all__ = [
    "UMPAssembly",
    "UMPSpanAssembly",
    "UMPRotorMixin",
    "assemble_ump",
    "consistent_lateral_ump_matrix",
    "ump_rotor_class",
]
