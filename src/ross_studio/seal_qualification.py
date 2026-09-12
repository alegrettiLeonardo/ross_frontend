from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import pi
from pathlib import Path
import tempfile

import numpy as np

from .domain import EngineeringError, SealSpec
from .models import ProjectModel, load_reference_project_model
from .project_io import load_project, save_project
from .ross_backend import RossModelBuilder
from .seal_models import (
    HolePatternSealSpec,
    HolePatternStageSpec,
    HybridSealSpec,
    LabyrinthSealSpec,
    LabyrinthStageSpec,
)
from .seal_studio import SealCalculationPreview, SealStudioService


@dataclass(slots=True)
class SealQualification:
    status: str
    ross_version: str
    prospective_exact_node_pass: bool
    direct_kc_parity_pass: bool
    labyrinth_native_class: str
    labyrinth_kxx_n_m: float
    labyrinth_kxy_n_m: float
    labyrinth_cxx_n_s_m: float
    labyrinth_cxy_n_s_m: float
    labyrinth_leakage_kg_s: float
    labyrinth_regression_pass: bool
    labyrinth_builder_parity_pass: bool
    labyrinth_k_plot_traces: int
    labyrinth_pressure_plot_traces: int
    hole_pattern_native_class: str
    hole_pattern_kxx_n_m: float
    hole_pattern_kxy_n_m: float
    hole_pattern_cxx_n_s_m: float
    hole_pattern_cxy_n_s_m: float
    hole_pattern_leakage_kg_s: float
    hole_pattern_regression_pass: bool
    hole_pattern_builder_parity_pass: bool
    hole_pattern_k_plot_traces: int
    hole_pattern_pressure_plot_traces: int
    hybrid_native_class: str
    hybrid_interface_pressure_pa: float
    hybrid_iterations: int
    hybrid_final_convergence: float
    hybrid_leakage_kg_s: float
    hybrid_kxx_n_m: float
    hybrid_kxy_n_m: float
    hybrid_cxx_n_s_m: float
    hybrid_cxy_n_s_m: float
    hybrid_regression_pass: bool
    hybrid_builder_parity_pass: bool
    hybrid_convergence_plot_traces: int
    persistence_roundtrip_pass: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _reference() -> tuple[ProjectModel, object]:
    model = load_reference_project_model()
    if model.engineering is None:
        raise EngineeringError("Reference OP-W60 project has no engineering RotorProject.")
    return model, model.engineering


def _station(project) -> float:
    # Deliberately not an existing engineering station: Seal Studio must calculate
    # against the prospective exact-node topology that Apply will create.
    x = float(project.total_length_mm) * 0.371234567
    existing = set(project.topology_split_positions_mm())
    if any(abs(value - x) <= 1e-7 for value in existing):
        x += min(0.1234567, 1e-4 * project.total_length_mm)
    return x


def _lateral_parity(native, assembled, rpm: float) -> bool:
    omega = rpm * 2.0 * pi / 60.0
    return bool(
        np.allclose(native.K(omega)[:2, :2], assembled.K(omega)[:2, :2], rtol=1e-10, atol=1e-6)
        and np.allclose(native.C(omega)[:2, :2], assembled.C(omega)[:2, :2], rtol=1e-10, atol=1e-9)
        and np.allclose(native.M(omega)[:2, :2], assembled.M(omega)[:2, :2], rtol=1e-10, atol=1e-12)
    )


def _assembled_seal(rs, project, preview: SealCalculationPreview):
    candidate = deepcopy(project)
    candidate.seals.append(deepcopy(preview.prepared))
    built = RossModelBuilder(rs).build(candidate, strict=True)
    return next(element for element in built.rotor.bearing_elements if getattr(element, "tag", None) == preview.prepared.name)


def _trace_count(figure) -> int:
    return len(getattr(figure, "data", ()))


