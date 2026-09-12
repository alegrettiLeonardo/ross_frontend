from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import pi

import numpy as np

from .domain import (
    AdapterStatus,
    EngineeringError,
    FoundationCoefficientPoint,
    FoundationModel,
    FoundationSpec,
)
from .models import load_reference_project_model
from .ross_backend import RossModelBuilder


@dataclass(slots=True)
class FoundationQualification:
    status: str
    ross_version: str
    baseline_matrix_shape: list[int]
    dynamic_matrix_shape: list[int]
    rigid_exact_m_parity: bool
    rigid_exact_k_parity: bool
    rigid_exact_c_parity: bool
    high_stiffness_baseline_hz: list[float]
    high_stiffness_foundation_hz: list[float]
    high_stiffness_max_error_percent: float
    soft_foundation_hz: list[float]
    modal_sensitivity_max_shift_percent: float
    matrix_delta_norm_m: float
    matrix_delta_norm_k: float
    matrix_delta_norm_c: float
    matrix_trace_delta_m: float
    expected_foundation_mass_kg: float
    cross_coupled_k_pass: bool
    cross_coupled_c_pass: bool
    frequency_axis_rad_s_pass: bool
    frequency_interpolation_pass: bool
    unsupported_contracts_blocked: bool
    exact_support_ownership_pass: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _project():
    model = load_reference_project_model()
    if model.engineering is None:
        raise EngineeringError("Reference OP-W60 project did not expose an engineering RotorProject.")
    return model.engineering


def _modal_hz(rotor, *, count: int = 6) -> np.ndarray:
    result = rotor.run_modal(speed=0.0, num_modes=max(2 * count, 12))
    values = np.asarray(result.wd, dtype=float) / (2.0 * pi)
    values = values[np.isfinite(values) & (values > 1.0e-6)]
    if values.size < count:
        raise EngineeringError(f"Foundation modal gate expected at least {count} finite modes, received {values.size}.")
    return values[:count]


