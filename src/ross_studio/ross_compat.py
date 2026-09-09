from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import numpy as np
from numba import njit


_NUM_ORBIT_POINTS = 360
_CIRCLE = np.exp(1j * np.linspace(0.0, 2.0 * np.pi, _NUM_ORBIT_POINTS, endpoint=False))


@dataclass(slots=True, frozen=True)
class RossCompatibilityNote:
    code: str
    message: str


@njit
def _init_orbit_symmetric(ru_e: complex, rv_e: complex):
    """ROSS 2.3 orbit initializer using the symmetric real 2x2 form.

    This is a compatibility implementation of the orbit geometry only. It does not
    alter the rotor matrices, eigensolver, eigenvalues or eigenvectors. The 2x2
    matrix H=T*T^T is real symmetric, therefore ``eigh`` is the mathematically
    appropriate solver and returns ordered real eigenvalues. This avoids the ROSS
    2.3 / NumPy 2.5 / Numba failure caused by ``argmax`` on a complex eigenvalue
    array in the published 2.3 post-processing implementation.
    """
    x_circle = np.real(ru_e * _CIRCLE)
    y_circle = np.real(rv_e * _CIRCLE)
    angle = np.arctan2(y_circle, x_circle)
    angle[angle < 0.0] = angle[angle < 0.0] + 2.0 * np.pi

    ru = np.absolute(ru_e)
    rv = np.absolute(rv_e)
    nu = np.angle(ru_e)
    nv = np.angle(rv_e)
    t = np.array(
        [
            [ru * np.cos(nu), -ru * np.sin(nu)],
            [rv * np.cos(nv), -rv * np.sin(nv)],
        ]
    )
    h = t @ t.T
    eigenvalues, eigenvectors = np.linalg.eigh(h)

    minor = np.sqrt(max(eigenvalues[0], 0.0))
    major = np.sqrt(max(eigenvalues[-1], 0.0))
    diff = nv - nu
    if diff < -np.pi:
        diff += 2.0 * np.pi
    elif diff > np.pi:
        diff -= 2.0 * np.pi

    if diff == 0.0 or diff == np.pi or major == 0.0:
        kappa = 0.0
    elif 0.0 < diff < np.pi:
        kappa = -minor / major
    else:
        kappa = minor / major

    major_index = int(np.argmax(eigenvalues))
    vector = eigenvectors[:, major_index]
    vector = vector / np.linalg.norm(vector)
    if vector[1] < 0.0 or (vector[1] == 0.0 and vector[0] < 0.0):
        vector = -vector

    major_x = major * vector[0]
    major_y = major * vector[1]
    major_angle = np.arctan2(major_y, major_x)
    if major_angle < 0.0:
        major_angle += 2.0 * np.pi
    minor_angle = major_angle + np.pi / 2.0

    return (
        x_circle,
        y_circle,
        angle,
        major_x,
        major_y,
        major_angle,
        minor_angle,
        major_index,
        nu,
        nv,
        minor,
        major,
        kappa,
    )


def install_ross_compatibility(ross_module: Any) -> tuple[RossCompatibilityNote, ...]:
    """Install narrowly-scoped compatibility fixes required by the pinned ROSS.

    ROSS Studio 0.8 pins ``ross-rotordynamics==2.3.0``. That release's modal
    post-processing can fail with current NumPy/Numba when an orbit's symmetric
    eigenproblem is returned with complex dtype. Upstream ROSS subsequently changed
    this calculation to a symmetric ``eigh`` formulation. We apply the equivalent
    geometry-only fix at runtime for 2.3.0 so public ``run_modal``/``run_campbell``
    remain usable while preserving the exact ROSS 2.3 numerical rotor solution.
    """
    version = str(getattr(ross_module, "__version__", ""))
    if version != "2.3.0":
        return ()

    results = import_module("ross.results")
    if getattr(results, "_ross_studio_orbit_compat_installed", False):
        return (
            RossCompatibilityNote(
                "ROSS_230_ORBIT_COMPAT",
                "ROSS 2.3 orbit post-processing compatibility shim already active; rotor matrices and eigensolver are unchanged.",
            ),
        )

    results._init_orbit = _init_orbit_symmetric
    results._ross_studio_orbit_compat_installed = True
    return (
        RossCompatibilityNote(
            "ROSS_230_ORBIT_COMPAT",
            "Applied the symmetric-eigh orbit post-processing fix required by ROSS 2.3 with current NumPy/Numba. Only orbit geometry initialization is replaced; M/C/G/K assembly and the ROSS eigensolver are unchanged.",
        ),
    )


__all__ = [
    "RossCompatibilityNote",
    "install_ross_compatibility",
]
