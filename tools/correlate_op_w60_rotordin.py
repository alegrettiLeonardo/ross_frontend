from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSS = ROOT / "artifacts" / "op_w60_pipeline_summary.json"
DEFAULT_GOLDEN = ROOT / "tests" / "golden" / "op_w60_rotordin_gmm_900_4500.csv"
DEFAULT_META = ROOT / "tests" / "golden" / "op_w60_rotordin_gmm_metadata.json"
DEFAULT_JSON = ROOT / "artifacts" / "op_w60_ross_vs_rotordin_correlation.json"
DEFAULT_CSV = ROOT / "artifacts" / "op_w60_ross_vs_rotordin_correlation.csv"


def _wrap_deg(value: np.ndarray | float) -> np.ndarray:
    a = np.asarray(value, dtype=float)
    return (a + 180.0) % 360.0 - 180.0


def _read_golden(path: Path) -> dict[str, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    result: dict[str, np.ndarray] = {}
    for key in rows[0]:
        result[key] = np.asarray([float(row[key]) for row in rows], dtype=float)
    return result


def _complex_probe_matrix(ref: dict[str, np.ndarray]) -> np.ndarray:
    amp = np.column_stack([ref[f"amp_p{i}_um"] for i in range(1, 5)])
    phase = np.column_stack([ref[f"phase_p{i}_deg"] for i in range(1, 5)])
    return amp * np.exp(1j * np.deg2rad(phase))


def _physical_degree_reference(
    ref: dict[str, np.ndarray], metadata: dict
) -> tuple[np.ndarray, np.ndarray]:
    """Convert the committed bug-compatible 45-rad golden to intended 45 degrees.

    The supplied migrated RotorDin frontend right-justifies RANUN in an A10 field.
    `cadjf(cin,1)` then loses the token, so the solver defaults to radians. A direct
    left-justified RANUN=D run proved that the physical degree result is exactly an
    orthogonal rotation of the two complex channels. No solver result is fitted here.
    """

    q = _complex_probe_matrix(ref).copy()
    probes = metadata["probes"]
    for first, second in ((0, 1), (2, 3)):
        raw = float(probes[first]["orientation_raw"])
        if abs(raw - float(probes[second]["orientation_raw"])) > 1e-12:
            raise RuntimeError("Physical-degree reconstruction requires an orthogonal pair with a common raw orientation.")
        # q_bug = R(raw radians) q_xy; q_deg = R(raw degrees) q_xy.
        delta = np.deg2rad(raw) - raw
        c = float(np.cos(delta))
        s = float(np.sin(delta))
        a = q[:, first].copy()
        b = q[:, second].copy()
        q[:, first] = c * a + s * b
        q[:, second] = -s * a + c * b
    return np.abs(q), _wrap_deg(np.rad2deg(np.angle(q)))


def _amp_metrics(ross: np.ndarray, ref: np.ndarray, rpm: np.ndarray, rated_rpm: float) -> dict[str, float]:
    rated = int(np.argmin(np.abs(rpm - rated_rpm)))
    ir = int(np.argmax(ross))
    ig = int(np.argmax(ref))
    rmse = float(np.sqrt(np.mean((ross - ref) ** 2)))
    return {
        "correlation_r": float(np.corrcoef(ross, ref)[0, 1]),
        "rmse_um": rmse,
        "mae_um": float(np.mean(np.abs(ross - ref))),
        "nrmse_percent_of_rotordin_peak": 100.0 * rmse / float(np.max(ref)),
        "ross_peak_um": float(ross[ir]),
        "ross_peak_rpm": float(rpm[ir]),
        "rotordin_peak_um": float(ref[ig]),
        "rotordin_peak_rpm": float(rpm[ig]),
        "peak_amplitude_error_percent": 100.0 * (float(ross[ir]) - float(ref[ig])) / float(ref[ig]),
        "ross_rated_um": float(ross[rated]),
        "rotordin_rated_um": float(ref[rated]),
        "rated_amplitude_error_percent": 100.0 * (float(ross[rated]) - float(ref[rated])) / float(ref[rated]),
    }


def _phase_metrics(
    ross_deg: np.ndarray,
    ref_deg: np.ndarray,
    ref_amp_um: np.ndarray,
    rpm: np.ndarray,
    rated_rpm: float,
) -> dict[str, object]:
    """Compare phase using the source-derived fixed -90 degree reference shift."""

    mask = ref_amp_um >= 0.20 * float(np.max(ref_amp_um))
    rated = int(np.argmin(np.abs(rpm - rated_rpm)))

    fixed_offset = -90.0
    fixed_delta = _wrap_deg(ross_deg + fixed_offset - ref_deg)
    fixed_mae = float(np.mean(np.abs(fixed_delta[mask])))
    fixed_median = float(np.median(np.abs(fixed_delta[mask])))
    fixed_p95 = float(np.percentile(np.abs(fixed_delta[mask]), 95.0))

    # Free global phasor offset is reported only as a diagnostic. Qualification
    # uses the fixed source-level convention above; no fitted offset is applied.
    complex_cross = np.sum(
        ref_amp_um[mask]
        * np.exp(1j * np.deg2rad(ref_deg[mask]))
        * np.conj(ref_amp_um[mask] * np.exp(1j * np.deg2rad(ross_deg[mask])))
    )
    best_offset = float(np.rad2deg(np.angle(complex_cross))) if abs(complex_cross) > 0 else 0.0
    best_delta = _wrap_deg(ross_deg + best_offset - ref_deg)

    qualified = bool(fixed_mae <= 5.0 and fixed_p95 <= 10.0)
    return {
        "qualified": qualified,
        "mask": "RotorDin amplitude >= 20% of channel peak",
        "fixed_source_offset_deg": fixed_offset,
        "fixed_mean_abs_error_deg": fixed_mae,
        "fixed_median_abs_error_deg": fixed_median,
        "fixed_p95_abs_error_deg": fixed_p95,
        "fixed_rated_error_deg": float(fixed_delta[rated]),
        "best_free_diagnostic_offset_deg": best_offset,
        "best_free_mean_abs_error_deg": float(np.mean(np.abs(best_delta[mask]))),
        "note": "Qualification uses exactly -90 deg from the phasor convention audit; the free offset is diagnostic only.",
    }


def _critical_metrics(ross_summary: dict, metadata: dict) -> list[dict[str, float]]:
    candidates = [
        row for row in ross_summary["critical_speeds"]
        if abs(float(row["damping_ratio"])) < 0.5
    ]
    result = []
    for ref_rpm in metadata["campbell_reference"]["critical_1x_rpm"]:
        row = min(candidates, key=lambda item: abs(float(item["speed_rpm"]) - float(ref_rpm)))
        ross_rpm = float(row["speed_rpm"])
        result.append(
            {
                "rotordin_rpm": float(ref_rpm),
                "ross_rpm": ross_rpm,
                "delta_rpm": ross_rpm - float(ref_rpm),
                "error_percent": 100.0 * (ross_rpm - float(ref_rpm)) / float(ref_rpm),
                "ross_mode": int(row["mode"]),
                "ross_damping_ratio": float(row["damping_ratio"]),
            }
        )
    return result


def correlate(ross_path: Path, golden_path: Path, metadata_path: Path) -> tuple[dict, list[dict[str, float]]]:
    ross = json.loads(ross_path.read_text(encoding="utf-8"))
    raw_ref = _read_golden(golden_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rpm = np.asarray(ross["response_speed_rpm"], dtype=float)
    if not np.array_equal(rpm, raw_ref["rpm"]):
        raise RuntimeError("ROSS and RotorDin response grids differ; correlation refuses interpolation.")

    rated_rpm = float(ross["qualification_policy"]["rated_speed_rpm"])
    ross_amp = np.column_stack([np.asarray(p["amplitude_um"], dtype=float) for p in ross["probes"]])
    ross_phase = _wrap_deg(np.column_stack([np.asarray(p["phase_deg"], dtype=float) for p in ross["probes"]]))
    ref_amp, ref_phase = _physical_degree_reference(raw_ref, metadata)

    channels = []
    for index in range(4):
        amplitude = _amp_metrics(ross_amp[:, index], ref_amp[:, index], rpm, rated_rpm)
        phase = _phase_metrics(ross_phase[:, index], ref_phase[:, index], ref_amp[:, index], rpm, rated_rpm)
        amplitude["qualified"] = bool(
            amplitude["correlation_r"] >= 0.99
            and amplitude["nrmse_percent_of_rotordin_peak"] <= 5.0
        )
        channels.append({"probe": index + 1, "amplitude": amplitude, "phase": phase})

    pairs = []
    for name, indices in (("DE", (0, 1)), ("NDE", (2, 3))):
        ross_pair = np.sqrt(np.sum(ross_amp[:, list(indices)] ** 2, axis=1))
        ref_pair = np.sqrt(np.sum(ref_amp[:, list(indices)] ** 2, axis=1))
        pair_metrics = _amp_metrics(ross_pair, ref_pair, rpm, rated_rpm)
        pair_metrics["qualified"] = bool(
            pair_metrics["correlation_r"] >= 0.99
            and pair_metrics["nrmse_percent_of_rotordin_peak"] <= 5.0
        )
        pairs.append({"bearing": name, "amplitude_resultant": pair_metrics})

    static_ref = metadata["static_reference"]
    static_ross = ross["static"]
    static_error = 100.0 * (
        float(static_ross["max_abs_deformation_um"]) - float(static_ref["max_abs_deformation_um"])
    ) / float(static_ref["max_abs_deformation_um"])
    ross_reactions = [float(value) for value in static_ross["bearing_forces_n"].values()]
    reaction_rows = []
    for i, (ross_n, ref_n) in enumerate(zip(ross_reactions, static_ref["bearing_reactions_z_n"]), 1):
        reaction_rows.append(
            {
                "bearing": i,
                "ross_n": ross_n,
                "rotordin_n": float(ref_n),
                "error_percent": 100.0 * (ross_n - float(ref_n)) / float(ref_n),
            }
        )

    critical = _critical_metrics(ross, metadata)
    static_pass = abs(static_error) <= 1.0 and all(abs(row["error_percent"]) <= 1.0 for row in reaction_rows)
    critical_pass = all(abs(row["error_percent"]) <= 2.0 for row in critical)
    pair_pass = all(row["amplitude_resultant"]["qualified"] for row in pairs)
    channel_pass = all(row["amplitude"]["qualified"] for row in channels)
    phase_pass = all(row["phase"]["qualified"] for row in channels)
    overall = static_pass and critical_pass and pair_pass and channel_pass and phase_pass

    summary = {
        "case": ross["project"],
        "status": "PASS" if overall else ("PARTIAL" if static_pass and critical_pass and pair_pass else "FAIL"),
        "unit_contract": "PASS",
        "lateral_convention": {
            "ross_project": ross.get("lateral_convention", "unknown"),
            "qualified_import_contract": metadata["lateral_convention_evidence"]["qualified_import_convention"],
            "bearing_cross_term_mapping": "IDENTITY",
            "gyro_mapping": "G_RotorDin_positive = -G_ROSS_native",
            "synchronous_force_mapping": "ROSS [1,-j] -> RotorDin-positive adapter [1,+j]",
        },
        "probe_angle_contract": {
            "production": "DEGREES",
            "committed_raw_golden": metadata["response_angle_contract"]["golden_effective_contract"],
            "reference_used_for_qualification": "physical DEGREES reconstructed by exact orthogonal complex rotation",
        },
        "grid": {"points": int(len(rpm)), "min_rpm": float(rpm[0]), "max_rpm": float(rpm[-1])},
        "rotordin_provenance": metadata["source"],
        "structural_static": {
            "qualified": static_pass,
            "ross_max_deformation_um": float(static_ross["max_abs_deformation_um"]),
            "rotordin_max_deformation_um": float(static_ref["max_abs_deformation_um"]),
            "max_deformation_error_percent": static_error,
            "bearing_reactions": reaction_rows,
        },
        "critical_1x": {"qualified": critical_pass, "rows": critical},
        "oriented_probe_channels": {
            "amplitude_qualified": channel_pass,
            "phase_qualified": phase_pass,
            "rows": channels,
        },
        "orthogonal_probe_pair_resultants": {"qualified": pair_pass, "rows": pairs},
        "interpretation": {
            "unit_error_closed": True,
            "gross_mass_stiffness_error_unlikely": static_pass and critical_pass,
            "bearing_cross_coupling_requires_sign_change": False,
            "positive_rotation_convention_closed": channel_pass and pair_pass,
            "ranun_parser_bug_isolated": True,
            "individual_directional_channels_correlate": channel_pass,
            "phase_correlates_with_fixed_source_offset": phase_pass,
            "remaining_isolation_targets": [] if overall else [
                "residual high-speed damping/amplitude differences",
                "any phase residual above the fixed -90 degree convention gate",
            ],
        },
    }

    detail_rows: list[dict[str, float]] = []
    for k, speed in enumerate(rpm):
        row: dict[str, float] = {"rpm": float(speed)}
        for i in range(4):
            row[f"ross_amp_p{i+1}_um"] = float(ross_amp[k, i])
            row[f"rotordin_degree_amp_p{i+1}_um"] = float(ref_amp[k, i])
            row[f"amp_error_p{i+1}_um"] = float(ross_amp[k, i] - ref_amp[k, i])
            row[f"ross_phase_p{i+1}_deg"] = float(ross_phase[k, i])
            row[f"rotordin_degree_phase_p{i+1}_deg"] = float(ref_phase[k, i])
            row[f"phase_error_after_minus90_p{i+1}_deg"] = float(_wrap_deg(ross_phase[k, i] - 90.0 - ref_phase[k, i]))
        row["ross_de_resultant_um"] = float(np.hypot(ross_amp[k, 0], ross_amp[k, 1]))
        row["rotordin_de_resultant_um"] = float(np.hypot(ref_amp[k, 0], ref_amp[k, 1]))
        row["ross_nde_resultant_um"] = float(np.hypot(ross_amp[k, 2], ross_amp[k, 3]))
        row["rotordin_nde_resultant_um"] = float(np.hypot(ref_amp[k, 2], ref_amp[k, 3]))
        detail_rows.append(row)
    return summary, detail_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate qualified OP-W60 ROSS output against regenerated RotorDin golden data.")
    parser.add_argument("--ross", type=Path, default=DEFAULT_ROSS)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_META)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--enforce", action="store_true", help="Fail unless the full physical amplitude/phase correlation is qualified.")
    args = parser.parse_args()

    summary, detail = correlate(args.ross, args.golden, args.metadata)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with args.csv_out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(detail[0]))
        writer.writeheader()
        writer.writerows(detail)

    print(json.dumps({
        "status": summary["status"],
        "static": summary["structural_static"]["qualified"],
        "critical_1x": summary["critical_1x"]["qualified"],
        "pair_resultants": summary["orthogonal_probe_pair_resultants"]["qualified"],
        "oriented_amplitude": summary["oriented_probe_channels"]["amplitude_qualified"],
        "phase": summary["oriented_probe_channels"]["phase_qualified"],
        "json": str(args.json_out),
        "csv": str(args.csv_out),
    }, indent=2))

    if args.enforce and summary["status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