def _pad_baseline(base: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    if base.shape[0] > target_shape[0] or base.shape[1] > target_shape[1]:
        raise EngineeringError(f"Dynamic Foundation matrix unexpectedly shrank from {base.shape} to {target_shape}.")
    padded = np.zeros(target_shape, dtype=float)
    padded[: base.shape[0], : base.shape[1]] = base
    return padded


def _matrix_evidence(base_rotor, dynamic_rotor) -> tuple[float, float, float, float, list[int], list[int]]:
    m0 = np.asarray(base_rotor.M(), dtype=float)
    k0 = np.asarray(base_rotor.K(0.0), dtype=float)
    c0 = np.asarray(base_rotor.C(0.0), dtype=float)
    m1 = np.asarray(dynamic_rotor.M(), dtype=float)
    k1 = np.asarray(dynamic_rotor.K(0.0), dtype=float)
    c1 = np.asarray(dynamic_rotor.C(0.0), dtype=float)
    if not (m1.shape == k1.shape == c1.shape):
        raise EngineeringError(f"Dynamic Foundation global matrix shapes disagree: M={m1.shape}, K={k1.shape}, C={c1.shape}.")
    pm = _pad_baseline(m0, m1.shape)
    pk = _pad_baseline(k0, k1.shape)
    pc = _pad_baseline(c0, c1.shape)
    return (
        float(np.linalg.norm(m1 - pm)),
        float(np.linalg.norm(k1 - pk)),
        float(np.linalg.norm(c1 - pc)),
        float(np.trace(m1) - np.trace(pm)),
        list(m0.shape),
        list(m1.shape),
    )


def run_foundation_qualification() -> FoundationQualification:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise EngineeringError(f"Foundation 0.24 is qualified only against ROSS 2.3.0, received {rs.__version__}.")

    builder = RossModelBuilder(rs)
    baseline_project = _project()
    baseline_build = builder.build(deepcopy(baseline_project), strict=True)
    baseline = baseline_build.rotor

    rigid_project = deepcopy(baseline_project)
    rigid_project.foundations.append(FoundationSpec("Explicit rigid DE", 0, FoundationModel.RIGID))
    rigid = RossModelBuilder(rs).build(rigid_project, strict=True).rotor
    rigid_m = np.array_equal(np.asarray(rigid.M()), np.asarray(baseline.M()))
    rigid_k = np.array_equal(np.asarray(rigid.K(0.0)), np.asarray(baseline.K(0.0)))
    rigid_c = np.array_equal(np.asarray(rigid.C(0.0)), np.asarray(baseline.C(0.0)))

    baseline_hz = _modal_hz(baseline)

    # Isolate the stiffness asymptote: no Foundation mass is added here.  As
    # Kfoundation -> infinity, this topology must converge to the legacy/RIGID
    # direct-to-ground support rather than to a rigidly attached extra mass.
    high_project = deepcopy(baseline_project)
    high_project.foundations.append(
        FoundationSpec(
            name="DE high-stiffness limit",
            support_index=0,
            model_type=FoundationModel.LUMPED_KC,
            kxx=1.0e14,
            kyy=1.0e14,
            cxx=0.0,
            cyy=0.0,
        )
    )
    high_rotor = RossModelBuilder(rs).build(high_project, strict=True).rotor
    high_hz = _modal_hz(high_rotor)
    high_error = float(np.max(np.abs(high_hz - baseline_hz) / baseline_hz * 100.0))

    dynamic_mass = 125.0
    soft_project = deepcopy(baseline_project)
    soft_foundation = FoundationSpec(
        name="DE dynamic Foundation",
        support_index=0,
        model_type=FoundationModel.LUMPED_KCM,
        mass_kg=dynamic_mass,
        kxx=5.0e7,
        kyy=7.0e7,
        kxy=4.0e6,
        kyx=-2.0e6,
        cxx=4.0e4,
        cyy=6.0e4,
        cxy=2.0e3,
        cyx=-1.0e3,
    )
    soft_project.foundations.append(soft_foundation)
    dynamic_builder = RossModelBuilder(rs)
    soft_build = dynamic_builder.build(soft_project, strict=True)
    soft_rotor = soft_build.rotor
    soft_hz = _modal_hz(soft_rotor)
    sensitivity = float(np.max(np.abs(soft_hz - baseline_hz) / baseline_hz * 100.0))
    dm, dk, dc, trace_dm, baseline_shape, dynamic_shape = _matrix_evidence(baseline, soft_rotor)

    foundation_element = next(
        element for element in soft_rotor.bearing_elements if element.tag == f"{soft_foundation.name} / ground"
    )
    expected_k = np.asarray([[soft_foundation.kxx, soft_foundation.kxy], [soft_foundation.kyx, soft_foundation.kyy]])
    expected_c = np.asarray([[soft_foundation.cxx, soft_foundation.cxy], [soft_foundation.cyx, soft_foundation.cyy]])
    cross_k = bool(np.allclose(foundation_element.K(0.0)[:2, :2], expected_k, rtol=0.0, atol=1.0e-9))
    cross_c = bool(np.allclose(foundation_element.C(0.0)[:2, :2], expected_c, rtol=0.0, atol=1.0e-12))
    support_name = soft_project.supports[soft_foundation.support_index].name
    exact_ownership = bool(
        support_name in soft_build.support_link_nodes
        and dynamic_builder.last_foundation_nodes.get(soft_foundation.name) is not None
        and dynamic_builder.last_foundation_nodes[soft_foundation.name] != soft_build.support_link_nodes[support_name]
    )

    frequency_project = deepcopy(baseline_project)
    frequency_foundation = FoundationSpec(
        name="DE frequency Foundation",
        support_index=0,
        model_type=FoundationModel.FREQUENCY_DEPENDENT_KC,
        coefficients=[
            FoundationCoefficientPoint(10.0, 1.0e8, 0.0, 0.0, 1.2e8, 1.0e4, 0.0, 0.0, 1.2e4),
            FoundationCoefficientPoint(20.0, 3.0e8, 2.0e6, -4.0e6, 3.2e8, 3.0e4, 200.0, -400.0, 3.2e4),
        ],
    )
    frequency_project.foundations.append(frequency_foundation)
    frequency_rotor = RossModelBuilder(rs).build(frequency_project, strict=True).rotor
    frequency_element = next(
        element for element in frequency_rotor.bearing_elements if element.tag == f"{frequency_foundation.name} / ground"
    )
    axis_pass = bool(np.allclose(frequency_element.frequency, np.asarray([10.0, 20.0]) * 2.0 * pi, rtol=0.0, atol=1.0e-12))
    midpoint = 15.0 * 2.0 * pi
    midpoint_expected = np.asarray([[2.0e8, 1.0e6], [-2.0e6, 2.2e8]])
    interpolation_pass = bool(np.allclose(frequency_element.K(midpoint)[:2, :2], midpoint_expected, rtol=1.0e-12, atol=1.0e-8))

    blocked = True
    for candidate in (
        FoundationSpec("6DOF blocked", 0, FoundationModel.LUMPED_KCM, mass_kg=1.0, dof=6),
        FoundationSpec("ROM blocked", 0, FoundationModel.REDUCED_MATRIX),
    ):
        try:
            candidate.validate()
        except EngineeringError:
            blocked = blocked and candidate.status == AdapterStatus.BLOCKED
        else:
            blocked = False

    gates = (
        rigid_m,
        rigid_k,
        rigid_c,
        high_error < 0.5,
        sensitivity > 0.5,
        dm > 0.0,
        dk > 0.0,
        dc > 0.0,
        trace_dm > 0.0,
        cross_k,
        cross_c,
        axis_pass,
        interpolation_pass,
        blocked,
        exact_ownership,
    )
    return FoundationQualification(
        status="PASS" if all(gates) else "FAIL",
        ross_version=rs.__version__,
        baseline_matrix_shape=baseline_shape,
        dynamic_matrix_shape=dynamic_shape,
        rigid_exact_m_parity=rigid_m,
        rigid_exact_k_parity=rigid_k,
        rigid_exact_c_parity=rigid_c,
        high_stiffness_baseline_hz=[float(value) for value in baseline_hz],
        high_stiffness_foundation_hz=[float(value) for value in high_hz],
        high_stiffness_max_error_percent=high_error,
        soft_foundation_hz=[float(value) for value in soft_hz],
        modal_sensitivity_max_shift_percent=sensitivity,
        matrix_delta_norm_m=dm,
        matrix_delta_norm_k=dk,
        matrix_delta_norm_c=dc,
        matrix_trace_delta_m=trace_dm,
        expected_foundation_mass_kg=dynamic_mass,
        cross_coupled_k_pass=cross_k,
        cross_coupled_c_pass=cross_c,
        frequency_axis_rad_s_pass=axis_pass,
        frequency_interpolation_pass=interpolation_pass,
        unsupported_contracts_blocked=blocked,
        exact_support_ownership_pass=exact_ownership,
    )


__all__ = ["FoundationQualification", "run_foundation_qualification"]
