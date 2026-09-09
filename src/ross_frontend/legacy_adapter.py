from __future__ import annotations

from .domain import (
    AnalysisRequest,
    CoefficientBearingSpec,
    MaterialSpec,
    PointMassSpec,
    RotorProject,
    ShaftSectionSpec,
)


class LegacyUnsupportedError(RuntimeError):
    """Feature from RotorDin that has not yet received a verified ROSS mapping."""


def from_rotordin_project(project) -> RotorProject:
    """Convert the verified common subset of the old RotorDin UI model.

    The adapter is deliberately conservative: it refuses features whose physical
    equivalence has not been established instead of silently approximating them.
    """
    cfg = project.configuration
    materials = [
        MaterialSpec(
            name="RotorDinSteel",
            density_kg_m3=cfg.density_kg_m3,
            young_pa=cfg.young_pa,
            poisson=cfg.poisson,
        )
    ]
    shaft = []
    for i, seg in enumerate(project.segments, start=1):
        if getattr(seg, "is_ribbed", False):
            raise LegacyUnsupportedError(
                "RotorDin ribbed shaft sections require a dedicated verified equivalence model before ROSS migration."
            )
        shaft.append(
            ShaftSectionSpec(
                length_mm=seg.length_mm,
                outer_diameter_left_mm=seg.diameter_mm,
                inner_diameter_left_mm=seg.inner_diameter_mm,
                outer_diameter_right_mm=(
                    seg.final_diameter_mm if getattr(seg, "is_conical", False) else seg.diameter_mm
                ),
                inner_diameter_right_mm=seg.inner_diameter_mm,
                material="RotorDinSteel",
                tag=f"section_{i}",
            )
        )

    bearings = []
    for i, bearing in enumerate(project.bearings, start=1):
        if bearing.file.strip():
            raise LegacyUnsupportedError(
                "RotorDin COEF/TABLE bearing files are not migrated implicitly; import them into a ROSS speed-dependent bearing first."
            )
        if bearing.support_enabled:
            raise LegacyUnsupportedError(
                "RotorDin bearing-support chains require the support/n_link migration gate before use with ROSS."
            )
        bearings.append(
            CoefficientBearingSpec(
                position_mm=bearing.position_mm,
                kxx=bearing.kxx,
                kzz=bearing.kzz,
                kxz=bearing.kxz,
                kzx=bearing.kzx,
                cxx=bearing.cxx,
                czz=bearing.czz,
                cxz=bearing.cxz,
                czx=bearing.czx,
                tag=f"bearing_{i}",
            )
        )

    if project.masses:
        raise LegacyUnsupportedError(
            "Distributed RotorDin masses are not converted to ROSS point masses because that would change inertia distribution."
        )
    point_masses = []
    for i, mass in enumerate(project.concentrated_masses, start=1):
        if any(abs(v) > 0 for v in (mass.ix_kg_m2, mass.iy_kg_m2, mass.iz_kg_m2)):
            raise LegacyUnsupportedError(
                "Concentrated masses with rotational inertia need an explicit axis/inertia mapping before ROSS migration."
            )
        point_masses.append(PointMassSpec(position_mm=mass.xi_mm, mass_kg=mass.kg, tag=f"mass_{i}"))

    if project.forces or project.probes:
        raise LegacyUnsupportedError(
            "RotorDin force/probe definitions will be migrated with the response-analysis phase; no silent mapping is performed."
        )

    analysis = AnalysisRequest(
        modal=project.analyses.modes,
        critical_speed=project.analyses.auto,
        campbell=project.analyses.campbell or project.analyses.log_decrement,
        static=False,
        modal_speed_rpm=cfg.modal_rpm,
        campbell_initial_rpm=max(0.0, project.identification.rpm_initial),
        campbell_final_rpm=max(
            project.identification.rpm_final,
            project.identification.rpm_initial + cfg.campbell_step_rpm,
        ),
        campbell_step_rpm=cfg.campbell_step_rpm,
        modes=max(1, cfg.critical_speed_count),
    )
    return RotorProject(
        reference=project.identification.reference,
        materials=materials,
        shaft=shaft,
        point_masses=point_masses,
        bearings=bearings,
        analyses=analysis,
        metadata={"source": "rotordin_frontend_v1"},
    )
