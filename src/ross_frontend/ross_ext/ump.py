from __future__ import annotations

from functools import lru_cache
from math import isfinite
from typing import Iterable

# Legacy RotorDin projects expose the UMP engineering value in the old UI as
# kg-based input, while the beam formulation consumes a distributed radial
# stiffness with SI dimensions N/m².  The original INI format does not carry a
# unit token, so the migration keeps the source value and records this explicit
# kgf/mm² -> N/m² interpretation in project metadata for auditability.
LEGACY_KGF_MM2_TO_N_M2 = 9.80665e6


def legacy_ump_to_si(value: float) -> float:
    """Convert the legacy RotorDin UMP engineering value to N/m².

    The conversion assumption is intentionally centralized instead of being
    hidden in the importer.  A value of 1 kgf/mm² equals 9.80665e6 N/m².
    """

    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError("Legacy UMP value must be a finite non-negative number.")
    return value * LEGACY_KGF_MM2_TO_N_M2


def consistent_ump_matrix(stiffness_per_length_n_m2: float, length_m: float) -> list[list[float]]:
    r"""Return the 12x12 consistent linearized UMP matrix for a ROSS shaft element.

    For small radial perturbations, UMP is modeled as a destabilizing distributed
    force density

        f_UMP(z) = k'_UMP u(z)

    where ``k'_UMP`` has units N/m².  The equivalent nodal force is

        F_UMP,e = K_UMP,e q_e

    and the structural equation therefore contains ``K - K_UMP``.

    The interpolation is the same consistent Euler-Bernoulli transverse shape
    matrix used by the legacy RotorDin ``coemas`` UMP formulation (the
    translational part only).  The matrix is embedded in the ROSS local DOF order

        [x0, y0, z0, alpha0, beta0, theta0,
         x1, y1, z1, alpha1, beta1, theta1]

    with the required ROSS sign convention for ``alpha`` and ``beta``.
    """

    k = float(stiffness_per_length_n_m2)
    length = float(length_m)
    if not isfinite(k) or k < 0:
        raise ValueError("UMP stiffness per length must be finite and non-negative.")
    if not isfinite(length) or length <= 0:
        raise ValueError("UMP element length must be finite and positive.")

    l2 = length * length
    plane = [
        [156.0, 22.0 * length, 54.0, -13.0 * length],
        [22.0 * length, 4.0 * l2, 13.0 * length, -3.0 * l2],
        [54.0, 13.0 * length, 156.0, -22.0 * length],
        [-13.0 * length, -3.0 * l2, -22.0 * length, 4.0 * l2],
    ]
    scale = k * length / 420.0

    matrix = [[0.0 for _ in range(12)] for _ in range(12)]

    # x/beta bending plane.  This is the direct sign convention used by ROSS.
    x_dofs = (0, 4, 6, 10)
    for i, gi in enumerate(x_dofs):
        for j, gj in enumerate(x_dofs):
            matrix[gi][gj] = scale * plane[i][j]

    # y/alpha bending plane.  ROSS uses the opposite rotational sign for alpha,
    # so S * plane * S with S = diag(1,-1,1,-1) maps the same physical energy.
    y_dofs = (1, 3, 7, 9)
    signs = (1.0, -1.0, 1.0, -1.0)
    for i, gi in enumerate(y_dofs):
        for j, gj in enumerate(y_dofs):
            matrix[gi][gj] = scale * signs[i] * plane[i][j] * signs[j]

    return matrix


def _matvec(matrix: Iterable[Iterable[float]], vector: Iterable[float]) -> list[float]:
    values = [float(v) for v in vector]
    rows = [list(row) for row in matrix]
    if any(len(row) != len(values) for row in rows):
        raise ValueError("UMP matrix/vector dimensions are inconsistent.")
    return [sum(float(a) * b for a, b in zip(row, values)) for row in rows]


def ump_force_from_displacement(
    stiffness_per_length_n_m2: float,
    length_m: float,
    displacement: Iterable[float],
) -> list[float]:
    """Return the explicit linearized UMP force ``F = K_UMP q``.

    This is the force-side form used for transient/state-dependent integration.
    Do not add this force to a model whose shaft stiffness already contains the
    same UMP reduction, otherwise the UMP contribution would be counted twice.
    """

    return _matvec(consistent_ump_matrix(stiffness_per_length_n_m2, length_m), displacement)


@lru_cache(maxsize=None)
def make_ump_shaft_element_class(base_cls):
    """Create a ShaftElement subclass that subtracts linearized UMP stiffness.

    The factory accepts the ROSS class rather than importing ROSS at module import
    time.  This keeps the domain/core tests independent from the heavy solver
    dependency and also allows the existing FakeRoss test double to exercise the
    builder path.
    """

    class UMPLinearizedShaftElement(base_cls):
        def __init__(self, *args, ump_stiffness_per_length_n_m2: float = 0.0, **kwargs):
            self.ump_stiffness_per_length_n_m2 = float(ump_stiffness_per_length_n_m2)
            super().__init__(*args, **kwargs)

        def K(self):
            import numpy as np

            base = super().K()
            if self.ump_stiffness_per_length_n_m2 <= 0.0:
                return base
            k_ump = np.asarray(
                consistent_ump_matrix(self.ump_stiffness_per_length_n_m2, self.L),
                dtype=float,
            )
            return base - k_ump

        def ump_K(self):
            import numpy as np

            return np.asarray(
                consistent_ump_matrix(self.ump_stiffness_per_length_n_m2, self.L),
                dtype=float,
            )

        def ump_force(self, displacement):
            import numpy as np

            q = np.asarray(displacement, dtype=float)
            if q.shape != (12,):
                raise ValueError("A shaft-element UMP displacement vector must contain 12 local DOFs.")
            return self.ump_K() @ q

    UMPLinearizedShaftElement.__name__ = f"UMP{base_cls.__name__}"
    UMPLinearizedShaftElement.__qualname__ = UMPLinearizedShaftElement.__name__
    UMPLinearizedShaftElement.__module__ = __name__
    return UMPLinearizedShaftElement


__all__ = [
    "LEGACY_KGF_MM2_TO_N_M2",
    "consistent_ump_matrix",
    "legacy_ump_to_si",
    "make_ump_shaft_element_class",
    "ump_force_from_displacement",
]
