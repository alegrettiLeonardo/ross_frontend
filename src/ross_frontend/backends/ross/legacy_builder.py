from __future__ import annotations

from .builder import RossBuild, RossModelBuilder
from ...ross_ext.ump_rotor import make_ump_rotor_class
from ...ross_ext.rotordin_legacy_shaft import make_rotordin_legacy_shaft_class


class RotorDinLegacyModelBuilder(RossModelBuilder):
    """Build a deterministic RotorDin-compatibility rotor on top of ROSS.

    The normal ``RossModelBuilder`` remains the production physical ROSS path.
    This builder is a regression/migration adapter: it preserves the already
    verified disk, bearing, support, point-mass and UMP topology, but replaces
    each cylindrical shaft element by the exact RotorDin lateral M/K/G element.
    """

    def build(self, project) -> RossBuild:
        if "legacy_import" not in project.metadata:
            raise ValueError("RotorDinLegacyModelBuilder requires a legacy-imported RotorProject.")

        native = super().build(project)
        legacy_cls = make_rotordin_legacy_shaft_class(self.rs.ShaftElement)
        shaft_elements = []
        for source in native.shaft_elements:
            shaft_elements.append(
                legacy_cls(
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

        rotor_kwargs = self._rotor_kwargs(
            shaft_elements,
            native.disk_elements,
            native.bearing_elements,
            native.point_mass_elements,
            native.support_mass_elements,
        )
        base_rotor = self.rs.Rotor(**rotor_kwargs)

        if project.ump_regions:
            ump_rotor_cls = make_ump_rotor_class(self.rs.Rotor)
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

        ump_audit = dict(ump_audit)
        ump_audit["shaft_matrix_formulation"] = "rotordin_coemas_coerig_coegir"

        return RossBuild(
            rotor=rotor,
            base_rotor=base_rotor,
            node_by_position_mm=native.node_by_position_mm,
            shaft_elements=shaft_elements,
            disk_elements=native.disk_elements,
            bearing_elements=native.bearing_elements,
            point_mass_elements=native.point_mass_elements,
            support_mass_elements=native.support_mass_elements,
            support_link_node_by_bearing=native.support_link_node_by_bearing,
            ump_element_spans=native.ump_element_spans,
            ump_contributions=ump_contributions,
            ump_audit=ump_audit,
        )


__all__ = ["RotorDinLegacyModelBuilder"]
