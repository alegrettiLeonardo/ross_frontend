#!/usr/bin/env python3
"""Diagnostic W60 unbalance correlation: RotorDin reference versus pinned ROSS.

This is intentionally an observational gate first. It fails only when the ROSS
calculation cannot be compared consistently (missing/non-finite data, mismatched
speed/probe counts). Numerical similarity thresholds must be justified from the
correlation evidence before they become release gates.
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
from ross_frontend.backends.ross.response_calculator import RossResponseCalculator
from ross_frontend.legacy_import import load_irdin_project


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "OP-W60-500-60Hz-IC611-P3"
INPUT = CASE_DIR / "irdin_input.txt"
REFERENCE = CASE_DIR / "rotordin_unbalance_keypoints.csv"


def load_reference(path: Path) -> tuple[list[float], list[list[float]], list[list[float]]]:
    with path.open("r", encoding="utf-8") as stream:
        rows = list(csv.DictReader(line for line in stream if not line.startswith("#")))
    if not rows:
        raise RuntimeError(f"Empty RotorDin reference: {path}")
    rpm = [float(row["rpm"]) for row in rows]
    amplitudes = [
        [float(row[f"amp_p{probe}_m"]) for row in rows]
        for probe in range(1, 5)
    ]
    phases_deg = [
        [degrees(float(row[f"phase_p{probe}_rad"])) for row in rows]
        for probe in range(1, 5)
    ]
    return rpm, amplitudes, phases_deg


def circular_delta_deg(actual: float, reference: float) -> float:
    return (actual - reference + 180.0) % 360.0 - 180.0


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q))


def projected_responses(rotor, build, project, rpm: list[float]):
    speed = rpm_to_rad_s(rpm)
    nodes = [build.node_by_position_mm[build_builder._p(item.position_mm)] for item in project.unbalances]
    magnitude = [item.magnitude_g_mm * 1e-6 for item in project.unbalances]
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
        node = build.node_by_position_mm[build_builder._p(probe.position_mm)]
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
        phase_error = [abs(circular_delta_deg(a, r)) for a, r in zip(phase_deg, ref_phase)]
        ref_peak_i = max(range(len(rpm)), key=lambda i: ref_amp[i])
        ross_peak_i = max(range(len(rpm)), key=lambda i: amplitude[i])
        item = {
            "probe": idx,
            "median_amplitude_ratio": statistics.median(ratios),
            "median_abs_relative_amplitude_error": statistics.median(relative),
            "p95_abs_relative_amplitude_error": percentile(relative, 95.0),
            "max_abs_relative_amplitude_error": max(relative),
            "median_abs_phase_error_deg": statistics.median(phase_error),
            "p95_abs_phase_error_deg": percentile(phase_error, 95.0),
            "max_abs_phase_error_deg": max(phase_error),
            "reference_peak_keypoint": {
                "rpm": rpm[ref_peak_i],
                "amplitude_m": ref_amp[ref_peak_i],
            },
            "ross_peak_keypoint": {
                "rpm": rpm[ross_peak_i],
                "amplitude_m": amplitude[ross_peak_i],
            },
        }
        probes.append(item)
        print(
            f"{label} P{idx}: amp ratio median={item['median_amplitude_ratio']:.6g}; "
            f"amp |rel err| median/p95/max={item['median_abs_relative_amplitude_error']:.3%}/"
            f"{item['p95_abs_relative_amplitude_error']:.3%}/{item['max_abs_relative_amplitude_error']:.3%}; "
            f"phase |err| median/p95/max={item['median_abs_phase_error_deg']:.3f}/"
            f"{item['p95_abs_phase_error_deg']:.3f}/{item['max_abs_phase_error_deg']:.3f} deg; "
            f"peak ref={rpm[ref_peak_i]:.3f} rpm, ROSS={rpm[ross_peak_i]:.3f} rpm"
        )
    return probes


if __name__ == "__main__":
    rpm, reference_amp, reference_phase = load_reference(REFERENCE)
    project = load_irdin_project(INPUT)
    if len(project.probes) != 4:
        raise RuntimeError(f"Expected four W60 probes, got {len(project.probes)}")
    if len(project.unbalances) != 2:
        raise RuntimeError(f"Expected two W60 unbalance planes, got {len(project.unbalances)}")

    build_builder = RossModelBuilder()
    build = build_builder.build(project)

    print("W60 RotorDin -> ROSS unbalance correlation")
    print(f"Reference points: {len(rpm)}; rpm: {rpm[0]:.6f} .. {rpm[-1]:.6f}")
    print("Unbalance planes: " + ", ".join(
        f"x={item.position_mm:g} mm, U={item.magnitude_g_mm:g} g.mm, phase={item.phase_deg:g} deg"
        for item in project.unbalances
    ))
    print("Production dynamic path: UmpRotor" if build.rotor is not build.base_rotor else "Production dynamic path: native Rotor")

    production = projected_responses(build.rotor, build, project, rpm)
    production_metrics = summarize("UMP", rpm, reference_amp, reference_phase, production)

    # Diagnostic only: isolate how much the legacy-compatible UMP extension shifts
    # the response. This is not a substitute production model.
    base = projected_responses(build.base_rotor, build, project, rpm)
    base_metrics = summarize("NO_UMP_DIAGNOSTIC", rpm, reference_amp, reference_phase, base)

    payload = {
        "case": "OP-W60-500-60Hz-IC611-P3",
        "reference": "RotorDin Fortran rotordin -std -f -b",
        "reference_points": len(rpm),
        "rpm_start": rpm[0],
        "rpm_final": rpm[-1],
        "production_path": type(build.rotor).__name__,
        "production": production_metrics,
        "without_ump_diagnostic": base_metrics,
    }
    print("W60_CORRELATION_JSON=" + json.dumps(payload, separators=(",", ":"), sort_keys=True))
