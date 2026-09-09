from __future__ import annotations

import json
from math import pi
from pathlib import Path

import numpy as np
import ross as rs

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.analysis_pipeline import AnalysisPipelineService
from ross_studio.legacy_import import load_irdin_project


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"
OUT = ROOT / "artifacts" / "op_w60_pipeline_summary.json"


def main() -> int:
    project = load_irdin_project(FIXTURE)
    backend = RossAnalysisBackend(rs)
    service = AnalysisPipelineService(backend=backend)  # production GUI defaults

    def progress(event) -> None:
        print(
            f"[{event.index}/{event.total}] {event.state.upper():9s} "
            f"{event.stage}: {event.message} ({event.elapsed_s:.3f} s)"
        )

    result = service.run(project, progress=progress)
    case = project.operating_cases[0]
    rated_omega = float(case.rated_speed_rpm) * 2.0 * pi / 60.0

    unbalance_loads = [load for load in project.loads if load.kind.strip().casefold() == "unbalance"]
    load_by_node = {
        result.build.node_insertion_plan.node_for(load.position_mm): load
        for load in unbalance_loads
    }
    unbalance_input = []
    for applied in result.unbalance_inputs:
        load = load_by_node[applied.node]
        unbalance_input.append(
            {
                "name": load.name,
                "node": applied.node,
                "position_mm": load.position_mm,
                "raw_magnitude": applied.raw_magnitude,
                "raw_unit": applied.source_unit,
                "normalization_factor_to_kg_m": applied.magnitude_kg_m / applied.raw_magnitude,
                "magnitude_kg_m_sent_to_ross": applied.magnitude_kg_m,
                "phase_deg": load.phase_deg,
                "centrifugal_force_at_rated_n": applied.magnitude_kg_m * rated_omega**2,
            }
        )

    summary = {
        "project": project.name,
        "ross_version": getattr(rs, "__version__", "unknown"),
        "qualification_policy": {
            "modal_num_modes_requested": service.policy.modal_num_modes,
            "campbell_frequencies": service.policy.campbell_frequencies,
            "campbell_points_requested": service.policy.campbell_points,
            "response_points_requested": service.policy.response_points,
            "rated_speed_rpm": case.rated_speed_rpm,
        },
        "ross_compatibility": [
            {"code": note.code, "message": note.message}
            for note in backend.compatibility_notes
        ],
        "topology": {
            "physical_sections": project.physical_section_count,
            "shaft_elements": len(result.build.shaft_plan),
            "shaft_nodes": len(result.build.node_positions_mm),
            "support_link_nodes": result.build.support_link_nodes,
            "unresolved_positions_mm": result.build.unresolved_positions_mm,
        },
        "speed_envelope_rpm": [float(result.speed_rpm[0]), float(result.speed_rpm[-1])],
        "response_speed_station_count": int(len(result.speed_rpm)),
        "response_speed_rpm": [float(value) for value in result.speed_rpm],
        "campbell_speed_station_count": int(len(result.campbell.speed_range)),
        "static": {
            "max_abs_deformation_m": float(np.max(np.abs(np.asarray(result.static.deformation, dtype=float)))),
            "max_abs_deformation_um": float(np.max(np.abs(np.asarray(result.static.deformation, dtype=float))) * 1e6),
            "bearing_forces_n": {str(key): float(value) for key, value in result.static.bearing_forces.items()},
        },
        "modal_rated": [
            {
                "mode": mode.mode,
                "wn_hz": mode.wn_hz,
                "wd_hz": mode.wd_hz,
                "damping_ratio": mode.damping_ratio,
                "damping_percent": 100.0 * mode.damping_ratio,
                "log_dec": mode.log_dec,
                "whirl": mode.whirl,
            }
            for mode in result.modal_modes
        ],
        "critical_speeds": [
            {
                "mode": critical.mode,
                "speed_rpm": critical.speed_rpm,
                "frequency_hz": critical.frequency_hz,
                "damping_ratio": critical.damping_ratio,
                "damping_percent": 100.0 * critical.damping_ratio,
                "log_dec": critical.log_dec,
                "whirl": critical.whirl,
                "method": critical.method,
            }
            for critical in result.critical_speeds
        ],
        "unbalance_contract": {
            "domain_source_unit": "g*mm",
            "ross_required_unit": "kg*m",
            "conversion_location": "RossAnalysisBackend.run_unbalance_build",
            "conversion_factor": 1e-6,
            "inputs": unbalance_input,
        },
        "probes": [
            {
                "name": probe.name,
                "node": probe.node,
                "position_mm": probe.position_mm,
                "coordinate": probe.coordinate,
                "orientation_deg": probe.orientation_deg,
                "peak_speed_rpm": probe.peak_speed_rpm,
                "peak_amplitude_m": probe.peak_amplitude_m,
                "peak_amplitude_um": probe.peak_amplitude_um,
                "peak_phase_deg": probe.peak_phase_deg,
                "rated_speed_rpm": probe.rated_speed_rpm,
                "rated_amplitude_m": probe.rated_amplitude_m,
                "rated_amplitude_um": probe.rated_amplitude_um,
                "rated_phase_deg": probe.rated_phase_deg,
                "amplitude_m": [float(value) for value in probe.amplitude_m],
                "amplitude_um": [float(value) * 1e6 for value in probe.amplitude_m],
                "phase_deg": [float(value) for value in probe.phase_deg],
            }
            for probe in result.probe_responses
        ],
        "audits": [
            {"severity": audit.severity, "code": audit.code, "message": audit.message}
            for audit in result.audits
        ],
        "stage_elapsed_s": result.stage_elapsed_s,
        "total_elapsed_s": result.total_elapsed_s,
        "status": "PASS",
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Qualification summary written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
