from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any

from ...domain import (
    BallBearingSpec,
    CoefficientBearingSpec,
    CylindricalBearingSpec,
    PlainJournalBearingSpec,
    RollerBearingSpec,
    RotorProject,
    ShaftSectionSpec,
    TiltingPadBearingSpec,
)
from ...ross_ext.ump import make_ump_shaft_element_class
from ..coordinates import rpm_to_rad_s, rotordin_xz_to_ross_xy


class RossDependencyError(RuntimeError):
    pass


class RossBuildError(RuntimeError):
    pass


def load_ross():
    try:
        import ross as rs
    except ImportError as exc:
        raise RossDependencyError(
            "ROSS is unavailable. Initialize vendor/ross or install ross-rotordynamics==2.3.0."
        ) from exc
    return rs


@dataclass(slots=True)
class RossBuild:
    rotor: Any
    node_by_position_mm: dict[float, int]
    shaft_elements: list[Any]
    disk_elements: list[Any]
    bearing_elements: list[Any]
    point_mass_elements: list[Any]
    support_link_node_by_bearing: dict[int, int]
    ump_shaft_elements: list[Any]


class RossModelBuilder:
    """Translate the frontend domain model into native ROSS objects.

    Components in ROSS are attached to nodes. The builder therefore creates a
    breakpoint at every shaft boundary and component position. Conical geometry
    is re-interpolated at those breakpoints. Flexible bearing supports are
    realized as bearings in series using external ``n_link`` housing nodes:

        shaft node -- bearing K/C -- housing mass -- support K/C -- ground

    Linearized UMP regions are represented as distributed negative radial
    stiffness.  UMP boundaries are inserted as shaft breakpoints so an element
    is either completely inside or completely outside each active span.
    """

    _POS_DIGITS = 9

    def __init__(self, ross_module=None):
        self.rs = ross_module or load_ross()

    @classmethod
    def _p(cls, value: float) -> float:
        return round(float(value), cls._POS_DIGITS)

    @staticmethod
    def _material_name(name: str) -> str:
        return "_".join(name.strip().split()) or "Material"

    @staticmethod
    def _interp(section: ShaftSectionSpec, ratio: float) -> tuple[float, float]:
        od = section.outer_diameter_left_mm + (section.odr_mm - section.outer_diameter_left_mm) * ratio
        inner = section.inner_diameter_left_mm + (section.idr_mm - section.inner_diameter_left_mm) * ratio
        return od, inner

    def _section_ranges(self, project: RotorProject):
        x0 = 0.0
        out = []
        for section in project.shaft:
            x1 = x0 + section.length_mm
            out.append((self._p(x0), self._p(x1), section))
            x0 = x1
        return out

    def _find_section(self, ranges, x_mid: float):
        for x0, x1, section in ranges:
            if x0 - 1e-8 <= x_mid <= x1 + 1e-8:
                return x0, x1, section
        raise RossBuildError(f"Could not locate shaft section at x={x_mid:g} mm.")

    @staticmethod
    def _ump_stiffness_at(project: RotorProject, x_mid_mm: float) -> float:
        return sum(
            region.stiffness_per_length_n_m2
            for region in project.ump_regions
            if region.start_mm - 1e-8 <= x_mid_mm <= region.end_mm + 1e-8
        )

    def _breakpoints(self, project: RotorProject) -> list[float]:
        points = {self._p(0.0), self._p(project.shaft_length_mm)}
        x = 0.0
        for section in project.shaft:
            x += section.length_mm
            points.add(self._p(x))
        for item in [*project.disks, *project.point_masses, *project.bearings, *project.unbalances, *project.probes]:
            points.add(self._p(item.position_mm))
            linked = getattr(item, "n_link_position_mm", None)
            if linked is not None:
                points.add(self._p(linked))
        for region in project.ump_regions:
            points.add(self._p(region.start_mm))
            points.add(self._p(region.end_mm))
        return sorted(points)

    def build(self, project: RotorProject) -> RossBuild:
        project.validate()
        rs = self.rs

        material_by_name: dict[str, Any] = {}
        for spec in project.materials:
            material_by_name[spec.name] = rs.Material(
                name=self._material_name(spec.name),
                rho=spec.density_kg_m3,
                E=spec.young_pa,
                Poisson=spec.poisson,
            )

        points = self._breakpoints(project)
        node_by_position = {p: i for i, p in enumerate(points)}
        ranges = self._section_ranges(project)
        shaft_elements: list[Any] = []
        ump_shaft_elements: list[Any] = []
        ump_shaft_cls = make_ump_shaft_element_class(rs.ShaftElement)

        for n, (xa, xb) in enumerate(zip(points, points[1:])):
            if xb <= xa:
                continue
            x_mid = (xa + xb) / 2.0
            section_x0, _section_x1, section = self._find_section(ranges, x_mid)
            left_ratio = (xa - section_x0) / section.length_mm
            right_ratio = (xb - section_x0) / section.length_mm
            odl, idl = self._interp(section, left_ratio)
            odr, idr = self._interp(section, right_ratio)
            ump_k = self._ump_stiffness_at(project, x_mid)
            shaft_cls = ump_shaft_cls if ump_k > 0.0 else rs.ShaftElement
            kwargs = dict(
                L=(xb - xa) / 1000.0,
                idl=idl / 1000.0,
                odl=odl / 1000.0,
                idr=idr / 1000.0,
                odr=odr / 1000.0,
                material=material_by_name[section.material],
                n=n,
                shear_effects=section.shear_effects,
                rotary_inertia=section.rotary_inertia,
                gyroscopic=section.gyroscopic,
                tag=section.tag or None,
            )
            if ump_k > 0.0:
                kwargs["ump_stiffness_per_length_n_m2"] = ump_k
            element = shaft_cls(**kwargs)
            shaft_elements.append(element)
            if ump_k > 0.0:
                ump_shaft_elements.append(element)

        disk_elements = [
            rs.DiskElement(
                n=node_by_position[self._p(d.position_mm)],
                m=d.mass_kg,
                Id=d.diametral_inertia_kg_m2,
                Ip=d.polar_inertia_kg_m2,
                tag=d.tag or None,
            )
            for d in project.disks
        ]
        point_mass_elements = [
            rs.PointMass(
                n=node_by_position[self._p(m.position_mm)],
                m=m.mass_kg,
                tag=m.tag or None,
            )
            for m in project.point_masses
        ]

        support_by_bearing = {support.bearing_index: support for support in project.supports}
        support_link_node_by_bearing: dict[int, int] = {}
        bearing_elements: list[Any] = []
        next_link_node = len(points)
        for index, bearing in enumerate(project.bearings):
            support = support_by_bearing.get(index)
            if support is None:
                bearing_elements.append(self._build_bearing(bearing, node_by_position))
                continue
            if not isinstance(bearing, CoefficientBearingSpec):
                raise RossBuildError(
                    "Flexible support realization is currently verified for coefficient/table bearings only."
                )
            link_node = next_link_node
            next_link_node += 1
            support_link_node_by_bearing[index] = link_node
            bearing_elements.append(self._build_bearing(bearing, node_by_position, n_link_override=link_node))
            support_coeff = rotordin_xz_to_ross_xy(
                kxx=support.kxx,
                kzz=support.kzz,
                kxz=support.kxz,
                kzx=support.kzx,
                cxx=support.cxx,
                czz=support.czz,
                cxz=support.cxz,
                czx=support.czx,
            )
            bearing_elements.append(
                rs.BearingElement(
                    n=link_node,
                    kxx=support_coeff.kxx,
                    kyy=support_coeff.kyy,
                    kxy=support_coeff.kxy,
                    kyx=support_coeff.kyx,
                    cxx=support_coeff.cxx,
                    cyy=support_coeff.cyy,
                    cxy=support_coeff.cxy,
                    cyx=support_coeff.cyx,
                    tag=support.tag or f"Support {index + 1}",
                )
            )
            point_mass_elements.append(
                rs.PointMass(
                    n=link_node,
                    m=support.mass_kg,
                    tag=f"{support.tag or f'Support {index + 1}'} housing mass",
                )
            )

        rotor = rs.Rotor(
            shaft_elements=shaft_elements,
            disk_elements=disk_elements,
            bearing_elements=bearing_elements,
            point_mass_elements=point_mass_elements,
        )
        return RossBuild(
            rotor,
            node_by_position,
            shaft_elements,
            disk_elements,
            bearing_elements,
            point_mass_elements,
            support_link_node_by_bearing,
            ump_shaft_elements,
        )

    def _build_bearing(self, spec, node_by_position, *, n_link_override: int | None = None):
        rs = self.rs
        n = node_by_position[self._p(spec.position_mm)]
        tag = spec.tag or None

        if isinstance(spec, CoefficientBearingSpec):
            coeff = rotordin_xz_to_ross_xy(
                kxx=spec.kxx,
                kzz=spec.kzz,
                kxz=spec.kxz,
                kzx=spec.kzx,
                cxx=spec.cxx,
                czz=spec.czz,
                cxz=spec.cxz,
                czx=spec.czx,
            )
            n_link = n_link_override
            if n_link is None and spec.n_link_position_mm is not None:
                n_link = node_by_position[self._p(spec.n_link_position_mm)]
            return rs.BearingElement(
                n=n,
                kxx=coeff.kxx,
                kyy=coeff.kyy,
                kxy=coeff.kxy,
                kyx=coeff.kyx,
                cxx=coeff.cxx,
                cyy=coeff.cyy,
                cxy=coeff.cxy,
                cyx=coeff.cyx,
                frequency=None if spec.frequency_rpm is None else rpm_to_rad_s(spec.frequency_rpm),
                n_link=n_link,
                tag=tag,
            )

        if n_link_override is not None:
            raise RossBuildError("n_link override is not enabled for this bearing family yet.")

        if isinstance(spec, BallBearingSpec):
            return rs.BallBearingElement(
                n=n,
                n_balls=spec.n_balls,
                d_balls=spec.ball_diameter_mm / 1000.0,
                fs=spec.static_load_n,
                alpha=spec.contact_angle_deg * pi / 180.0,
                cxx=spec.cxx,
                cyy=spec.cyy,
                tag=tag,
            )

        if isinstance(spec, RollerBearingSpec):
            return rs.RollerBearingElement(
                n=n,
                n_rollers=spec.n_rollers,
                l_rollers=spec.roller_length_mm / 1000.0,
                fs=spec.static_load_n,
                alpha=spec.contact_angle_deg * pi / 180.0,
                cxx=spec.cxx,
                cyy=spec.cyy,
                tag=tag,
            )

        if isinstance(spec, CylindricalBearingSpec):
            return rs.CylindricalBearing(
                n=n,
                speed=rpm_to_rad_s(spec.speed_rpm),
                weight=spec.weight_n,
                bearing_length=spec.bearing_length_mm / 1000.0,
                journal_diameter=spec.journal_diameter_mm / 1000.0,
                radial_clearance=spec.radial_clearance_mm / 1000.0,
                oil_viscosity=spec.oil_viscosity_pa_s,
                tag=tag,
            )

        if isinstance(spec, PlainJournalBearingSpec):
            kwargs = dict(
                n=n,
                pad_axial_length=spec.pad_axial_length_mm / 1000.0,
                journal_diameter=spec.journal_diameter_mm / 1000.0,
                radial_clearance=spec.radial_clearance_mm / 1000.0,
                n_pads=spec.n_pads,
                pad_arc=spec.pad_arc_deg * pi / 180.0,
                preload=spec.preload,
                oil_supply_temperature=spec.oil_supply_temperature_c + 273.15,
                frequency=rpm_to_rad_s(spec.frequency_rpm),
                fxs_load=spec.load_x_n,
                fys_load=spec.load_y_n,
                lubricant=spec.lubricant,
                oil_supply_pressure=spec.oil_supply_pressure_pa,
                equilibrium_type=spec.equilibrium_type,
                thermal_type=spec.thermal_type,
                total_ex_film=spec.film_elements_circumferential,
                total_ez_film=spec.film_elements_axial,
                tag=tag,
            )
            if spec.oil_flow_l_min is not None:
                kwargs["oil_flow_v"] = spec.oil_flow_l_min / 1000.0 / 60.0
            return rs.PlainJournal(**kwargs)

        if isinstance(spec, TiltingPadBearingSpec):
            kwargs = dict(
                n=n,
                journal_diameter=spec.journal_diameter_mm / 1000.0,
                radial_clearance=spec.radial_clearance_mm / 1000.0,
                pad_axial_length=spec.pad_axial_length_mm / 1000.0,
                pad_thickness=spec.pad_thickness_mm / 1000.0,
                pad_arc=spec.pad_arc_deg * pi / 180.0,
                pivot_angle=[v * pi / 180.0 for v in spec.pivot_angle_deg],
                frequency=rpm_to_rad_s(spec.frequency_rpm),
                oil_supply_temperature=spec.oil_supply_temperature_c + 273.15,
                lubricant=spec.lubricant,
                preload=spec.preload,
                offset=spec.offset,
                fxs_load=spec.load_x_n,
                fys_load=spec.load_y_n,
                oil_supply_pressure=spec.oil_supply_pressure_pa,
                equilibrium_type=spec.equilibrium_type,
                thermal_type=spec.thermal_type,
                total_ex_film=spec.film_elements_circumferential,
                total_ez_film=spec.film_elements_axial,
                total_ey_pad=spec.pad_elements_radial,
                tag=tag,
            )
            if spec.oil_flow_l_min is not None:
                kwargs["oil_flow_v"] = spec.oil_flow_l_min / 1000.0 / 60.0
            return rs.TiltingPad(**kwargs)

        raise RossBuildError(f"Unsupported bearing spec: {type(spec).__name__}")
