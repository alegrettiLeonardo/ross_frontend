from __future__ import annotations

from ..domain import AnalysisRequest, CoefficientBearingSpec, DiskSpec, MaterialSpec, RotorProject, ShaftSectionSpec


def sample_project() -> RotorProject:
    steel = MaterialSpec(name="Steel (AISI 4140)", density_kg_m3=7850.0, young_pa=2.07e11, poisson=0.30)
    shaft = [
        ShaftSectionSpec(200, 50, 0, 50, 0, steel.name, tag="1"),
        ShaftSectionSpec(150, 50, 0, 60, 0, steel.name, tag="2"),
        ShaftSectionSpec(250, 60, 0, 60, 0, steel.name, tag="3"),
        ShaftSectionSpec(250, 60, 0, 50, 0, steel.name, tag="4"),
        ShaftSectionSpec(200, 50, 0, 50, 0, steel.name, tag="5"),
        ShaftSectionSpec(150, 50, 0, 50, 0, steel.name, tag="6"),
    ]
    disks = [
        DiskSpec(position_mm=400, mass_kg=58.0, diametral_inertia_kg_m2=0.85, polar_inertia_kg_m2=1.62, tag="Disk 1"),
        DiskSpec(position_mm=820, mass_kg=61.0, diametral_inertia_kg_m2=0.90, polar_inertia_kg_m2=1.70, tag="Disk 2"),
    ]
    bearings = [
        CoefficientBearingSpec(position_mm=80, kxx=2.8e7, kzz=2.7e7, cxx=1.1e5, czz=1.05e5, tag="Bearing 1"),
        CoefficientBearingSpec(position_mm=1120, kxx=2.8e7, kzz=2.7e7, cxx=1.1e5, czz=1.05e5, tag="Bearing 2"),
    ]
    analyses = AnalysisRequest(
        static=True, modal=True, critical_speed=True, campbell=True,
        modal_speed_rpm=1800.0, campbell_initial_rpm=0.0, campbell_final_rpm=10000.0,
        campbell_step_rpm=500.0, modes=6,
    )
    return RotorProject(
        reference="WGM20", materials=[steel], shaft=shaft, disks=disks, bearings=bearings, analyses=analyses,
        metadata={
            "description": "Wind generator main rotor\n(20 MW class)",
            "created": "Apr 25, 2025  10:24",
            "last_modified": "Apr 25, 2025  14:17",
            "rotor_speed_rpm": 1800.0,
            "display_total_mass_kg": 286.4,
        },
    )
