from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi

import numpy as np

from ..domain import BearingSpec, MaterialSpec, RotorProject, ShaftSection
from .builder import MultiRotorBuilder
from .domain import GearConnection, GearModel, GearSpec, METHOD_QUALIFICATION, MultiRotorProject


FRISWELL_HZ = np.array([11.641, 12.284, 17.268, 18.458, 23.956, 37.681, 49.889, 50.861, 56.248, 57.752, 59.188, 63.113, 74.203], dtype=float)


@dataclass(slots=True)
class MultiRotorQualification:
    status: str
    ross_version: str
    friswell_hz: list[float]
    ross_hz: list[float]
    max_error_percent: float
    speed_mapping_pass: bool
    two_shaft_native_class: str
    three_shaft_native_class: str
    three_shaft_modal_finite: bool
    tvms_native_class: str
    tvms_stiffness_positive: bool
    blocked_methods: list[str]
    experimental_methods: list[str]
    qualified_methods: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _small_rotor(name: str) -> RotorProject:
    material = MaterialSpec(name="Steel", density_kg_m3=7800.0, young_pa=207e9, poisson=0.3)
    return RotorProject(name=name, materials={"Steel": material}, shaft_sections=[ShaftSection(1,100.0,20.0,material="Steel"), ShaftSection(2,100.0,20.0,material="Steel")], bearings=[BearingSpec(f"{name} B0",0.0,kxx=2e7,kyy=2e7,cxx=2e3,cyy=2e3), BearingSpec(f"{name} B1",200.0,kxx=2e7,kyy=2e7,cxx=2e3,cyy=2e3)])


def three_shaft_project(*, tvms: bool = False) -> MultiRotorProject:
    rotors = [_small_rotor(f"R{i}") for i in range(3)]
    model = GearModel.TVMS if tvms else GearModel.SIMPLE
    common = dict(model=model, pressure_angle_deg=20.0)
    gear_kwargs = dict(material_name="Steel", width_m=0.01, bore_diameter_m=0.01, module_m=0.001) if tvms else dict(mass_kg=0.5, id_kg_m2=1e-4, ip_kg_m2=2e-4)
    gears = [GearSpec("G0",0,100.0,n_teeth=40,pitch_diameter_m=0.04,**common,**gear_kwargs), GearSpec("G1a",1,0.0,n_teeth=20,pitch_diameter_m=0.02,**common,**gear_kwargs), GearSpec("G1b",1,200.0,n_teeth=30,pitch_diameter_m=0.03,**common,**gear_kwargs), GearSpec("G2",2,0.0,n_teeth=15,pitch_diameter_m=0.015,**common,**gear_kwargs)]
    stiffness = None if tvms else 5e7
    connections = [GearConnection(0,1,0,1,gear_mesh_stiffness=stiffness,position="above"), GearConnection(1,2,2,3,gear_mesh_stiffness=stiffness,position="below")]
    return MultiRotorProject("Three shaft qualification", rotors, gears, connections)


def run_multirotor_qualification() -> MultiRotorQualification:
    import ross as rs
    from ross.multi_rotor.multi_rotor import two_shaft_rotor_example
    tutorial = two_shaft_rotor_example()
    speed = 1500.0 * 2.0 * pi / 60.0
    modal = tutorial.run_modal(speed=speed, num_modes=26)
    ross_hz = (np.asarray(modal.wd, dtype=float) / (2.0 * pi))[:13]
    max_error = float(np.max(np.abs(ross_hz - FRISWELL_HZ) / FRISWELL_HZ * 100.0))
    omega = 123.456
    driving_speed = float(tutorial.check_speed(tutorial.nodes[0], omega)); driven_speed = float(tutorial.check_speed(tutorial.driven_nodes[0], omega))
    speed_mapping_pass = bool(np.isclose(driving_speed, omega, rtol=0, atol=1e-12) and np.isclose(driven_speed, -tutorial.mesh.gear_ratio * omega, rtol=1e-12, atol=1e-12))
    three = MultiRotorBuilder().build(three_shaft_project()); three_modal = three.rotor.run_modal(speed=0.0, num_modes=8); three_finite = bool(np.all(np.isfinite(np.asarray(three_modal.wd, dtype=float))))
    tvms_two = three_shaft_project(tvms=True); tvms_two.rotors = tvms_two.rotors[:2]; tvms_two.gears = tvms_two.gears[:2]; tvms_two.connections = tvms_two.connections[:1]; tvms_two.name = "TVMS qualification"; tvms = MultiRotorBuilder().build(tvms_two)
    blocked = sorted(k for k,v in METHOD_QUALIFICATION.items() if v.value == "BLOCKED"); experimental = sorted(k for k,v in METHOD_QUALIFICATION.items() if v.value == "EXPERIMENTAL"); qualified = sorted(k for k,v in METHOD_QUALIFICATION.items() if v.value == "QUALIFIED")
    ok = rs.__version__ == "2.3.0" and max_error < 0.01 and speed_mapping_pass and three.rotor.__class__.__name__ == "MultiRotor" and three_finite and tvms.rotor.__class__.__name__ == "MultiRotor" and tvms.rotor.mesh.stiffness > 0 and blocked == ["level1","static","ucs"] and experimental == ["critical_speed"]
    return MultiRotorQualification("PASS" if ok else "FAIL", rs.__version__, FRISWELL_HZ.tolist(), [float(v) for v in ross_hz], max_error, speed_mapping_pass, tutorial.__class__.__name__, three.rotor.__class__.__name__, three_finite, tvms.rotor.mesh.driving_gear.__class__.__name__, bool(tvms.rotor.mesh.stiffness > 0), blocked, experimental, qualified)


__all__ = ["FRISWELL_HZ", "MultiRotorQualification", "run_multirotor_qualification", "three_shaft_project"]
