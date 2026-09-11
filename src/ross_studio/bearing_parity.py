from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BearingAnalysisFormulation(str, Enum):
    # The executable ROSS 2.3 THD contract is the default selection. Keeping this
    # first prevents an event-loop race when the user moves directly from a General
    # bearing to PlainJournal/TiltingPad and immediately presses Calculate.
    DIMENSIONAL_HEAT_BALANCE = "Dimensional · Heat Balance / THD"
    DIMENSIONAL_CONSTANT_VISCOSITY = "Dimensional · Constant Viscosity"
    NON_DIMENSIONAL = "Non-Dimensional"


class BearingCoordinateConvention(str, Enum):
    STANDARD_XY = "Standard Coordinates (X-Y)"
    LUND_X_LOAD = "Lund Convention (X = W)"


class CapabilityStatus(str, Enum):
    ROSS_NATIVE = "ROSS_NATIVE"
    PREPARED = "PREPARED_NEEDS_QUALIFIED_ADAPTER"
    BLOCKED = "BLOCKED"


@dataclass(slots=True, frozen=True)
class Capability:
    status: CapabilityStatus
    note: str


@dataclass(slots=True, frozen=True)
class BearingStudioContract:
    """Explicit BePerf-equivalence surface separated from solver implementation.

    The UI may expose a requirement before an exact ROSS 2.3.0 mapping is
    qualified, but a PREPARED/BLOCKED capability must never be executed as though
    it were native.  This is the boundary that lets Bearing Studio grow toward
    BePerf breadth without silently changing bearing physics.
    """

    model_class: str
    analyses: dict[BearingAnalysisFormulation, Capability]
    coordinates: dict[BearingCoordinateConvention, Capability]
    input_groups: tuple[str, ...]
    result_groups: tuple[str, ...]


BEPERF_INPUT_GROUPS = (
    "Geometry",
    "Clearance",
    "Preload / Offset",
    "Pad Geometry / Pivot",
    "Load / Speed",
    "Lubricant Properties",
    "Oil Supply / Flow",
    "Thermal Model",
    "Coordinate Convention",
    "Coefficient Coordinate Angle",
    "Numerical / Convergence",
)

BEPERF_RESULT_GROUPS = (
    "Operating Point",
    "Eccentricity Ratio",
    "Attitude Angle",
    "Minimum Film Thickness",
    "Maximum Film Pressure",
    "Frictional Power Loss",
    "Oil Flow",
    "Temperature",
    "Dynamic K/C Coefficients",
    "Pressure Field",
    "Film Thickness Field",
    "Convergence",
)


def contract_for(ross_class: str) -> BearingStudioContract:
    thermal_native = ross_class in {"PlainJournal", "TiltingPad"}
    general_fluid = ross_class in {"PlainJournal", "TiltingPad", "CylindricalBearing"}

    analyses = {
        BearingAnalysisFormulation.DIMENSIONAL_CONSTANT_VISCOSITY: Capability(
            CapabilityStatus.PREPARED,
            "BePerf constant-viscosity semantics are represented in the UI contract, but the exact ROSS 2.3.0 adapter is not yet qualified.",
        ),
        BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE: Capability(
            CapabilityStatus.ROSS_NATIVE if thermal_native else CapabilityStatus.PREPARED,
            (
                "ROSS 2.3.0 native thermal hydrodynamic solution is available; numerical equivalence to BePerf is not asserted."
                if thermal_native
                else "This model has no qualified BePerf heat-balance mapping in the current adapter."
            ),
        ),
        BearingAnalysisFormulation.NON_DIMENSIONAL: Capability(
            CapabilityStatus.PREPARED if general_fluid else CapabilityStatus.BLOCKED,
            "The BePerf non-dimensional input/result surface is reserved; no hidden dimensional reconstruction is allowed.",
        ),
    }
    coordinates = {
        BearingCoordinateConvention.STANDARD_XY: Capability(
            CapabilityStatus.ROSS_NATIVE if general_fluid else CapabilityStatus.PREPARED,
            "ROSS lateral X-Y inputs are treated as the Standard coordinate contract.",
        ),
        BearingCoordinateConvention.LUND_X_LOAD: Capability(
            CapabilityStatus.PREPARED,
            "Requires an explicit, tested load/bearing coefficient coordinate transformation before execution.",
        ),
    }
    return BearingStudioContract(
        model_class=ross_class,
        analyses=analyses,
        coordinates=coordinates,
        input_groups=BEPERF_INPUT_GROUPS,
        result_groups=BEPERF_RESULT_GROUPS,
    )


def require_executable_contract(
    ross_class: str,
    analysis: BearingAnalysisFormulation,
    coordinates: BearingCoordinateConvention,
) -> None:
    contract = contract_for(ross_class)
    a = contract.analyses[analysis]
    c = contract.coordinates[coordinates]
    missing = []
    if a.status is not CapabilityStatus.ROSS_NATIVE:
        missing.append(f"analysis={analysis.value}: {a.note}")
    if c.status is not CapabilityStatus.ROSS_NATIVE:
        missing.append(f"coordinates={coordinates.value}: {c.note}")
    if missing:
        raise ValueError(
            "Bearing Studio contract is present but not scientifically qualified for execution: "
            + " | ".join(missing)
        )


__all__ = [
    "BEPERF_INPUT_GROUPS",
    "BEPERF_RESULT_GROUPS",
    "BearingAnalysisFormulation",
    "BearingCoordinateConvention",
    "BearingStudioContract",
    "Capability",
    "CapabilityStatus",
    "contract_for",
    "require_executable_contract",
]
