from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi
from typing import Any

import numpy as np

from .domain import BearingSpec, EngineeringError, RotorProject, ShaftSection
from .services import EngineeringValidationService


@dataclass(slots=True, frozen=True)
class ShaftElementPlan:
    n: int
    x0_mm: float
    x1_mm: float
    physical_section: int
    od0_mm: float
    od1_mm: float
    id0_mm: float
    id1_mm: float
    material: str

    @property
    def length_mm(self) -> float:
        return self.x1_mm - self.x0_mm


@dataclass(slots=True, frozen=True)
class NodeMapping:
    position_mm: float
    node: int | None
    exact: bool


@dataclass(slots=True)
class RossBuildResult:
    rotor: Any
    shaft_plan: list[ShaftElementPlan]
    node_positions_mm: list[float]
    unresolved_positions_mm: list[float]


class RossModelBuilder:
    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def _ross(self) -> Any:
        if self.rs is None:
            self.rs = import_module("ross")
        return self.rs

    @staticmethod
    def shaft_plan(project: RotorProject) -> list[ShaftElementPlan]:
        project.validate()
        split = project.topology_split_positions_mm()
        plan: list[ShaftElementPlan] = []

        def section_at(x0: float, x1: float) -> tuple[ShaftSection, float, float]:
            midpoint = 0.5 * (x0 + x1)
            start = 0.0
            for section in project.shaft_sections:
                end = start + section.length_mm
                if start - 1e-9 <= midpoint <= end + 1e-9:
                    return section, (x0 - start) / section.length_mm, (x1 - start) / section.length_mm
                start = end
            raise EngineeringError(f"Cannot map FE interval [{x0}, {x1}] mm to a physical shaft section.")

        for n, (x0, x1) in enumerate(zip(split, split[1:])):
            section, t0, t1 = section_at(x0, x1)
            od0 = section.od_left_mm + (section.odr_mm - section.od_left_mm) * t0
            od1 = section.od_left_mm + (section.odr_mm - section.od_left_mm) * t1
            id0 = section.id_left_mm + (section.idr_mm - section.id_left_mm) * t0
            id1 = section.id_left_mm + (section.idr_mm - section.id_left_mm) * t1
            plan.append(ShaftElementPlan(n, x0, x1, section.section, od0, od1, id0, id1, section.material))
        return plan

    @staticmethod
    def node_positions_mm(project: RotorProject) -> list[float]:
        return project.topology_split_positions_mm()

    @staticmethod
    def map_position(project: RotorProject, position_mm: float, *, tolerance_mm: float = 1e-7) -> NodeMapping:
        for node, x in enumerate(project.topology_split_positions_mm()):
            if abs(x - position_mm) <= tolerance_mm:
                return NodeMapping(position_mm, node, True)
        return NodeMapping(position_mm, None, False)

    def _material(self, project: RotorProject, name: str) -> Any:
        rs = self._ross()
        spec = project.materials[name]
        return rs.Material(name=spec.name, rho=spec.density_kg_m3, E=spec.young_pa, G_s=spec.shear_pa)

    def _bearing(self, project: RotorProject, spec: BearingSpec) -> Any:
        rs = self._ross()
        mapping = self.map_position(project, spec.position_mm)
        if mapping.node is None:
            raise EngineeringError(f"Bearing {spec.name!r} is not located at an FE node.")

        if spec.ross_class == "BallBearingElement":
            required = ("n_balls", "d_balls_m", "static_load_n", "contact_angle_rad")
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Ball bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            return rs.BallBearingElement(n=mapping.node, n_balls=int(spec.metadata["n_balls"]), d_balls=float(spec.metadata["d_balls_m"]), fs=float(spec.metadata["static_load_n"]), alpha=float(spec.metadata["contact_angle_rad"]), cxx=float(spec.metadata["cxx"]) if "cxx" in spec.metadata else None, cyy=float(spec.metadata["cyy"]) if "cyy" in spec.metadata else None, tag=spec.name)

        if spec.ross_class == "RollerBearingElement":
            required = ("n_rollers", "roller_length_m", "static_load_n", "contact_angle_rad")
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Roller bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            return rs.RollerBearingElement(n=mapping.node, n_rollers=int(spec.metadata["n_rollers"]), l_rollers=float(spec.metadata["roller_length_m"]), fs=float(spec.metadata["static_load_n"]), alpha=float(spec.metadata["contact_angle_rad"]), cxx=float(spec.metadata["cxx"]) if "cxx" in spec.metadata else None, cyy=float(spec.metadata["cyy"]) if "cyy" in spec.metadata else None, tag=spec.name)

        if spec.ross_class == "CylindricalBearing":
            required = ("speed_rpm", "weight_n", "bearing_length_m", "journal_diameter_m", "radial_clearance_m", "oil_viscosity_pa_s")
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Cylindrical bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            speed = np.asarray(spec.metadata["speed_rpm"], dtype=float) * 2.0 * pi / 60.0
            return rs.CylindricalBearing(n=mapping.node, speed=speed, weight=float(spec.metadata["weight_n"]), bearing_length=float(spec.metadata["bearing_length_m"]), journal_diameter=float(spec.metadata["journal_diameter_m"]), radial_clearance=float(spec.metadata["radial_clearance_m"]), oil_viscosity=float(spec.metadata["oil_viscosity_pa_s"]), tag=spec.name)

        if spec.ross_class != "BearingElement":
            raise EngineeringError(f"Bearing class {spec.ross_class} is not enabled in the qualified 0.8.0 builder.")
        if spec.coefficients:
            rpm = np.asarray([p.rpm for p in spec.coefficients], dtype=float)
            frequency = rpm * 2.0 * pi / 60.0
            return rs.BearingElement(n=mapping.node, kxx=np.asarray([p.kxx for p in spec.coefficients]), kyy=np.asarray([p.kyy for p in spec.coefficients]), kxy=np.asarray([p.kxy for p in spec.coefficients]), kyx=np.asarray([p.kyx for p in spec.coefficients]), cxx=np.asarray([p.cxx for p in spec.coefficients]), cyy=np.asarray([p.cyy for p in spec.coefficients]), cxy=np.asarray([p.cxy for p in spec.coefficients]), cyx=np.asarray([p.cyx for p in spec.coefficients]), frequency=frequency, tag=spec.name)
        return rs.BearingElement(n=mapping.node, kxx=spec.kxx, kyy=spec.kyy or spec.kxx, kxy=spec.kxy, kyx=spec.kyx, cxx=spec.cxx, cyy=spec.cyy or spec.cxx, cxy=spec.cxy, cyx=spec.cyx, tag=spec.name)

    def build(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        issues = EngineeringValidationService().validate(project)
        if strict and any(i.severity == "error" for i in issues):
            raise EngineeringError("; ".join(i.message for i in issues if i.severity == "error"))
        if strict and project.distributed_masses:
            raise EngineeringError("Distributed masses are preserved but do not yet have a qualified ROSS realization in 0.8.0; strict build is intentionally blocked.")

        rs = self._ross()
        plan = self.shaft_plan(project)
        material_cache = {name: self._material(project, name) for name in project.materials}
        shaft_elements = [rs.ShaftElement(L=e.length_mm / 1000.0, idl=e.id0_mm / 1000.0, odl=e.od0_mm / 1000.0, idr=e.id1_mm / 1000.0, odr=e.od1_mm / 1000.0, material=material_cache[e.material], n=e.n, tag=f"S{e.physical_section:02d}.{e.n:02d}") for e in plan]
        bearings = [self._bearing(project, b) for b in project.bearings]
        disks = []
        unresolved: list[float] = []
        for disk in project.disks:
            mapping = self.map_position(project, disk.position_mm)
            if mapping.node is None:
                unresolved.append(disk.position_mm)
                continue
            disks.append(rs.DiskElement(mapping.node, disk.mass_kg, disk.id_kg_m2, disk.ip_kg_m2, tag=disk.name))
        point_masses = []
        for mass in project.point_masses:
            mapping = self.map_position(project, mass.position_mm)
            if mapping.node is None:
                unresolved.append(mass.position_mm)
                continue
            point_masses.append(rs.PointMass(n=mapping.node, m=mass.mass_kg, tag=mass.name))
        rotor = rs.Rotor(shaft_elements=shaft_elements, disk_elements=disks or None, bearing_elements=bearings or None, point_mass_elements=point_masses or None, tag=project.name)
        return RossBuildResult(rotor, plan, self.node_positions_mm(project), sorted(set(unresolved)))


class RossBackend:
    """Application-facing scientific boundary. Qt widgets must not call ROSS directly."""

    def __init__(self, ross_module: Any | None = None) -> None:
        self.builder = RossModelBuilder(ross_module)

    def build_rotor(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        return self.builder.build(project, strict=strict)

    def run_static(self, project: RotorProject) -> Any:
        return self.build_rotor(project).rotor.run_static()

    def run_modal(self, project: RotorProject, speed_rpm: float, *, num_modes: int = 12) -> Any:
        speed = float(speed_rpm) * 2.0 * pi / 60.0
        return self.build_rotor(project).rotor.run_modal(speed=speed, num_modes=num_modes)

    def run_campbell(self, project: RotorProject, speeds_rpm: list[float], *, frequencies: int = 6) -> Any:
        speeds = np.asarray(speeds_rpm, dtype=float) * 2.0 * pi / 60.0
        return self.build_rotor(project).rotor.run_campbell(speed_range=speeds, frequencies=frequencies)
