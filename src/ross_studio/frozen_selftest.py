from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from .domain import AdapterStatus, BearingGroup
from .models import load_reference_project_model
from .ross_backend import RossModelBuilder
from .ross_native_view import RossRotorPlotService
from .services import BearingCatalogService, EngineeringValidationService


QUALIFIED_ROSS_VERSION = "2.3.0"
EXPECTED_EXECUTABLE_CLASSES = {
    "BearingElement",
    "BallBearingElement",
    "RollerBearingElement",
    "CylindricalBearing",
    "PlainJournal",
    "TiltingPad",
    "SqueezeFilmDamper",
    "ThrustPad",
    "MagneticBearingElement",
}
EXPECTED_BLOCKED_CLASSES: set[str] = set()


@dataclass(slots=True, frozen=True)
class FrozenSelfTestResult:
    status: str
    ross_version: str
    project: str
    physical_sections: int
    requested_base_elements: int
    effective_shaft_elements: int
    shaft_nodes: int
    unresolved_positions_mm: tuple[float, ...]
    native_plot_traces: int
    executable_classes: tuple[str, ...]
    blocked_classes: tuple[str, ...]
    validation_errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_frozen_self_test(ross_module: Any | None = None) -> FrozenSelfTestResult:
    """Exercise the same production objects that a frozen ROSS Studio executable uses.

    This is deliberately stronger than an import smoke test. It verifies the pinned ROSS
    runtime, the capability registry that drives Bearing Studio, the strict OP-W60 rotor
    assembly and the native ``Rotor.plot_rotor`` path. A frozen package that accidentally
    drops ROSS bearing submodules must fail here instead of degrading the GUI to
    ``0 executable adapters``.
    """

    rs = ross_module or import_module("ross")
    ross_version = str(getattr(rs, "__version__", "unknown"))
    if ross_version != QUALIFIED_ROSS_VERSION:
        raise RuntimeError(
            f"Frozen ROSS Studio is qualified for ROSS {QUALIFIED_ROSS_VERSION}; received {ross_version}."
        )

    project_model = load_reference_project_model()
    project = project_model.engineering
    if project is None:
        raise RuntimeError("OP-W60 engineering domain was not packaged into the executable.")

    validation = EngineeringValidationService().validate(project)
    errors = tuple(issue.message for issue in validation if issue.severity == "error")
    if errors:
        raise RuntimeError(f"Packaged OP-W60 failed engineering validation: {errors[0]}")

    catalog = BearingCatalogService()
    executable: set[str] = set()
    blocked: set[str] = set()
    for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
        for row in catalog.entries(group):
            ross_class = str(row["class"])
            if bool(row["can_execute"]):
                executable.add(ross_class)
            else:
                blocked.add(ross_class)

    if executable != EXPECTED_EXECUTABLE_CLASSES:
        missing = sorted(EXPECTED_EXECUTABLE_CLASSES - executable)
        unexpected = sorted(executable - EXPECTED_EXECUTABLE_CLASSES)
        raise RuntimeError(
            "Frozen Bearing Studio capability mismatch: "
            f"missing executable={missing}, unexpected executable={unexpected}, blocked={sorted(blocked)}."
        )
    if blocked != EXPECTED_BLOCKED_CLASSES:
        raise RuntimeError(
            f"Frozen Bearing Studio blocked-class mismatch: expected {sorted(EXPECTED_BLOCKED_CLASSES)}, "
            f"received {sorted(blocked)}."
        )

    # Re-check registry status directly so a UI/catalog transformation cannot mask a
    # missing ROSS class in a frozen build.
    for ross_class in EXPECTED_EXECUTABLE_CLASSES:
        status, reason = catalog.registry.effective_status(ross_class)
        if status != AdapterStatus.VALIDATED:
            raise RuntimeError(f"{ross_class} is not VALIDATED in frozen runtime: {status.value}. {reason}")

    from .amb_qualification import qualify_amb_assembly
    qualify_amb_assembly(rs)

    built = RossModelBuilder(rs).build(project, strict=True)
    if built.unresolved_positions_mm:
        raise RuntimeError(f"Frozen strict build contains unresolved positions: {built.unresolved_positions_mm}")

    native = RossRotorPlotService(rs).build_figure(project)
    trace_count = len(tuple(native.figure.data))
    if trace_count <= 0:
        raise RuntimeError("Frozen ROSS native rotor plot contains no Plotly traces.")

    return FrozenSelfTestResult(
        status="PASS",
        ross_version=ross_version,
        project=project.name,
        physical_sections=project.physical_section_count,
        requested_base_elements=project.requested_shaft_element_count,
        effective_shaft_elements=len(built.shaft_plan),
        shaft_nodes=len(built.node_positions_mm),
        unresolved_positions_mm=tuple(float(x) for x in built.unresolved_positions_mm),
        native_plot_traces=trace_count,
        executable_classes=tuple(sorted(executable)),
        blocked_classes=tuple(sorted(blocked)),
        validation_errors=errors,
    )


__all__ = [
    "EXPECTED_BLOCKED_CLASSES",
    "EXPECTED_EXECUTABLE_CLASSES",
    "FrozenSelfTestResult",
    "QUALIFIED_ROSS_VERSION",
    "run_frozen_self_test",
]
