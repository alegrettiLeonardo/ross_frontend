from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import pi
from typing import Any

import numpy as np

from .concentrated import concentrated_disk_class
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
    shear_effects: bool = True
    rotary_inertia: bool = True
    gyroscopic: bool = True

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


@dataclass(slots=True, frozen=True)
class EquivalentPointMassPlan:
    name: str
    node: int
    position_mm: float
    mass_kg: float
    ix_kg_m2: float = 0.0
    iy_kg_m2: float = 0.0
    iz_kg_m2: float = 0.0
    source: str = "legacy [Concent] mass + Ix/Iy/Iz"


@dataclass(slots=True)
class RossBuildResult:
    rotor: Any
    shaft_plan: list[ShaftElementPlan]
    node_positions_mm: list[float]
    unresolved_positions_mm: list[float]
    support_link_nodes: dict[str, int]
    node_insertion_plan: NodeInsertionPlan
    equivalent_disks: list[EquivalentDiskPlan]
    equivalent_point_masses: list[EquivalentPointMassPlan]


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
            plan.append(ShaftElementPlan(
                n, x0, x1, section.section, od0, od1, id0, id1, section.material,
                bool(section.shear_effects), bool(section.rotary_inertia), bool(section.gyroscopic),
            ))
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

        if spec.ross_class == "MagneticBearingElement":
            data = spec.metadata.get("engineering_input", spec.metadata)
            required = ("g0_m", "i0_a", "ag_m2", "nw")
            missing = [key for key in required if key not in data]
            if missing:
                raise EngineeringError(f"AMB {spec.name!r} is missing engineering inputs: {', '.join(missing)}")
            speed_rpm = data.get("speed_rpm")
            frequency = None if speed_rpm is None else np.asarray(speed_rpm, dtype=float) * 2.0 * pi / 60.0
            return rs.MagneticBearingElement(
                n=mapping.node, n_link=n_link, tag=spec.name,
                g0=float(data["g0_m"]), i0=float(data["i0_a"]), ag=float(data["ag_m2"]), nw=float(data["nw"]),
                frequency=frequency, alpha=float(data.get("alpha_rad", pi / 8.0)),
                k_amp=float(data.get("k_amp", 1.0)), k_sense=float(data.get("k_sense", 1.0)),
                kp_pid=float(data.get("kp_pid", 0.0)), kd_pid=float(data.get("kd_pid", 0.0)),
                ki_pid=float(data.get("ki_pid", 0.0)), n_f=float(data.get("n_f_rad_s", 10000.0)),
                sensors_axis_rotation=float(data.get("sensors_axis_rotation_rad", pi / 4.0)),
            )

        if spec.ross_class != "BearingElement":
            raise EngineeringError(f"Bearing class {spec.ross_class} is not enabled in the qualified builder.")
        common = {"n": mapping.node, "tag": spec.name, "n_link": n_link}

        axial_rows = spec.metadata.get("axial_coefficients")
        if axial_rows:
            if n_link is not None:
                raise EngineeringError(
                    f"Axial bearing {spec.name!r} is attached to a lateral flexible-support link. "
                    "ROSS Studio will not transfer Kzz/Czz through that link until an explicit axial support Kzz/Czz contract exists."
                )
            try:
                rpm = np.asarray([float(row["rpm"]) for row in axial_rows], dtype=float)
                kzz = np.asarray([float(row["kzz"]) for row in axial_rows], dtype=float)
                czz = np.asarray([float(row["czz"]) for row in axial_rows], dtype=float)
            except (KeyError, TypeError, ValueError) as exc:
                raise EngineeringError(
                    f"Axial bearing {spec.name!r} has an invalid axial_coefficients table; expected rpm/kzz/czz rows."
                ) from exc
            if (
                rpm.ndim != 1
                or rpm.size == 0
                or rpm.size != kzz.size
                or rpm.size != czz.size
                or not np.all(np.isfinite(rpm))
                or not np.all(np.isfinite(kzz))
                or not np.all(np.isfinite(czz))
                or np.any(rpm <= 0.0)
                or (rpm.size > 1 and np.any(np.diff(rpm) <= 0.0))
            ):
                raise EngineeringError(
                    f"Axial bearing {spec.name!r} requires finite, positive, strictly increasing speed rows with finite Kzz/Czz."
                )
            frequency = rpm * 2.0 * pi / 60.0
            zeros = np.zeros_like(kzz)
            return rs.BearingElement(
                **common,
                kxx=zeros,
                kyy=zeros,
                kxy=zeros,
                kyx=zeros,
                cxx=zeros,
                cyy=zeros,
                cxy=zeros,
                cyx=zeros,
                kzz=kzz,
                czz=czz,
                frequency=frequency,
            )

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
            kyy=spec.kyy,
            kxy=spec.kxy,
            kyx=spec.kyx,
            cxx=spec.cxx,
            cyy=spec.cyy,
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
        coupling_by_interval: dict[tuple[float, float], Any] = {}
        for coupling in project.couplings:
            if coupling.length_mm <= 0:
                raise EngineeringError(
                    f"Coupling {coupling.name!r} still uses the legacy single-station contract. "
                    "Edit it and provide a positive length to create native ROSS CouplingElement nodes n and n+1."
                )
            key = (round(coupling.position_mm, 10), round(coupling.end_mm, 10))
            if key in coupling_by_interval:
                raise EngineeringError(f"More than one coupling occupies interval {key} mm.")
            coupling_by_interval[key] = coupling

        shaft_elements: list[Any] = []
        for element in plan:
            coupling = coupling_by_interval.get((round(element.x0_mm, 10), round(element.x1_mm, 10)))
            if coupling is not None:
                shaft_elements.append(
                    rs.CouplingElement(
                        m_l=coupling.left_mass_kg, m_r=coupling.right_mass_kg,
                        Ip_l=coupling.left_ip_kg_m2, Ip_r=coupling.right_ip_kg_m2,
                        Id_l=coupling.left_id_kg_m2, Id_r=coupling.right_id_kg_m2,
                        kt_x=coupling.kt_x_n_m, kt_y=coupling.kt_y_n_m, kt_z=coupling.kt_z_n_m,
                        kr_x=coupling.kr_x_n_m_rad, kr_y=coupling.kr_y_n_m_rad, kr_z=coupling.kr_z_n_m_rad,
                        ct_x=coupling.ct_x_n_s_m, ct_y=coupling.ct_y_n_s_m, ct_z=coupling.ct_z_n_s_m,
                        cr_x=coupling.cr_x_n_m_s_rad, cr_y=coupling.cr_y_n_m_s_rad, cr_z=coupling.cr_z_n_m_s_rad,
                        o_d=None if coupling.od_mm <= 0 else coupling.od_mm / 1000.0,
                        L=coupling.length_mm / 1000.0, n=element.n, tag=coupling.name,
                    )
                )
                continue
            shaft_elements.append(
                rs.ShaftElement(
                    L=element.length_mm / 1000.0, idl=element.id0_mm / 1000.0, odl=element.od0_mm / 1000.0,
                    idr=element.id1_mm / 1000.0, odr=element.od1_mm / 1000.0,
                    material=material_cache[element.material], n=element.n, tag=f"S{element.physical_section:02d}.{element.n:02d}",
                    shear_effects=element.shear_effects, rotary_inertia=element.rotary_inertia, gyroscopic=element.gyroscopic,
                )
            )

        unmatched = set(coupling_by_interval) - {(round(item.x0_mm, 10), round(item.x1_mm, 10)) for item in plan}
        if unmatched:
            joined = ", ".join(f"{a:g}-{b:g}" for a, b in sorted(unmatched))
            raise EngineeringError(
                "Native CouplingElement must replace exactly one adjacent shaft interval; "
                f"these coupling spans contain intermediate nodes or boundaries: {joined} mm."
            )

        support_by_bearing = {support.bearing_index: support for support in project.supports}
        support_link_nodes: dict[str, int] = {}
        bearings: list[Any] = []
        support_point_masses: list[Any] = []
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
                        kyy=support.kyy,
                        kxy=support.kxy,
                        kyx=support.kyx,
                        cxx=support.cxx,
                        cyy=support.cyy,
                        cxy=support.cxy,
                        cyx=support.cyx,
                        tag=f"{support.name} / ground",
                    )
                )
                support_point_masses.append(rs.PointMass(n=link_node, m=support.mass_kg, tag=f"{support.name} mass"))

        disks: list[Any] = []
        equivalent_disks: list[EquivalentDiskPlan] = []
        equivalent_point_masses: list[EquivalentPointMassPlan] = []
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

        # ROSS PointMass is a link/support element and its Rotor constructor expects
        # its node to belong to the support chain. Legacy [Concent] acts directly on
        # an ordinary shaft station and also carries Ix/Iy/Iz. Represent it as a
        # DiskElement subclass with independent principal inertias so static gravity,
        # M and G are all retained without nearest-node or support-node workarounds.
        concentrated_cls = concentrated_disk_class(rs)
        for mass in project.point_masses:
            mapping = self.map_position(project, mass.position_mm)
            if mapping.node is None:
                unresolved.append(mass.position_mm)
                continue
            disks.append(
                concentrated_cls(
                    mapping.node,
                    mass.mass_kg,
                    mass.ix_kg_m2,
                    mass.iy_kg_m2,
                    mass.iz_kg_m2,
                    tag=f"{mass.name} / shaft point mass",
                )
            )
            equivalent_point_masses.append(EquivalentPointMassPlan(
                name=mass.name,
                node=mapping.node,
                position_mm=mass.position_mm,
                mass_kg=mass.mass_kg,
                ix_kg_m2=mass.ix_kg_m2,
                iy_kg_m2=mass.iy_kg_m2,
                iz_kg_m2=mass.iz_kg_m2,
            ))

        unresolved = sorted(set(unresolved))
        if strict and unresolved:
            joined = ", ".join(f"{x:g}" for x in unresolved)
            raise EngineeringError(f"Strict ROSS build has unresolved axial positions: {joined} mm.")

        rotor = rs.Rotor(
            shaft_elements=shaft_elements,
            disk_elements=disks or None,
            bearing_elements=bearings or None,
            point_mass_elements=support_point_masses or None,
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
            equivalent_point_masses=equivalent_point_masses,
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
