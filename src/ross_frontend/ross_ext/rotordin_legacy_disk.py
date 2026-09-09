from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=None)
def make_rotordin_legacy_disk_class(base_cls):
    """Create a ROSS disk element with RotorDin's gyroscopic sign convention.

    RotorDin assembles the rigid-disk rotational gyroscopic block as::

        [[0, -Ip],
         [+Ip, 0]]

    while ROSS 2.3.0 ``DiskElement.G()`` uses the opposite sign. Both solvers
    place ``+ i*omega*Omega*G`` in the dynamic stiffness, so the matrix itself
    must be sign-compatible for deterministic RotorDin regression.

    Mass/inertia terms are otherwise equivalent and remain native ROSS.
    """

    class RotorDinLegacyDiskElement(base_cls):
        def G(self):
            return -super().G()

    RotorDinLegacyDiskElement.__name__ = "RotorDinLegacyDiskElement"
    RotorDinLegacyDiskElement.__qualname__ = "RotorDinLegacyDiskElement"
    RotorDinLegacyDiskElement.__module__ = __name__
    return RotorDinLegacyDiskElement


__all__ = ["make_rotordin_legacy_disk_class"]
