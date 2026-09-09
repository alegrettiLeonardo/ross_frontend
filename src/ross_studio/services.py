from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from .concentrated import validate_concentrated_spec
from .domain import AdapterStatus, BearingGroup, EngineeringError, RotorProject
from .topology import NodeInsertionService
from .ump import project_ump_specs


@dataclass(slots=True, frozen=True)
class Capability:
    group: BearingGroup
    ross_class: str
    title: str
    adapter_status: AdapterStatus
    reason: str = ""


class RossCapabilityRegistry:
    """Separate ROSS class availability from ROSS Studio adapter readiness."""

    _CAPABILITIES = (
        Capability(BearingGroup.GENERAL, "BearingElement", "Coefficient K/C", AdapterStatus.VALIDATED),
        Capability(BearingGroup.GENERAL, "BallBearingElement", "Ball Bearing", AdapterStatus.VALIDATED),
        Capability(BearingGroup.GENERAL, "RollerBearingElement", "Roller Bearing", AdapterStatus.VALIDATED),
        Capability(BearingGroup.GENERAL, "CylindricalBearing", "Cylindrical Bearing", AdapterStatus.VALIDATED),
        Capability(BearingGroup.THD, "PlainJournal", "Plain Journal", AdapterStatus.PLANNED, "THD editor/adapter requires validated geometry, lubricant and thermal mapping."),
        Capability(BearingGroup.THD, "TiltingPad", "Tilting Pad", AdapterStatus.PLANNED, "THD editor exists visually but scientific parameter mapping is not qualified yet."),
        Capability(BearingGroup.THD, "ThrustPad", "Thrust Pad", AdapterStatus.PLANNED, "ROSS class exists; ROSS Studio thrust-domain adapter is not qualified."),
        Capability(BearingGroup.THD, "SqueezeFilmDamper", "Squeeze Film Damper", AdapterStatus.PLANNED, "ROSS class exists; ROSS Studio damper-domain adapter is pending qualification."),
        Capability(BearingGroup.AMB, "MagneticBearingElement", "Active Magnetic Bearing", AdapterStatus.BLOCKED, "Requires an explicit actuator/sensor/controller domain before execution is enabled."),
    )

    def __init__(self, ross_module: Any | None = None) -> None:
        self._ross = ross_module

    @property
    def ross_module(self) -> Any | None:
        if self._ross is not None:
            return self._ross
        try:
            self._ross = import_module("ross")
        except Exception:
            self._ross = None
        return self._ross

    def class_exists(self, ross_class: str) -> bool:
        module = self.ross_module
        return module is not None and hasattr(module, ross_class)

    def capabilities(self, group: BearingGroup | None = None) -> tuple[Capability, ...]:
        return tuple(c for c in self._CAPABILITIES if group is None or c.group == group)

    def effective_status(self, ross_class: str) -> tuple[AdapterStatus, str]:
        capability = next((c for c in self._CAPABILITIES if c.ross_class == ross_class), None)
        if capability is None:
            return AdapterStatus.BLOCKED, "Class is not registered in ROSS Studio."
        if not self.class_exists(ross_class):
            return AdapterStatus.BLOCKED, f"{ross_class} is not available in the installed ROSS package."
        return capability.adapter_status, capability.reason


class BearingCatalogService:
    def __init__(self, registry: RossCapabilityRegistry | None = None) -> None:
        self.registry = registry or RossCapabilityRegistry()

    def groups(self) -> tuple[BearingGroup, ...]:
        return (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB)

    def entries(self, group: BearingGroup) -> list[dict[str, str | bool]]:
        rows: list[dict[str, str | bool]] = []
        for cap in self.registry.capabilities(group):
            status, reason = self.registry.effective_status(cap.ross_class)
            rows.append({
                "group": cap.group.value,
                "class": cap.ross_class,
                "title": cap.title,
                "status": status.value,
                "reason": reason,
                "can_execute": status == AdapterStatus.VALIDATED,
            })
        return rows


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str


class EngineeringValidationService:
    """Readiness gate before an engineering project is translated into ROSS."""

    def validate(self, project: RotorProject) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            project.validate()
        except Exception as exc:
            return [ValidationIssue("error", "DOMAIN", str(exc))]

        support_indices = [support.bearing_index for support in project.supports]
        duplicates = sorted({index for index in support_indices if support_indices.count(index) > 1})
        for bearing_index in duplicates:
            issues.append(ValidationIssue(
                "error",
                "DUPLICATE_SUPPORT_LINK",
                f"Bearing #{bearing_index + 1} has more than one flexible support. "
                "ROSS Studio requires one unambiguous support chain per bearing.",
            ))

        for support in project.supports:
            if 0 <= support.bearing_index < len(project.bearings):
                bearing = project.bearings[support.bearing_index]
                if bearing.ross_class == "CylindricalBearing":
                    issues.append(ValidationIssue(
                        "error",
                        "CYLINDRICAL_SUPPORT_LINK_UNAVAILABLE",
                        f"{bearing.name} uses CylindricalBearing with flexible support {support.name}. "
                        "ROSS 2.3 CylindricalBearing does not expose n_link; execution is blocked until a qualified equivalent adapter exists.",
                    ))

        for mass in project.distributed_masses:
            try:
                mass.equivalent_disk_inertias_kg_m2()
            except EngineeringError as exc:
                issues.append(ValidationIssue("error", "DISTRIBUTED_MASS_GEOMETRY", str(exc)))

        for spec in project_ump_specs(project):
            try:
                spec.validate()
            except EngineeringError as exc:
                issues.append(ValidationIssue("error", "UMP_INPUT_INVALID", str(exc)))
                continue
            if spec.end_mm > project.total_length_mm + 1e-7:
                issues.append(ValidationIssue(
                    "error",
                    "UMP_SPAN_OUTSIDE_SHAFT",
                    f"{spec.name} ends at {spec.end_mm:g} mm beyond shaft length {project.total_length_mm:g} mm.",
                ))
            elif spec.stiffness_per_length_n_m2 == 0.0:
                issues.append(ValidationIssue(
                    "warning",
                    "UMP_ZERO_STIFFNESS",
                    f"{spec.name} is enabled but its distributed negative stiffness is zero N/m².",
                ))

        for mass in project.point_masses:
            try:
                validate_concentrated_spec(mass)
            except EngineeringError as exc:
                issues.append(ValidationIssue("error", "CONCENTRATED_MASS_INERTIA_INVALID", str(exc)))

        plan = NodeInsertionService.plan(project)
        node_positions = set(plan.positions_mm)
        required_positions: list[tuple[str, float]] = []
        required_positions.extend((bearing.name, bearing.position_mm) for bearing in project.bearings)
        required_positions.extend((mass.name, mass.center_mm) for mass in project.distributed_masses)
        required_positions.extend((mass.name, mass.position_mm) for mass in project.point_masses)
        required_positions.extend((disk.name, disk.position_mm) for disk in project.disks)
        required_positions.extend((seal.name, seal.position_mm) for seal in project.seals)
        required_positions.extend((coupling.name, coupling.position_mm) for coupling in project.couplings)
        required_positions.extend((load.name, load.position_mm) for load in project.loads)
        required_positions.extend((probe.name, probe.position_mm) for probe in project.probes)
        for name, position in required_positions:
            if round(position, 10) not in node_positions:
                issues.append(ValidationIssue(
                    "error",
                    "NODE_INSERTION_FAILED",
                    f"{name} at {position:g} mm did not receive an exact FE node.",
                ))

        return issues
