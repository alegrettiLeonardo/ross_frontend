from __future__ import annotations

from typing import Any


class RotorDinConventionMixin:
    """Map positive RotorDin rotation to the equivalent ROSS dynamic convention.

    Source-level and OP-W60 A/B evidence show that the two solvers use opposite
    signs for the gyroscopic matrix at the same positive RPM.  The synchronous
    rotating-force handedness must therefore be reversed together with G.  Bearing
    K/C coefficients are deliberately left untouched: Kxz/Kzx and Cxz/Czx map
    directly to ROSS Kxy/Kyx and Cxy/Cyx when x is horizontal and y/z is vertical.

    This mixin changes no mass, stiffness or damping value.  It changes only the
    positive-rotation convention used by rotating dynamic analyses.
    """

    lateral_convention = "ROTORDIN_POSITIVE"

    def G(self):
        return -super().G()

    def _unbalance_force(self, node, magnitude, phase, omega):
        force = super()._unbalance_force(node, magnitude, phase, omega)
        vertical_dof = self.number_dof * int(node) + 1
        # Native ROSS uses [1, -j].  RotorDin-positive rotation in the ROSS x/y
        # basis requires the opposite circular-force handedness [1, +j].
        force[vertical_dof, :] *= -1.0
        return force


def rotordin_rotor_class(ross_module: Any):
    """Return a ROSS Rotor subclass carrying only the RotorDin convention map."""

    base = ross_module.Rotor

    class RotorDinConventionRotor(RotorDinConventionMixin, base):
        pass

    RotorDinConventionRotor.__name__ = "RotorDinConventionRotor"
    RotorDinConventionRotor.__qualname__ = "RotorDinConventionRotor"
    RotorDinConventionRotor.__module__ = __name__
    return RotorDinConventionRotor


def rotor_class_for_convention(ross_module: Any, convention: str):
    value = str(convention).strip().upper()
    if value == "ROSS_NATIVE":
        return ross_module.Rotor
    if value == "ROTORDIN_POSITIVE":
        return rotordin_rotor_class(ross_module)
    raise ValueError(f"Unsupported lateral convention {convention!r}.")


__all__ = [
    "RotorDinConventionMixin",
    "rotor_class_for_convention",
    "rotordin_rotor_class",
]
