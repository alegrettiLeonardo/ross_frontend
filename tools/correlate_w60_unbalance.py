#!/usr/bin/env python3
"""W60 unbalance correlation: RotorDin reference versus pinned ROSS.

This gate keeps physical ROSS and historical RotorDin compatibility separate.
The legacy source VALUE is intentionally tested both as physical g.mm and as the
raw numeric ``mu`` used by the Fortran solver. A second ROSS model replaces only
the shaft lateral M/K/G blocks by the exact RotorDin ``coemas/coerig/coegir``
matrices so structural formulation differences can be isolated without changing
bearings, supports, disks, probes, UMP or the upstream ROSS source.
"""

from __future__ import annotations

import csv
import json
from math import degrees, pi
from pathlib import Path
import statistics

import numpy as np

from ross_frontend.backends.coordinates import rpm_to_rad_s
from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.backends.ross.legacy_builder import RotorDinLegacyModelBuilder
from ross_frontend.backends.ross.response_calculator import RossResponseCalculator
from ross_frontend.legacy_import import load_irdin_project


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "OP-W60-500-60Hz-IC611-P3"
INPUT = CASE_DIR / "irdin_input.txt"
REFERENCE = CASE_DIR / "rotordin_unbalance_keypoints.csv"
PHASE_CONVENTION_ADJUSTMENT_DEG = 90.0
PHYSICAL_G_MM_TO_KG_M = 1e-6
ROTORDIN_RAW_TO_KG_M = 1.0


def load_reference(path: Path) -> tuple[list[float], list[list[float]], list[list[float]]]:
    with path.open("r", encoding="utf-8") as stream:
        rows = list(csv.DictReader(line for line in stream if not line.startswith("#")))
    if not rows:
        raise RuntimeError(f"Empty RotorDin reference: {path}")
    rpm = [float(row["rpm"]) for row in rows]
    amplitudes = [[float(row[f"amp_p{probe}_m"]) for row in rows] for probe in range(1, 5)]
    phases_deg = [[degrees(float(row[f"phase_p{probe}_rad"])) for row in rows] for probe in range(1, 5)]
    return rpm, amplitudes, phases_deg


def circular_delta_deg(actual: float, reference: float) -> float:
    return (actual - reference + 180.0) % 360.0 - 180.0


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q))


def projected_responses(rotor, build, project, rpm: list[float], *, source_value_to_kg_m: float):
    speed = rpm_to_rad_s(rpm)
    nodes = [build.node_by_position_mm[RossModelBuilder._p(item.position_mm)] for item in project.unbalances]
    magnitude = [item.magnitude_g_mm * source_value_to_kg_m for item in project.unbalances]
    phase = [item.phase_deg * pi / 180.0 for item in project.unbalances]
    native = rotor.run_unbalance_response(
        node=nodes,
        unbalance_magnitude=magnitude,
        unbalance_phase=phase,
        frequency=speed,
        modes=None,
    )
    number_dof = int(rotor.number_dof)
    out = []
    for probe in project.probes:
        node = build.node_by_position_mm[RossModelBuilder._p(probe.position_mm)]
        x_values = native.forced_resp[node * number_dof + 0, :]
        y_values = native.forced_resp[node * number_dof + 1, :]
        projected = RossResponseCalculator._rotate_probe(
            x_values,
            y_values,
            probe.orientation_deg,
            probe.coordinate,
        )
        amplitude = [abs(complex(value)) for value in projected]
        phase_deg = [degrees(np.angle(complex(value))) for value in projected]
        out.append((amplitude, phase_deg))
    return out


def summarize(label: str, rpm, reference_amp, reference_phase, responses):
    probes = []
    for idx, ((amplitude, phase_deg), ref_amp, ref_phase) in enumerate(
        zip(responses, reference_amp, reference_phase), start=1
    ):
        if len(amplitude) != len(rpm) or len(phase_deg) != len(rpm):
            raise RuntimeError(f"{label} probe {idx}: response length does not match reference speed vector")
        all_values = np.asarray([*amplitude, *phase_deg], dtype=float)
        if not np.all(np.isfinite(all_values)):
            raise RuntimeError(f"{label} probe {idx}: non-finite ROSS response")

        ratios = [a / r for a, r in zip(amplitude, ref_amp)]
        relative = [abs(a - r) / abs(r) for a, r in zip(amplitude, ref_amp)]
        phase_error_raw = [abs(circular_delta_deg(a, r)) for a, r in zip(phase_deg, ref_phase)]
        phase_error_aligned = [
            abs(circular_delta_deg(a + PHASE_CONVENTION_ADJUSTMENT_DEG, r))
            for a, r in zip(phase_deg, ref_phase)
        ]
        ref_peak_i = max(range(len(rpm)), key=lambda i: ref_amp[i])
        ross_peak_i = max(range(len(rpm)), key=lambda i: amplitude[i])
        peak_delta_pct = 100.0 * (rpm[ross_peak_i] - rpm[ref_peak_i]) / rpm[ref_peak_i]
        item = {
            "probe": idx,
            "median_amplitude_ratio": statistics.median(ratios),
            "median_abs_relative_amplitude_error": statistics.median(relative),
            "p95_abs_relative_amplitude_error": percentile(relative, 95.0),
            "max_abs_relative_amplitude_error": max(relative),
            "median_abs_phase_error_raw_deg": statistics.median(phase_error_raw),
            "p95_abs_phase_error_raw_deg": percentile(phase_error_raw, 95.0),
            "max_abs_phase_error_raw_deg": max(phase_error_raw),
            "median_abs_phase_error_aligned_deg": statistics.median(phase_error_aligned),
            "p95_abs_phase_error_aligned_deg": percentile(phase_error_aligned, 95.0),
            "max_abs_phase_error_aligned_deg": max(phase_error_aligned),
            "reference_peak_keypoint": {"rpm": rpm[ref_peak_i], "amplitude_m": ref_amp[ref_peak_i]},
            "ross_peak_keypoint": {"rpm": rpm[ross_peak_i], "amplitude_m": amplitude[ross_peak_i]},
            "peak_speed_delta_pct": peak_delta_pct,
        }
        probes.append(item)
        print(
            f"{label} P{idx}: amp ratio median={item['median_amplitude_ratio']:.6g}; "
            f"amp |rel err| median/p95/max={item['median_abs_relative_amplitude_error']:.3%}/"
            f"{item['p95_abs_relative_amplitude_error']:.3%}/{item['max_abs_relative_amplitude_error']:.3%}; "
            f"phase raw/aligned median={item['median_abs_phase_error_raw_deg']:.2f}/"
            f"{item['median_abs_phase_error_aligned_deg']:.2f} deg; "
            f"peak ref={rpm[ref_peak_i]:.3f}, ROSS={rpm[ross_peak_i]:.3f} rpm "
            f"(delta={peak_delta_pct:+.2f}%)"
        )
    return probes


