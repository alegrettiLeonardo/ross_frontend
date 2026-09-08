"""ROSS Frontend integration core."""

from .vendor_runtime import activate_vendored_ross

# Prefer the solver source pinned in vendor/ross before any backend imports.
activate_vendored_ross()

__version__ = "0.5.0"

from .domain import (
    AnalysisRequest,
    BallBearingSpec,
    CoefficientBearingSpec,
    CylindricalBearingSpec,
    DiskSpec,
    MaterialSpec,
    PlainJournalBearingSpec,
    PointMassSpec,
    ProbeSpec,
    RollerBearingSpec,
    RotorProject,
    ShaftSectionSpec,
    SupportSpec,
    TiltingPadBearingSpec,
    UMPRegionSpec,
    UmpFormulation,
    UnbalanceSpec,
)

__all__ = [
    "AnalysisRequest",
    "BallBearingSpec",
    "CoefficientBearingSpec",
    "CylindricalBearingSpec",
    "DiskSpec",
    "MaterialSpec",
    "PlainJournalBearingSpec",
    "PointMassSpec",
    "ProbeSpec",
    "RollerBearingSpec",
    "RotorProject",
    "ShaftSectionSpec",
    "SupportSpec",
    "TiltingPadBearingSpec",
    "UMPRegionSpec",
    "UmpFormulation",
    "UnbalanceSpec",
]
