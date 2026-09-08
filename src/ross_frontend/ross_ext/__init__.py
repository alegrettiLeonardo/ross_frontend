"""Scientific extensions that preserve RotorDin-specific physics on top of ROSS."""

from .ump import (
    LEGACY_KGF_MM2_TO_N_M2,
    UMPElementContribution,
    consistent_ump_matrix,
    legacy_ump_to_si,
    make_ump_rhs_callback,
    make_ump_shaft_element_class,
    ump_force_from_displacement,
)

__all__ = [
    "LEGACY_KGF_MM2_TO_N_M2",
    "UMPElementContribution",
    "consistent_ump_matrix",
    "legacy_ump_to_si",
    "make_ump_rhs_callback",
    "make_ump_shaft_element_class",
    "ump_force_from_displacement",
]
