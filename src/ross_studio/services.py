from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from .domain import AdapterStatus, BearingGroup, RotorProject


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
        Capability(BearingGroup.THD, "SqueezeFilmDamper", "Squeeze Film Damper", AdapterStatus.PLANNED, "ROSS class exists; damper-domain adapter is pending qualification."),
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
            rows.append({"group": cap.group.value, "class": cap.ross_class, "title": cap.title, "status": status.value, "reason": reason, "can_execute": status == AdapterStatus.VALIDATED})
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
        if project.distributed_masses:
            issues.append(ValidationIssue("warning", "DISTRIBUTED_MASS_REALIZATION", "Distributed rotor masses are preserved in the domain and topology, but 0.8.0 does not silently lump them into DiskElement. A qualified realization policy is required before production analysis."))
        node_positions = set(project.topology_split_positions_mm())
        for load in project.loads:
            if round(load.position_mm, 10) not in node_positions:
                issues.append(ValidationIssue("warning", "LOAD_NODE_MAPPING", f"{load.name} at {load.position_mm:g} mm is preserved axially and requires explicit node insertion/mapping before force assembly."))
        for mass in project.point_masses:
            if round(mass.position_mm, 10) not in node_positions:
                issues.append(ValidationIssue("warning", "POINT_MASS_NODE_MAPPING", f"{mass.name} at {mass.position_mm:g} mm requires explicit node insertion/mapping."))
        return issues
