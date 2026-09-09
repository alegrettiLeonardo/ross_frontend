from __future__ import annotations

from functools import lru_cache


# RotorDin lateral element order:
#   [x0, z0, rot_x0, rot_z0, x1, z1, rot_x1, rot_z1]
# ROSS lateral subset:
#   [x0, y0, alpha0, beta0, x1, y1, alpha1, beta1]
# The historical rotation convention is rot_x=-alpha and rot_z=-beta.
_ROSS_LATERAL_DOF = (0, 1, 3, 4, 6, 7, 9, 10)
_ROTORDIN_TO_ROSS_SIGN = (1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0)


def _transform_rotordin_lateral(matrix):
    import numpy as np

    source = np.asarray(matrix, dtype=float)
    signs = np.asarray(_ROTORDIN_TO_ROSS_SIGN, dtype=float)
    return signs[:, None] * source * signs[None, :]


def _replace_lateral_block(base, lateral):
    import numpy as np

    out = np.array(base, dtype=float, copy=True)
    idx = np.asarray(_ROSS_LATERAL_DOF, dtype=int)
    out[np.ix_(idx, idx)] = _transform_rotordin_lateral(lateral)
    return out


def rotordin_lateral_stiffness(length, young, shear, area, inertia):
    """RotorDin ``coerig`` 8x8 bending stiffness matrix.

    RotorDin uses ``a=12*E*I/(G*A*L**2)`` directly, without the Cowper or
    Hutchinson shear coefficient used by the standard ROSS Timoshenko element.
    """
    import numpy as np

    L = float(length)
    E = float(young)
    G = float(shear)
    A = float(area)
    I = float(inertia)
    a = 12.0 * E * I / (G * A * L**2)
    L2 = L * L
    m = np.array(
        [
            [12, 0, 0, -6 * L, -12, 0, 0, -6 * L],
            [0, 12, 6 * L, 0, 0, -12, 6 * L, 0],
            [0, 6 * L, (4 + a) * L2, 0, 0, -6 * L, (2 - a) * L2, 0],
            [-6 * L, 0, 0, (4 + a) * L2, 6 * L, 0, 0, (2 - a) * L2],
            [-12, 0, 0, 6 * L, 12, 0, 0, 6 * L],
            [0, -12, -6 * L, 0, 0, 12, -6 * L, 0],
            [0, 6 * L, (2 - a) * L2, 0, 0, -6 * L, (4 + a) * L2, 0],
            [-6 * L, 0, 0, (2 - a) * L2, 6 * L, 0, 0, (4 + a) * L2],
        ],
        dtype=float,
    )
    return m * (E * I / ((1.0 + a) * L**3)), a


def rotordin_lateral_mass(length, density, area, inertia):
    """RotorDin ``coemas`` 8x8 consistent mass matrix."""
    import numpy as np

    L = float(length)
    rho = float(density)
    A = float(area)
    I = float(inertia)
    L2 = L * L

    translational = np.array(
        [
            [156, 0, 0, -22 * L, 54, 0, 0, 13 * L],
            [0, 156, 22 * L, 0, 0, 54, -13 * L, 0],
            [0, 22 * L, 4 * L2, 0, 0, 13 * L, -3 * L2, 0],
            [-22 * L, 0, 0, 4 * L2, -13 * L, 0, 0, -3 * L2],
            [54, 0, 0, -13 * L, 156, 0, 0, 22 * L],
            [0, 54, 13 * L, 0, 0, 156, -22 * L, 0],
            [0, -13 * L, -3 * L2, 0, 0, -22 * L, 4 * L2, 0],
            [13 * L, 0, 0, -3 * L2, 22 * L, 0, 0, 4 * L2],
        ],
        dtype=float,
    ) * (rho * A * L / 420.0)

    rotary = np.array(
        [
            [36, 0, 0, -3 * L, -36, 0, 0, -3 * L],
            [0, 36, 3 * L, 0, 0, -36, 3 * L, 0],
            [0, 3 * L, 4 * L2, 0, 0, -3 * L, -L2, 0],
            [-3 * L, 0, 0, 4 * L2, 3 * L, 0, 0, -L2],
            [-36, 0, 0, 3 * L, 36, 0, 0, 3 * L],
            [0, -36, -3 * L, 0, 0, 36, -3 * L, 0],
            [0, 3 * L, -L2, 0, 0, -3 * L, 4 * L2, 0],
            [-3 * L, 0, 0, -L2, 3 * L, 0, 0, 4 * L2],
        ],
        dtype=float,
    ) * (rho * I / (30.0 * L))
    return translational + rotary


