from __future__ import annotations

from ...domain import CoefficientBearingSpec
from ...ross_ext.rotordin_legacy_bearing import make_rotordin_legacy_bearing_class
from ...ross_ext.rotordin_legacy_disk import make_rotordin_legacy_disk_class
from ...ross_ext.rotordin_legacy_rotor import make_rotordin_legacy_rotor_class
from ...ross_ext.rotordin_legacy_shaft import make_rotordin_legacy_shaft_class
from ...ross_ext.ump_rotor import make_ump_rotor_class
from ..coordinates import rpm_to_rad_s, rotordin_xz_to_ross_xy
from .builder import RossBuild, RossModelBuilder


class RotorDinLegacyModelBuilder(RossModelBuilder):
    """Build a deterministic RotorDin-compatibility rotor on top of ROSS.

    This migration/regression adapter keeps the verified topology but reproduces
    historical numerical contracts that differ from native ROSS:

    * shaft lateral M/K/G are the exact ``coemas/coerig/coegir`` matrices;
    * rigid disks use the RotorDin gyroscopic sign convention;
    * synchronous unbalance uses RotorDin's exact complex ``[-i,+1]`` forcing;
    * inline TABLE rows use RotorDin's canonical ``xx,xz,zx,zz`` order;
    * TABLE bearings use ``intlag`` local three-point quadratic interpolation;
    * the RotorDin default ``DIV/MXDIV`` rule subdivides the first largest gap.

    The mesh rule is parameterized because the current domain schema does not yet
    expose the legacy UI's ``s_div``/``s_mxdiv`` fields. For the W60 golden case
    they are explicitly 1 and 3. New projects continue to use
    ``RossModelBuilder`` and native ROSS physics.
    """

    def __init__(self, ross_module=None, *, min_divisions: int = 1, max_divisions: int = 3):
        super().__init__(ross_module=ross_module)
        self.min_divisions = int(min_divisions)
        self.max_divisions = int(max_divisions)
        if self.min_divisions < 1 or self.max_divisions < self.min_divisions:
            raise ValueError("RotorDin legacy DIV/MXDIV must satisfy 1 <= DIV <= MXDIV.")

    def _breakpoints(self, project) -> list[float]:
        """Reproduce W60 ``predad.f`` automatic subdivision for LDR=0."""
        physical = super()._breakpoints(project)
        if len(physical) < 2:
            return physical
        gaps = [physical[i + 1] - physical[i] for i in range(len(physical) - 1)]
        largest_index = max(range(len(gaps)), key=gaps.__getitem__)
        refined = [physical[0]]
        for i, gap in enumerate(gaps):
            divisions = self.max_divisions if i == largest_index else self.min_divisions
            x0 = physical[i]
            for j in range(1, divisions + 1):
                refined.append(self._p(x0 + gap * j / divisions))
        return sorted(set(refined))

    @staticmethod
    def _rotordin_table_coefficients(spec: CoefficientBearingSpec):
        """Decode inline RotorDin TABLE rows in the exact Fortran order.

        ``beatab`` reads each variable-bearing line as::

            rpm, Kxx, Kxz, Kzx, Kzz, Cxx, Cxz, Czx, Czz

        The generic legacy domain slots retain the historical grid-column names,
        where the third/fourth K and C values are named ``kzz/kzx`` and
        ``czz/czx``.  The compatibility builder restores the canonical Fortran
        order before x/z -> x/y mapping.
        """
        return dict(
            kxx=spec.kxx,
            kxz=spec.kxz,
            kzx=spec.kzz,
            kzz=spec.kzx,
            cxx=spec.cxx,
            cxz=spec.cxz,
            czx=spec.czz,
            czz=spec.czx,
        )

    def _build_bearing(self, spec, node_by_position, *, n_link_override: int | None = None):
        if not isinstance(spec, CoefficientBearingSpec) or spec.frequency_rpm is None:
            return super()._build_bearing(spec, node_by_position, n_link_override=n_link_override)

        table = self._rotordin_table_coefficients(spec)
        coeff = rotordin_xz_to_ross_xy(
            kxx=table["kxx"],
            kzz=table["kzz"],
            kxz=table["kxz"],
            kzx=table["kzx"],
            cxx=table["cxx"],
            czz=table["czz"],
            cxz=table["cxz"],
            czx=table["czx"],
        )
        n = node_by_position[self._p(spec.position_mm)]
        n_link = n_link_override
        if n_link is None and spec.n_link_position_mm is not None:
            n_link = node_by_position[self._p(spec.n_link_position_mm)]
        legacy_bearing_cls = make_rotordin_legacy_bearing_class(self.rs.BearingElement)
        return legacy_bearing_cls(
            n=n,
            kxx=coeff.kxx,
            kyy=coeff.kyy,
            kxy=coeff.kxy,
            kyx=coeff.kyx,
            cxx=coeff.cxx,
            cyy=coeff.cyy,
            cxy=coeff.cxy,
            cyx=coeff.cyx,
            frequency=rpm_to_rad_s(spec.frequency_rpm),
            n_link=n_link,
            tag=spec.tag or None,
        )

    def build(self, project) -> RossBuild:
        if "legacy_import" not in project.metadata:
            raise ValueError("RotorDinLegacyModelBuilder requires a legacy-imported RotorProject.")

        # Polymorphic _breakpoints() and _build_bearing() mean this pass already
        # has RotorDin mesh, TABLE order and TABLE interpolation. Shaft, disk and
        # rotor forcing contracts are replaced below; the production builder stays
        # native ROSS.
        native = super().build(project)

        legacy_shaft_cls = make_rotordin_legacy_shaft_class(self.rs.ShaftElement)
        shaft_elements = []
        for source in native.shaft_elements:
            shaft_elements.append(
                legacy_shaft_cls(
                    L=source.L,
                    idl=source.idl,
                    odl=source.odl,
                    idr=source.idr,
                    odr=source.odr,
                    material=source.material,
                    n=source.n,
                    axial_force=getattr(source, "axial_force", 0.0),
                    torque=getattr(source, "torque", 0.0),
                    shear_effects=True,
                    rotary_inertia=getattr(source, "rotary_inertia", True),
                    gyroscopic=getattr(source, "gyroscopic", True),
                    tag=getattr(source, "tag", None),
                    alpha=getattr(source, "alpha", 0.0),
                    beta=getattr(source, "beta", 0.0),
                    gyroscopic_factor=1.0,
                )
            )

        legacy_disk_cls = make_rotordin_legacy_disk_class(self.rs.DiskElement)
        disk_elements = [
            legacy_disk_cls(
                n=source.n,
                m=source.m,
                Id=source.Id,
                Ip=source.Ip,
                tag=getattr(source, "tag", None),
                scale_factor=getattr(source, "scale_factor", 1.0),
                color=getattr(source, "color", "Firebrick"),
            )
            for source in native.disk_elements
        ]

        rotor_kwargs = self._rotor_kwargs(
            shaft_elements,
            disk_elements,
            native.bearing_elements,
            native.point_mass_elements,
            native.support_mass_elements,
        )
        legacy_rotor_cls = make_rotordin_legacy_rotor_class(self.rs.Rotor)
        base_rotor = legacy_rotor_cls(**rotor_kwargs)

        if project.ump_regions:
            ump_rotor_cls = make_ump_rotor_class(legacy_rotor_cls)
            rotor = ump_rotor_cls(
                **rotor_kwargs,
                ump_regions=project.ump_regions,
                ump_element_spans=native.ump_element_spans,
            )
            ump_contributions = list(rotor.ump_contributions)
            ump_audit = dict(rotor.ump_audit)
        else:
            rotor = base_rotor
            ump_contributions = []
            ump_audit = {"active": False, "formulations": [], "element_contributions": []}

        physical_points = super()._breakpoints(project)
        refined_points = self._breakpoints(project)
        inserted_points = [value for value in refined_points if value not in set(physical_points)]
        ump_audit = dict(ump_audit)
        ump_audit["shaft_matrix_formulation"] = "rotordin_coemas_coerig_coegir"
        ump_audit["rigid_disk_gyroscopic_sign"] = "rotordin_matrix_sign"
        ump_audit["unbalance_complex_force"] = "rotordin_Fx_minus_i_Fz_plus_1"
        ump_audit["bearing_table_source_order"] = "rpm_Kxx_Kxz_Kzx_Kzz_Cxx_Cxz_Czx_Czz"
        ump_audit["bearing_table_interpolation"] = "rotordin_intlag_local_quadratic"
        ump_audit["legacy_mesh"] = {
            "rule": "predad_first_largest_gap_DIV_MXDIV",
            "min_divisions": self.min_divisions,
            "max_divisions": self.max_divisions,
            "physical_station_count": len(physical_points),
            "refined_station_count": len(refined_points),
            "inserted_positions_mm": inserted_points,
        }

        return RossBuild(
            rotor=rotor,
            base_rotor=base_rotor,
            node_by_position_mm=native.node_by_position_mm,
            shaft_elements=shaft_elements,
            disk_elements=disk_elements,
            bearing_elements=native.bearing_elements,
            point_mass_elements=native.point_mass_elements,
            support_mass_elements=native.support_mass_elements,
            support_link_node_by_bearing=native.support_link_node_by_bearing,
            ump_element_spans=native.ump_element_spans,
            ump_contributions=ump_contributions,
            ump_audit=ump_audit,
        )


__all__ = ["RotorDinLegacyModelBuilder"]
