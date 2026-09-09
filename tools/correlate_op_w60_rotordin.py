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
    # ROSS and RotorDin use different complex-force/output phasor conventions.
    # Evaluate only canonical constant offsets here. This is diagnostic, not a
    # physical correction: the legacy probe angle-unit contract is still open.
    mask = ref_amp_um >= 0.20 * float(np.max(ref_amp_um))
    rated = int(np.argmin(np.abs(rpm - rated_rpm)))
    candidates = []
    for offset in (0.0, 90.0, -90.0, 180.0):
        delta = _wrap_deg(ross_deg + offset - ref_deg)
        candidates.append(
            {
                "offset_deg": offset,
                "mean_abs_error_deg": float(np.mean(np.abs(delta[mask]))),
                "median_abs_error_deg": float(np.median(np.abs(delta[mask]))),
                "rated_error_deg": float(delta[rated]),
            }
        )
    best = min(candidates, key=lambda row: row["mean_abs_error_deg"])
    return {
        "qualified": False,
        "mask": "RotorDin amplitude >= 20% of channel peak",
        "candidate_constant_offsets": candidates,
        "best_diagnostic_offset": best,
        "note": "Constant phasor offsets do not close the residual phase error; legacy RANUN/orientation semantics remain under investigation.",
    }


def _critical_metrics(ross_summary: dict, metadata: dict) -> list[dict[str, float]]:
    # Reject heavily overdamped/non-lateral crossings when correlating the two
    # physical 1X shaft branches reported by RotorDin.
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
    ref = _read_golden(golden_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rpm = np.asarray(ross["response_speed_rpm"], dtype=float)
    if not np.array_equal(rpm, ref["rpm"]):
        raise RuntimeError("ROSS and RotorDin response grids differ; correlation refuses interpolation.")

    rated_rpm = float(ross["qualification_policy"]["rated_speed_rpm"])
    ross_amp = np.column_stack([np.asarray(p["amplitude_um"], dtype=float) for p in ross["probes"]])
    ross_phase = np.column_stack([np.asarray(p["phase_deg"], dtype=float) for p in ross["probes"]])
    ref_amp = np.column_stack([ref[f"amp_p{i}_um"] for i in range(1, 5)])
    ref_phase = np.column_stack([ref[f"phase_p{i}_deg"] for i in range(1, 5)])

    channels = []
    for index in range(4):
        channels.append(
            {
                "probe": index + 1,
                "amplitude": _amp_metrics(ross_amp[:, index], ref_amp[:, index], rpm, rated_rpm),
                "phase": _phase_metrics(
                    ross_phase[:, index], ref_phase[:, index], ref_amp[:, index], rpm, rated_rpm
                ),
            }
        )

    pairs = []
    for name, indices in (("DE", (0, 1)), ("NDE", (2, 3))):
        ross_pair = np.sqrt(np.sum(ross_amp[:, list(indices)] ** 2, axis=1))
        ref_pair = np.sqrt(np.sum(ref_amp[:, list(indices)] ** 2, axis=1))
        pair_metrics = _amp_metrics(ross_pair, ref_pair, rpm, rated_rpm)
        pair_metrics["qualified"] = bool(
            pair_metrics["correlation_r"] >= 0.95
            and pair_metrics["nrmse_percent_of_rotordin_peak"] <= 10.0
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
    channel_pass = all(
        row["amplitude"]["nrmse_percent_of_rotordin_peak"] <= 10.0 for row in channels
    )
    phase_pass = False

    summary = {
        "case": ross["project"],
        "status": "PARTIAL" if static_pass and critical_pass and pair_pass else "FAIL",
        "unit_contract": "PASS",
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
            "pair_resultant_response_correlates": pair_pass,
            "individual_directional_channels_correlate": channel_pass,
            "phase_correlates": phase_pass,
            "remaining_isolation_targets": [
                "RotorDin 27-station/26-element mesh versus ROSS 28-node/27-element explicit-insertion mesh",
                "RotorDin local quadratic intlag bearing interpolation versus ROSS UnivariateSpline interpolation",
                "legacy RANUN response-angle unit and complex response convention",
                "high-speed NDE resonance/damping around 3950-4000 rpm",
            ],
        },
    }

    detail_rows: list[dict[str, float]] = []
    for k, speed in enumerate(rpm):
        row: dict[str, float] = {"rpm": float(speed)}
        for i in range(4):
            row[f"ross_amp_p{i+1}_um"] = float(ross_amp[k, i])
            row[f"rotordin_amp_p{i+1}_um"] = float(ref_amp[k, i])
            row[f"amp_error_p{i+1}_um"] = float(ross_amp[k, i] - ref_amp[k, i])
            row[f"ross_phase_p{i+1}_deg"] = float(_wrap_deg(ross_phase[k, i]))
            row[f"rotordin_phase_p{i+1}_deg"] = float(_wrap_deg(ref_phase[k, i]))
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
    parser.add_argument("--enforce", action="store_true", help="Fail unless oriented-channel amplitude and phase are also qualified.")
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

    if args.enforce and (
        not summary["oriented_probe_channels"]["amplitude_qualified"]
        or not summary["oriented_probe_channels"]["phase_qualified"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