def run_seal_qualification() -> SealQualification:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise EngineeringError(f"Seal Studio 0.25 requires ROSS 2.3.0; received {rs.__version__}.")

    model, project = _reference()
    service = SealStudioService(rs)
    x = _station(project)

    direct = SealSpec(
        "Seal 0.25 direct",
        x,
        1.0e6,
        1.2e6,
        2.0e3,
        2.2e3,
        1.0e5,
        -1.0e5,
        50.0,
        -50.0,
    )
    direct_preview = service.calculate(project, direct)
    direct_candidate = deepcopy(project)
    direct_candidate.seals.append(deepcopy(direct))
    direct_build = RossModelBuilder(rs).build(direct_candidate, strict=True)
    direct_element = next(element for element in direct_build.rotor.bearing_elements if element.tag == direct.name)
    direct_expected_k = np.asarray([[1.0e6, 1.0e5], [-1.0e5, 1.2e6]])
    direct_expected_c = np.asarray([[2.0e3, 50.0], [-50.0, 2.2e3]])
    direct_pass = bool(
        type(direct_preview.native).__name__ == "SealElement"
        and np.allclose(direct_element.K(0.0)[:2, :2], direct_expected_k, rtol=0.0, atol=1e-12)
        and np.allclose(direct_element.C(0.0)[:2, :2], direct_expected_c, rtol=0.0, atol=1e-12)
    )
    prospective_pass = bool(
        direct_preview.node is not None
        and direct_build.node_insertion_plan.node_for(x) == direct_preview.node
        and not any(abs(value - x) <= 1e-7 for value in project.topology_split_positions_mm())
    )

    labyrinth = LabyrinthSealSpec(
        name="Seal 0.25 Labyrinth",
        position_mm=x,
        kxx=0.0,
        kyy=0.0,
        cxx=0.0,
        cyy=0.0,
        shaft_radius_m=0.0725,
        radial_clearance_m=0.0003,
        n_teeth=16,
        pitch_m=0.003175,
        tooth_height_m=0.003175,
        tooth_width_m=0.0001524,
        seal_type="inter",
        inlet_pressure_pa=308000.0,
        outlet_pressure_pa=94300.0,
        inlet_temperature_k=283.15,
        frequency_rpm=[8000.0],
        preswirl=0.98,
        gas_composition={},
        molar_kg_kmol=28.96807,
        gamma=1.41,
        tz_k=(283.15, 282.60903080958565),
        muz_pa_s=(1.7746561138374613e-05, 1.7687886306966975e-05),
    )
    lab_preview = service.calculate(project, labyrinth)
    lab_point = lab_preview.coefficients[0]
    lab_regression = bool(
        np.isclose(lab_point.kxx, -50456.586597, rtol=1e-4)
        and np.isclose(lab_point.kxy, 35541.605312, rtol=1e-4)
        and np.isclose(lab_point.kyx, -35541.605312, rtol=1e-4)
        and np.isclose(lab_point.cxx, 23.825111, rtol=1e-4)
        and np.isclose(lab_point.cxy, 56.255682, rtol=1e-4)
        and lab_preview.leakage_kg_s
        and np.isclose(lab_preview.leakage_kg_s[0], 0.05195, rtol=0.02)
    )
    lab_assembled = _assembled_seal(rs, project, lab_preview)
    lab_builder = _lateral_parity(lab_preview.native, lab_assembled, 8000.0)
    lab_k_traces = _trace_count(lab_preview.native.plot(coefficients=["kxx", "kyy", "kxy", "kyx"], frequency_units="RPM"))
    lab_pressure_traces = _trace_count(lab_preview.native.plot_pressure_distribution(pressure_units="MPa", length_units="mm"))

    hole = HolePatternSealSpec(
        name="Seal 0.25 Hole Pattern",
        position_mm=x,
        kxx=0.0,
        kyy=0.0,
        cxx=0.0,
        cyy=0.0,
        shaft_radius_m=0.0751,
        radial_clearance_m=0.0004,
        length_m=0.0254,
        roughness=0.00198,
        cell_length_m=0.001,
        cell_width_m=0.001,
        cell_depth_m=0.00229,
        inlet_pressure_pa=1830000.0,
        outlet_pressure_pa=823500.0,
        inlet_temperature_k=300.0,
        frequency_rpm=[5000.0],
        gas_composition={},
        molar_kg_kmol=29.0,
        gamma=1.4,
        b_suther=1.458e-6,
        s_suther=110.4,
        preswirl=1.0,
        entr_coef=0.1,
        exit_coef=0.5,
    )
    hole_preview = service.calculate(project, hole)
    hole_point = hole_preview.coefficients[0]
    hole_regression = bool(
        np.isclose(hole_point.kxx, 586228.88958017, rtol=1e-4)
        and np.isclose(hole_point.kxy, 159741.17580073, rtol=1e-4)
        and np.isclose(hole_point.kyx, -159741.17580073, rtol=1e-4)
        and np.isclose(hole_point.cxx, 294.42942927, rtol=1e-4)
        and np.isclose(hole_point.cxy, -27.16217997, rtol=1e-4)
        and hole_preview.leakage_kg_s
        and np.isclose(hole_preview.leakage_kg_s[0], 0.6313559209954082, rtol=1e-4)
    )
    hole_assembled = _assembled_seal(rs, project, hole_preview)
    hole_builder = _lateral_parity(hole_preview.native, hole_assembled, 5000.0)
    hole_k_traces = _trace_count(hole_preview.native.plot(coefficients=["kxx", "kyy", "kxy", "kyx"], frequency_units="RPM"))
    hole_pressure_traces = _trace_count(hole_preview.native.plot_pressure_distribution(pressure_units="MPa", length_units="mm"))

    hybrid = HybridSealSpec(
        name="Seal 0.25 Hybrid",
        position_mm=x,
        kxx=0.0,
        kyy=0.0,
        cxx=0.0,
        cyy=0.0,
        shaft_radius_m=0.025,
        inlet_pressure_pa=500000.0,
        outlet_pressure_pa=100000.0,
        inlet_temperature_k=300.0,
        frequency_rpm=[5000.0],
        gas_composition={},
        molar_kg_kmol=28.96807,
        gamma=1.4,
        hole_pattern=HolePatternStageSpec(
            radial_clearance_m=0.0003,
            length_m=0.04,
            roughness=0.0001,
            cell_length_m=0.003,
            cell_width_m=0.003,
            cell_depth_m=0.002,
            preswirl=0.8,
            entr_coef=0.5,
            exit_coef=1.0,
            b_suther=1.458e-6,
            s_suther=110.4,
        ),
        labyrinth=LabyrinthStageSpec(
            radial_clearance_m=0.00025,
            n_teeth=10,
            pitch_m=0.003,
            tooth_height_m=0.003,
            tooth_width_m=0.00015,
            seal_type="inter",
            preswirl=0.9,
            tz_k=(300.0, 299.5),
            muz_pa_s=(1.85e-05, 1.84e-05),
        ),
        pressure_match_tolerance=1e-6,
        pressure_match_max_iterations=100,
    )
    hybrid_preview = service.calculate(project, hybrid)
    hybrid_point = hybrid_preview.coefficients[0]
    interface_pressure = float(hybrid_preview.summary["interface_pressure_pa"])
    iterations = int(hybrid_preview.summary["n_iterations"])
    final_convergence = float(hybrid_preview.summary["final_convergence"])
    hybrid_leakage = float(hybrid_preview.leakage_kg_s[0])
    hybrid_regression = bool(
        100000.0 < interface_pressure < 500000.0
        and np.isclose(interface_pressure, 219522.094727, rtol=1e-2)
        and np.isclose(hybrid_leakage, 0.034898, rtol=1e-2)
        and np.isclose(hybrid_point.kxx, 202947.350538, rtol=1e-2)
        and np.isclose(hybrid_point.kxy, 28599.34387089, rtol=1e-2)
        and np.isclose(hybrid_point.cxx, 61.950937, rtol=1e-2)
        and np.isclose(hybrid_point.cxy, -7.383646, rtol=1e-2)
        and iterations > 0
        and final_convergence <= hybrid.pressure_match_tolerance
    )
    hybrid_assembled = _assembled_seal(rs, project, hybrid_preview)
    hybrid_builder = _lateral_parity(hybrid_preview.native, hybrid_assembled, 5000.0)
    hybrid_conv_traces = _trace_count(hybrid_preview.native.plot_convergence())

    roundtrip_model = deepcopy(model)
    assert roundtrip_model.engineering is not None
    roundtrip_model.engineering.seals.extend(
        [deepcopy(lab_preview.prepared), deepcopy(hole_preview.prepared), deepcopy(hybrid_preview.prepared)]
    )
    with tempfile.TemporaryDirectory(prefix="ross-studio-seal-025-") as root:
        target = save_project(roundtrip_model, Path(root) / "seal025.rossproj")
        restored = load_project(target)
    persistence = bool(
        restored.engineering is not None
        and restored.engineering.seals[-3:] == roundtrip_model.engineering.seals[-3:]
    )

    gates = (
        prospective_pass,
        direct_pass,
        lab_regression,
        lab_builder,
        lab_k_traces > 0,
        lab_pressure_traces > 0,
        hole_regression,
        hole_builder,
        hole_k_traces > 0,
        hole_pressure_traces > 0,
        hybrid_regression,
        hybrid_builder,
        hybrid_conv_traces >= 3,
        persistence,
    )

    return SealQualification(
        status="PASS" if all(gates) else "FAIL",
        ross_version=rs.__version__,
        prospective_exact_node_pass=prospective_pass,
        direct_kc_parity_pass=direct_pass,
        labyrinth_native_class=type(lab_preview.native).__name__,
        labyrinth_kxx_n_m=lab_point.kxx,
        labyrinth_kxy_n_m=lab_point.kxy,
        labyrinth_cxx_n_s_m=lab_point.cxx,
        labyrinth_cxy_n_s_m=lab_point.cxy,
        labyrinth_leakage_kg_s=float(lab_preview.leakage_kg_s[0]),
        labyrinth_regression_pass=lab_regression,
        labyrinth_builder_parity_pass=lab_builder,
        labyrinth_k_plot_traces=lab_k_traces,
        labyrinth_pressure_plot_traces=lab_pressure_traces,
        hole_pattern_native_class=type(hole_preview.native).__name__,
        hole_pattern_kxx_n_m=hole_point.kxx,
        hole_pattern_kxy_n_m=hole_point.kxy,
        hole_pattern_cxx_n_s_m=hole_point.cxx,
        hole_pattern_cxy_n_s_m=hole_point.cxy,
        hole_pattern_leakage_kg_s=float(hole_preview.leakage_kg_s[0]),
        hole_pattern_regression_pass=hole_regression,
        hole_pattern_builder_parity_pass=hole_builder,
        hole_pattern_k_plot_traces=hole_k_traces,
        hole_pattern_pressure_plot_traces=hole_pressure_traces,
        hybrid_native_class=type(hybrid_preview.native).__name__,
        hybrid_interface_pressure_pa=interface_pressure,
        hybrid_iterations=iterations,
        hybrid_final_convergence=final_convergence,
        hybrid_leakage_kg_s=hybrid_leakage,
        hybrid_kxx_n_m=hybrid_point.kxx,
        hybrid_kxy_n_m=hybrid_point.kxy,
        hybrid_cxx_n_s_m=hybrid_point.cxx,
        hybrid_cxy_n_s_m=hybrid_point.cxy,
        hybrid_regression_pass=hybrid_regression,
        hybrid_builder_parity_pass=hybrid_builder,
        hybrid_convergence_plot_traces=hybrid_conv_traces,
        persistence_roundtrip_pass=persistence,
    )


__all__ = ["SealQualification", "run_seal_qualification"]