def rotordin_lateral_gyroscopic(length, density, inertia, factor=1.0):
    """RotorDin ``coegir`` 8x8 gyroscopic matrix."""
    import numpy as np

    L = float(length)
    rho = float(density)
    I = float(inertia)
    gf = float(factor)
    L2 = L * L
    m = np.array(
        [
            [0, -36, -3 * L, 0, 0, 36, -3 * L, 0],
            [36, 0, 0, -3 * L, -36, 0, 0, -3 * L],
            [3 * L, 0, 0, -4 * L2, -3 * L, 0, 0, L2],
            [0, 3 * L, 4 * L2, 0, 0, -3 * L, -L2, 0],
            [0, 36, 3 * L, 0, 0, -36, 3 * L, 0],
            [-36, 0, 0, 3 * L, 36, 0, 0, 3 * L],
            [3 * L, 0, 0, L2, -3 * L, 0, 0, -4 * L2],
            [0, 3 * L, -L2, 0, 0, -3 * L, 4 * L2, 0],
        ],
        dtype=float,
    )
    return m * (gf * rho * I / (15.0 * L))


@lru_cache(maxsize=None)
def make_rotordin_legacy_shaft_class(base_cls):
    """Create a ROSS shaft element with exact RotorDin lateral M/K/G blocks.

    This class exists only for deterministic migration/regression of RotorDin
    projects. New projects continue to use the standard ROSS ``ShaftElement``.
    The native ROSS axial/torsional blocks are retained as a decoupled numerical
    completion; the lateral matrices are replaced by ``coemas/coerig/coegir``.
    """

    class RotorDinLegacyShaftElement(base_cls):
        def __init__(self, *args, gyroscopic_factor=1.0, **kwargs):
            requested_shear = bool(kwargs.get("shear_effects", True))
            # phi=0 makes the native completion independent of ROSS Timoshenko
            # shear terms. The exact RotorDin lateral stiffness is inserted below.
            kwargs["shear_effects"] = False
            super().__init__(*args, **kwargs)
            self.rotordin_requested_shear_effects = requested_shear
            self.rotordin_gyroscopic_factor = float(gyroscopic_factor)

            tol = 1e-12
            if abs(float(self.odl) - float(self.odr)) > tol or abs(float(self.idl) - float(self.idr)) > tol:
                raise ValueError(
                    "RotorDin legacy shaft compatibility is verified only for cylindrical elements; tapered element found."
                )
            _k, shear_parameter = rotordin_lateral_stiffness(
                self.L,
                self.material.E,
                self.material.G_s,
                self.A,
                self.Ie,
            )
            self.rotordin_shear_parameter = float(shear_parameter)

        def M(self):
            lateral = rotordin_lateral_mass(
                self.L,
                self.material.rho,
                self.A,
                self.Ie,
            )
            return _replace_lateral_block(super().M(), lateral)

        def K(self):
            lateral, _a = rotordin_lateral_stiffness(
                self.L,
                self.material.E,
                self.material.G_s,
                self.A,
                self.Ie,
            )
            return _replace_lateral_block(super().K(), lateral)

        def G(self):
            if not self.gyroscopic:
                return super().G()
            lateral = rotordin_lateral_gyroscopic(
                self.L,
                self.material.rho,
                self.Ie,
                self.rotordin_gyroscopic_factor,
            )
            return _replace_lateral_block(super().G(), lateral)

    RotorDinLegacyShaftElement.__name__ = "RotorDinLegacyShaftElement"
    RotorDinLegacyShaftElement.__qualname__ = "RotorDinLegacyShaftElement"
    RotorDinLegacyShaftElement.__module__ = __name__
    return RotorDinLegacyShaftElement


__all__ = [
    "make_rotordin_legacy_shaft_class",
    "rotordin_lateral_stiffness",
    "rotordin_lateral_mass",
    "rotordin_lateral_gyroscopic",
]
