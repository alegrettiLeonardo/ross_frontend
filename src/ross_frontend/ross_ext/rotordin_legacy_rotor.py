from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=None)
def make_rotordin_legacy_rotor_class(base_cls):
    """Create a ROSS Rotor with RotorDin's exact complex unbalance convention.

    ``resp_fv.f`` constructs a synchronous unbalance phasor as::

        pmn = mu * omega**2 * exp(+i*phase)
        Fx  = -i * pmn
        Fz  =      pmn

    The legacy compatibility model maps RotorDin lateral ``z`` directly to ROSS
    lateral ``y`` (the same transform used for the exact shaft M/K/G blocks), so
    the ROSS-coordinate force vector must be ``[-i, +1]`` times the source
    phasor.  Native ROSS uses ``[+1, -i]`` and therefore represents the opposite
    complex whirl convention; a single global phase shift cannot make the two
    vectors equivalent.

    This override is intentionally restricted to deterministic RotorDin
    regression/migration.  New physical ROSS projects keep the upstream native
    unbalance definition and SI units.
    """

    class RotorDinLegacyRotor(base_cls):
        def _unbalance_force(self, node, magnitude, phase, omega):
            import numpy as np

            w = np.atleast_1d(np.asarray(omega, dtype=float))
            force = np.zeros((self.ndof, len(w)), dtype=np.complex128)
            phasor = float(magnitude) * np.exp(1j * float(phase))

            local = np.zeros(self.number_dof, dtype=np.complex128)
            local[0] = -1j * phasor
            local[1] = phasor

            start = self.number_dof * int(node)
            stop = start + self.number_dof
            for idx, speed in enumerate(w):
                force[start:stop, idx] += speed**2 * local
            return force

    RotorDinLegacyRotor.__name__ = "RotorDinLegacyRotor"
    RotorDinLegacyRotor.__qualname__ = "RotorDinLegacyRotor"
    RotorDinLegacyRotor.__module__ = __name__
    return RotorDinLegacyRotor


__all__ = ["make_rotordin_legacy_rotor_class"]