if __name__ == "__main__":
    rpm, reference_amp, reference_phase = load_reference(REFERENCE)
    project = load_irdin_project(INPUT)
    if len(project.probes) != 4 or len(project.unbalances) != 2:
        raise RuntimeError("W60 golden case must contain four probes and two unbalance planes")

    native_build = RossModelBuilder().build(project)
    legacy_build = RotorDinLegacyModelBuilder().build(project)

    print("W60 RotorDin -> ROSS unbalance correlation")
    print(f"Reference points: {len(rpm)}; rpm: {rpm[0]:.6f} .. {rpm[-1]:.6f}")
    print(
        "Reference note: these keypoints come from the historical frontend-transformed run; "
        "its response range was overridden to the identification/Campbell range 900-4500 rpm."
    )
    print(
        "Phase convention: ROSS force vector is -90 deg relative to RotorDin; "
        f"aligned comparison adds +{PHASE_CONVENTION_ADJUSTMENT_DEG:g} deg to ROSS phase."
    )
    print(
        "Legacy VALUE semantics: RotorDin reads VALUE and uses it directly as mu in mu*omega^2; "
        "the source field has no validated physical unit declaration."
    )
    print("Unbalance planes: " + ", ".join(
        f"x={item.position_mm:g} mm, VALUE={item.magnitude_g_mm:g}, phase={item.phase_deg:g} deg"
        for item in project.unbalances
    ))
    print(
        "Shaft formulations: native ROSS Timoshenko versus exact RotorDin coemas/coerig/coegir lateral blocks."
    )

    physical_native = projected_responses(
        native_build.rotor, native_build, project, rpm, source_value_to_kg_m=PHYSICAL_G_MM_TO_KG_M
    )
    physical_native_metrics = summarize(
        "PHYSICAL_G_MM_NATIVE_ROSS", rpm, reference_amp, reference_phase, physical_native
    )

    raw_native = projected_responses(
        native_build.rotor, native_build, project, rpm, source_value_to_kg_m=ROTORDIN_RAW_TO_KG_M
    )
    raw_native_metrics = summarize(
        "ROTORDIN_RAW_NATIVE_ROSS", rpm, reference_amp, reference_phase, raw_native
    )

    raw_legacy_matrix = projected_responses(
        legacy_build.rotor, legacy_build, project, rpm, source_value_to_kg_m=ROTORDIN_RAW_TO_KG_M
    )
    raw_legacy_matrix_metrics = summarize(
        "ROTORDIN_RAW_EXACT_SHAFT_MKG", rpm, reference_amp, reference_phase, raw_legacy_matrix
    )

    raw_legacy_no_ump = projected_responses(
        legacy_build.base_rotor,
        legacy_build,
        project,
        rpm,
        source_value_to_kg_m=ROTORDIN_RAW_TO_KG_M,
    )
    raw_legacy_no_ump_metrics = summarize(
        "ROTORDIN_RAW_EXACT_SHAFT_MKG_NO_UMP",
        rpm,
        reference_amp,
        reference_phase,
        raw_legacy_no_ump,
    )

    payload = {
        "case": "OP-W60-500-60Hz-IC611-P3",
        "reference": "RotorDin Fortran rotordin -std -f -b via historical frontend serialization",
        "reference_points": len(rpm),
        "rpm_start": rpm[0],
        "rpm_final": rpm[-1],
        "source_unbalance_value_unit": "legacy_unknown",
        "physical_g_mm_to_kg_m": PHYSICAL_G_MM_TO_KG_M,
        "rotordin_raw_to_kg_m_for_compatibility": ROTORDIN_RAW_TO_KG_M,
        "rotordin_raw_basis": "Fortran reads VALUE into mu and resp_fv uses mu*omega^2 with no conversion",
        "response_solver_basis": "TABLE bearings select resp_fv direct full dynamic-matrix solve; no modal reduction",
        "phase_convention_adjustment_deg": PHASE_CONVENTION_ADJUSTMENT_DEG,
        "physical_g_mm_native_ross": physical_native_metrics,
        "rotordin_raw_native_ross": raw_native_metrics,
        "rotordin_raw_exact_shaft_mkg": raw_legacy_matrix_metrics,
        "rotordin_raw_exact_shaft_mkg_without_ump": raw_legacy_no_ump_metrics,
    }
    print("W60_CORRELATION_JSON=" + json.dumps(payload, separators=(",", ":"), sort_keys=True))
