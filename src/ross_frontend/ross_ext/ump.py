from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from typing import Iterable

LEGACY_KGF_MM2_TO_N_M2 = 9.80665e6


@dataclass(frozen=True, slots=True)
class UMPElementContribution:
    """One active beam contribution used to assemble UMP force in global DOFs."""

    node: int
    length_m: float
    stiffness_per_length_n_m2: float


def legacy_ump_to_si(value: float) -> float:
    """Convert a legacy UMP value interpreted as kgf/mm² to N/m²."""
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError("Legacy UMP value must be a finite non-negative number.")
    return value * LEGACY_KGF_MM2_TO_N_M2


def consistent_ump_matrix(stiffness_per_length_n_m2: float, length_m: float) -> list[list[float]]:
    r"""Return the 12x12 consistent linearized UMP matrix for a ROSS shaft element.

    For small radial perturbations, ``f_UMP(z)=k'_UMP u(z)``.  Therefore the
    structural equation can be written either with ``K-K_UMP`` on the left or
    with ``F_UMP=K_UMP q`` on the right.  Only lateral bending DOFs are affected.
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

    x_dofs = (0, 4, 6, 10)
    for i, gi in enumerate(x_dofs):
        for j, gj in enumerate(x_dofs):
            matrix[gi][gj] = scale * plane[i][j]

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


def ump_force_from_displacement(stiffness_per_length_n_m2: float, length_m: float, displacement: Iterable[float]) -> list[float]:
    """Return the explicit local linearized UMP force ``F=K_UMP q``."""
    return _matvec(consistent_ump_matrix(stiffness_per_length_n_m2, length_m), displacement)


def make_ump_rhs_callback(ndof: int, contributions: Iterable[UMPElementContribution], *, number_dof: int = 6):
    """Build a ROSS ``add_to_RHS`` callback for state-dependent UMP force.

    Use this only with a rotor built with ``ump_realization='rhs_force'``.  The
    callback receives the current ROSS displacement vector and assembles all
    local ``K_UMP q`` contributions into global DOFs.
    """
    items = tuple(contributions)
    if number_dof != 6:
        raise ValueError("UMP RHS assembly is currently verified for the ROSS 6-DOF rotor formulation only.")

    def rhs(step, *, disp_resp=None, **_state):
        import numpy as np

        force = np.zeros(int(ndof), dtype=float)
        if disp_resp is None:
            return force
        q = np.asarray(disp_resp, dtype=float)
        if q.shape != (int(ndof),):
            raise ValueError(f"UMP RHS expected displacement vector with {ndof} DOFs, received {q.shape}.")
        for item in items:
            left = number_dof * item.node
            right = number_dof * (item.node + 1)
            dofs = [*range(left, left + number_dof), *range(right, right + number_dof)]
            local_q = q[dofs]
            local_f = ump_force_from_displacement(
                item.stiffness_per_length_n_m2,
                item.length_m,
                local_q,
            )
            force[dofs] += np.asarray(local_f, dtype=float)
        return force

    return rhs


@lru_cache(maxsize=None)
def make_ump_shaft_element_class(base_cls):
    """Create a ShaftElement subclass that subtracts linearized UMP stiffness."""
    class UMPLinearizedShaftElement(base_cls):
        def __init__(self, *args, ump_stiffness_per_length_n_m2: float = 0.0, **kwargs):
            self.ump_stiffness_per_length_n_m2 = float(ump_stiffness_per_length_n_m2)
            super().__init__(*args, **kwargs)

        def K(self):
            import numpy as np
            base = super().K()
            if self.ump_stiffness_per_length_n_m2 <= 0.0:
                return base
            return base - np.asarray(
                consistent_ump_matrix(self.ump_stiffness_per_length_n_m2, self.L),
                dtype=float,
            )

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
    "UMPElementContribution",
    "consistent_ump_matrix",
    "legacy_ump_to_si",
    "make_ump_rhs_callback",
    "make_ump_shaft_element_class",
    "ump_force_from_displacement",
]
