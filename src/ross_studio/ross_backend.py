from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi
from typing import Any

import numpy as np

from .domain import BearingSpec, EngineeringError, RotorProject, ShaftSection
from .services import EngineeringValidationService
from .topology import NodeInsertionPlan, NodeInsertionService


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


@dataclass(slots=True, frozen=True)
class EquivalentDiskPlan:
    name: str
    node: int
    position_mm: float
    mass_kg: float
    id_kg_m2: float
    ip_kg_m2: float
    source: str = "legacy [Massas]"


@dataclass(slots=True)
class RossBuildResult:
    rotor: Any
    shaft_plan: list[ShaftElementPlan]
    node_positions_mm: list[float]
    unresolved_positions_mm: list[float]
    support_link_nodes: dict[str, int]
    node_insertion_plan: NodeInsertionPlan
    equivalent_disks: list[EquivalentDiskPlan]


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
        split = NodeInsertionService.plan(project).positions_mm
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
        return list(NodeInsertionService.plan(project).positions_mm)

    @staticmethod
    def map_position(project: RotorProject, position_mm: float, *, tolerance_mm: float = 1e-7) -> NodeMapping:
        plan = NodeInsertionService.plan(project)
        node = plan.node_for(position_mm, tolerance_mm=tolerance_mm)
        return NodeMapping(position_mm, node, node is not None)

    def _material(self, project: RotorProject, name: str) -> Any:
        rs = self._ross()
        spec = project.materials[name]
        return rs.Material(name=spec.name, rho=spec.density_kg_m3, E=spec.young_pa, G_s=spec.shear_pa)

    def _bearing(self, project: RotorProject, spec: BearingSpec, *, n_link: int | None = None) -> Any:
        rs = self._ross()
        mapping = self.map_position(project, spec.position_mm)
        if mapping.node is None:
            raise EngineeringError(f"Bearing {spec.name!r} is not located at an FE node.")

        if spec.ross_class == "BallBearingElement":
            required = ("n_balls", "d_balls_m", "static_load_n", "contact_angle_rad")
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Ball bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            return rs.BallBearingElement(
                n=mapping.node,
                n_balls=int(spec.metadata["n_balls"]),
                d_balls=float(spec.metadata["d_balls_m"]),
                fs=float(spec.metadata["static_load_n"]),
                alpha=float(spec.metadata["contact_angle_rad"]),
                cxx=float(spec.metadata["cxx"]) if "cxx" in spec.metadata else None,
                cyy=float(spec.metadata["cyy"]) if "cyy" in spec.metadata else None,
                tag=spec.name,
                n_link=n_link,
            )

        if spec.ross_class == "RollerBearingElement":
            required = ("n_rollers", "roller_length_m", "static_load_n", "contact_angle_rad")
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Roller bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            return rs.RollerBearingElement(
                n=mapping.node,
                n_rollers=int(spec.metadata["n_rollers"]),
                l_rollers=float(spec.metadata["roller_length_m"]),
                fs=float(spec.metadata["static_load_n"]),
                alpha=float(spec.metadata["contact_angle_rad"]),
                cxx=float(spec.metadata["cxx"]) if "cxx" in spec.metadata else None,
                cyy=float(spec.metadata["cyy"]) if "cyy" in spec.metadata else None,
                tag=spec.name,
                n_link=n_link,
            )

        if spec.ross_class == "CylindricalBearing":
            if n_link is not None:
                raise EngineeringError(
                    f"Cylindrical bearing {spec.name!r} cannot be linked to a flexible support with the "
                    "ROSS 2.3 CylindricalBearing constructor. Use a qualified equivalent adapter before execution."
                )
            required = (
                "speed_rpm",
                "weight_n",
                "bearing_length_m",
                "journal_diameter_m",
                "radial_clearance_m",
                "oil_viscosity_pa_s",
            )
            missing = [key for key in required if key not in spec.metadata]
            if missing:
                raise EngineeringError(f"Cylindrical bearing {spec.name!r} is missing metadata: {', '.join(missing)}")
            speed = np.asarray(spec.metadata["speed_rpm"], dtype=float) * 2.0 * pi / 60.0
            return rs.CylindricalBearing(
                n=mapping.node,
                speed=speed,
                weight=float(spec.metadata["weight_n"]),
                bearing_length=float(spec.metadata["bearing_length_m"]),
                journal_diameter=float(spec.metadata["journal_diameter_m"]),
                radial_clearance=float(spec.metadata["radial_clearance_m"]),
                oil_viscosity=float(spec.metadata["oil_viscosity_pa_s"]),
                tag=spec.name,
            )

        if spec.ross_class != "BearingElement":
            raise EngineeringError(f"Bearing class {spec.ross_class} is not enabled in the qualified 0.8.0 builder.")
        common = {"n": mapping.node, "tag": spec.name, "n_link": n_link}
        if spec.coefficients:
            rpm = np.asarray([point.rpm for point in spec.coefficients], dtype=float)
            frequency = rpm * 2.0 * pi / 60.0
            return rs.BearingElement(
                **common,
                kxx=np.asarray([point.kxx for point in spec.coefficients]),
                kyy=np.asarray([point.kyy for point in spec.coefficients]),
                kxy=np.asarray([point.kxy for point in spec.coefficients]),
                kyx=np.asarray([point.kyx for point in spec.coefficients]),
                cxx=np.asarray([point.cxx for point in spec.coefficients]),
                cyy=np.asarray([point.cyy for point in spec.coefficients]),
                cxy=np.asarray([point.cxy for point in spec.coefficients]),
                cyx=np.asarray([point.cyx for point in spec.coefficients]),
                frequency=frequency,
            )
        return rs.BearingElement(
            **common,
            kxx=spec.kxx,
            kyy=spec.kyy or spec.kxx,
            kxy=spec.kxy,
            kyx=spec.kyx,
            cxx=spec.cxx,
            cyy=spec.cyy or spec.cxx,
            cxy=spec.cxy,
            cyx=spec.cyx,
        )

    def build(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        issues = EngineeringValidationService().validate(project)
        if strict and any(issue.severity == "error" for issue in issues):
            raise EngineeringError("; ".join(issue.message for issue in issues if issue.severity == "error"))

        rs = self._ross()
        insertion_plan = NodeInsertionService.plan(project)
        plan = self.shaft_plan(project)
        node_positions = list(insertion_plan.positions_mm)
        material_cache = {name: self._material(project, name) for name in project.materials}
        shaft_elements = [
            rs.ShaftElement(
                L=element.length_mm / 1000.0,
                idl=element.id0_mm / 1000.0,
                odl=element.od0_mm / 1000.0,
                idr=element.id1_mm / 1000.0,
                odr=element.od1_mm / 1000.0,
                material=material_cache[element.material],
                n=element.n,
                tag=f"S{element.physical_section:02d}.{element.n:02d}",
            )
            for element in plan
        ]

        support_by_bearing = {support.bearing_index: support for support in project.supports}
        support_link_nodes: dict[str, int] = {}
        bearings: list[Any] = []
        point_masses: list[Any] = []
        next_link_node = len(node_positions)
        for bearing_index, bearing_spec in enumerate(project.bearings):
            support = support_by_bearing.get(bearing_index)
            link_node: int | None = None
            if support is not None:
                link_node = next_link_node
                next_link_node += 1
                support_link_nodes[support.name] = link_node
            bearings.append(self._bearing(project, bearing_spec, n_link=link_node))
            if support is not None and link_node is not None:
                bearings.append(
                    rs.BearingElement(
                        n=link_node,
                        kxx=support.kxx,
                        kyy=support.kyy or support.kxx,
                        kxy=support.kxy,
                        kyx=support.kyx,
                        cxx=support.cxx,
                        cyy=support.cyy or support.cxx,
                        cxy=support.cxy,
                        cyx=support.cyx,
                        tag=f"{support.name} / ground",
                    )
                )
                point_masses.append(rs.PointMass(n=link_node, m=support.mass_kg, tag=f"{support.name} mass"))

        disks: list[Any] = []
        equivalent_disks: list[EquivalentDiskPlan] = []
        unresolved: list[float] = []

        for mass in project.distributed_masses:
            mapping = self.map_position(project, mass.center_mm)
            if mapping.node is None:
                unresolved.append(mass.center_mm)
                continue
            id_kg_m2, ip_kg_m2 = mass.equivalent_disk_inertias_kg_m2()
            disks.append(
                rs.DiskElement(
                    mapping.node,
                    mass.mass_kg,
                    id_kg_m2,
                    ip_kg_m2,
                    tag=f"{mass.name} / legacy equivalent",
                )
            )
            equivalent_disks.append(EquivalentDiskPlan(
                name=mass.name,
                node=mapping.node,
                position_mm=mass.center_mm,
                mass_kg=mass.mass_kg,
                id_kg_m2=id_kg_m2,
                ip_kg_m2=ip_kg_m2,
            ))

        for disk in project.disks:
            mapping = self.map_position(project, disk.position_mm)
            if mapping.node is None:
                unresolved.append(disk.position_mm)
                continue
            disks.append(rs.DiskElement(mapping.node, disk.mass_kg, disk.id_kg_m2, disk.ip_kg_m2, tag=disk.name))

        for mass in project.point_masses:
            mapping = self.map_position(project, mass.position_mm)
            if mapping.node is None:
                unresolved.append(mass.position_mm)
                continue
            kwargs: dict[str, Any] = {"n": mapping.node, "m": mass.mass_kg, "tag": mass.name}
            if mass.mx_kg is not None:
                kwargs["mx"] = mass.mx_kg
            if mass.my_kg is not None:
                kwargs["my"] = mass.my_kg
            if mass.mz_kg is not None:
                kwargs["mz"] = mass.mz_kg
            point_masses.append(rs.PointMass(**kwargs))

        unresolved = sorted(set(unresolved))
        if strict and unresolved:
            joined = ", ".join(f"{x:g}" for x in unresolved)
            raise EngineeringError(f"Strict ROSS build has unresolved axial positions: {joined} mm.")

        rotor = rs.Rotor(
            shaft_elements=shaft_elements,
            disk_elements=disks or None,
            bearing_elements=bearings or None,
            point_mass_elements=point_masses or None,
            tag=project.name,
        )
        return RossBuildResult(
            rotor=rotor,
            shaft_plan=plan,
            node_positions_mm=node_positions,
            unresolved_positions_mm=unresolved,
            support_link_nodes=support_link_nodes,
            node_insertion_plan=insertion_plan,
            equivalent_disks=equivalent_disks,
        )


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
