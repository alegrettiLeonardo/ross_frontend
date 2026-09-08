"""Scientific extensions that preserve RotorDin-specific physics on top of ROSS."""

from .ump import (
    LEGACY_KGF_MM2_TO_N_M2,
    ROTORDIN_LEGACY_MAX_REGIONS,
    ROTORDIN_LEGACY_THRESHOLD_N_M2,
    UMPAssembly,
    UMPElementContribution,
    UMPElementSpan,
    assemble_ump_global,
    consistent_ump_matrix,
    legacy_ump_to_si,
    rotordin_legacy_ump_matrix,
)
from .ump_rotor import make_ump_rotor_class

__all__ = [
    "LEGACY_KGF_MM2_TO_N_M2",
    "ROTORDIN_LEGACY_MAX_REGIONS",
    "ROTORDIN_LEGACY_THRESHOLD_N_M2",
    "UMPAssembly",
    "UMPElementContribution",
    "UMPElementSpan",
    "assemble_ump_global",
    "consistent_ump_matrix",
    "legacy_ump_to_si",
    "make_ump_rotor_class",
    "rotordin_legacy_ump_matrix",
]
