from __future__ import annotations

from functools import lru_cache

from .ump import assemble_ump_global


@lru_cache(maxsize=None)
def make_ump_rotor_class(base_cls):
    """Create a ROSS Rotor subclass whose only physics change is ``K-K_UMP``.

    The factory avoids importing ROSS in lightweight core tests while producing a
    true subclass of the pinned ``ross.Rotor`` at runtime.
    """

    class UmpRotor(base_cls):
        def __init__(self, *args, ump_regions=(), ump_element_spans=(), **kwargs):
            super().__init__(*args, **kwargs)
            self.ump_regions = tuple(ump_regions)
            self.ump_element_spans = tuple(ump_element_spans)
            assembly = assemble_ump_global(self, self.ump_regions, self.ump_element_spans)
            self.K_ump = assembly.matrix
            self.ump_contributions = assembly.contributions
            self.ump_audit = assembly.audit_dict()

        def K_without_ump(self, frequency):
            """Return the native ROSS stiffness, including frequency-dependent bearings."""

            return super().K(frequency)

        def K(self, frequency):
            """Return the effective dynamic stiffness ``K_ROSS - K_UMP``."""

            return self.K_without_ump(frequency) - self.K_ump

    UmpRotor.__name__ = "UmpRotor"
    UmpRotor.__qualname__ = "UmpRotor"
    UmpRotor.__module__ = __name__
    return UmpRotor


__all__ = ["make_ump_rotor_class"]
