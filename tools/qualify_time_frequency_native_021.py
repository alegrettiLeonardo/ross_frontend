from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ross_studio import __version__
from ross_studio.domain import BearingSpec, DiskSpec, LoadSpec, OperatingCase, ProbeSpec, RotorProject, ShaftSection
from ross_studio.time_frequency_analysis import (
    ClearanceRequest,
    ClearanceService,
    FrequencyResponseRequest,
    FrequencyResponseService,
    HarmonicBalanceRequest,
    HarmonicBalanceService,
    TimeResponseRequest,
    TimeResponseService,
    UCSRequest,
    UCSService,
    UnbalanceResponseRequest,
    UnbalanceResponseService,
)
from ross_studio.time_frequency_native import (
    ClearanceNativeCatalog,
    FrequencyResponseNativeCatalog,
    HarmonicBalanceNativeCatalog,
    TIME_FREQUENCY_NATIVE_OUTPUTS,
    TimeResponseNativeCatalog,
    UCSNativeCatalog,
    UnbalanceResponseNativeCatalog,
)


ARTIFACT = Path("artifacts/time_frequency_native_021_qualification.json")
FIGURES = Path("artifacts/time_frequency_native_021")


def project_fixture() -> RotorProject:
    project = RotorProject(
        name="TF-021-qualification",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec("DE", 0.0, kxx=1e6, kyy=1e6, cxx=500.0, cyy=500.0, metadata={"radial_clearance_m": 100e-6}),
            BearingSpec("NDE", 1000.0, kxx=1e6, kyy=1e6, cxx=500.0, cyy=500.0, metadata={"radial_clearance_m": 120e-6}),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        loads=[LoadSpec("U1", "unbalance", 500.0, 100.0, 0.0, metadata={"source_unit": "g*mm"})],
        probes=[ProbeSpec("PX", 500.0, 1, 0.0), ProbeSpec("PY", 500.0, 1, 90.0)],
        operating_cases=[OperatingCase("Qualification", 1200.0, 600.0, 1800.0, 20.0)],
    )
    project.validate()
    return project


def traces(fig) -> int:
    return len(getattr(fig, "data", ()))


def main() -> int:
    import ross

    project = project_fixture()
    fr = FrequencyResponseService().run(project, FrequencyResponseRequest(600, 1800, 7, 500, 1, 500, 1))
    ub = UnbalanceResponseService().run(project, UnbalanceResponseRequest(600, 1800, 7))
    tr = TimeResponseService().run(project, TimeResponseRequest(1200, 1200, 0.10, 81, "newmark"))
    hb = HarmonicBalanceService().run(project, HarmonicBalanceRequest(1200, 0.10, 81, 1))
    ucs = UCSService().run(project, UCSRequest(5.0, 8.0, 4, 8, False))
    clr = ClearanceService().run(project, ClearanceRequest(1200, 5.0, 3))

    catalogs = {
        "frequency": FrequencyResponseNativeCatalog(fr),
        "unbalance": UnbalanceResponseNativeCatalog(ub),
        "time": TimeResponseNativeCatalog(tr),
        "hbm": HarmonicBalanceNativeCatalog(hb),
        "ucs": UCSNativeCatalog(ucs),
        "clearance": ClearanceNativeCatalog(clr),
    }

    figures = {
        "frequency_bode_polar": catalogs["frequency"].figure("all", frequency_units="rad/s", phase_units="rad"),
        "unbalance_deflected": catalogs["unbalance"].figure("deflected", speed_rpm=1200.0),
        "time_orbits_3d": catalogs["time"].figure("orbits_3d"),
        "hbm_frequency": catalogs["hbm"].figure("frequency", frequency_units="Hz"),
        "ucs_map": catalogs["ucs"].figure("map"),
        "clearance": catalogs["clearance"].figure(),
    }
    if not all(traces(fig) > 0 for fig in figures.values()):
        raise RuntimeError("One or more native ROSS 0.21 qualification figures contain no Plotly traces.")

    FIGURES.mkdir(parents=True, exist_ok=True)
    for name, figure in figures.items():
        figure.write_html(str(FIGURES / f"{name}.html"), include_plotlyjs=True, full_html=True)

    fr_raw = catalogs["frequency"].raw_arrays()
    ub_raw = catalogs["unbalance"].raw_arrays()
    tr_raw = catalogs["time"].raw_arrays()
    clr_raw = catalogs["clearance"].raw_arrays()
    if not np.all(np.isfinite(np.abs(fr_raw["displacement_frf"]))):
        raise RuntimeError("Frequency-response qualification contains non-finite values.")
    if not np.all(np.isfinite(np.abs(ub_raw["displacement_response"]))):
        raise RuntimeError("Unbalance qualification contains non-finite values.")
    if not np.all(np.isfinite(tr_raw["displacement_time"])):
        raise RuntimeError("Time-response qualification contains non-finite values.")
    if not np.all(np.isfinite(clr_raw["magnitudes_um_pkpk"])):
        raise RuntimeError("Clearance qualification contains non-finite vibration values.")

    payload = {
        "status": "PASS",
        "ross_version": str(ross.__version__),
        "ross_studio_version": __version__,
        "project": project.name,
        "transactions": {
            "frequency_response": list(fr.stage_elapsed_s),
            "unbalance_response": list(ub.stage_elapsed_s),
            "time_response": list(tr.stage_elapsed_s),
            "harmonic_balance": list(hb.stage_elapsed_s),
            "ucs": list(ucs.stage_elapsed_s),
            "clearance": list(clr.stage_elapsed_s),
        },
        "native_output_inventory": {key: list(value) for key, value in TIME_FREQUENCY_NATIVE_OUTPUTS.items()},
        "representative_plot_traces": {key: traces(value) for key, value in figures.items()},
        "frequency_shape": list(fr_raw["displacement_frf"].shape),
        "unbalance_shape": list(ub_raw["displacement_response"].shape),
        "time_shape": list(tr_raw["displacement_time"].shape),
        "hbm_reconstructed_time_cached": catalogs["hbm"].reconstructed_time() is catalogs["hbm"].reconstructed_time(),
        "ucs_critical_mode_count": catalogs["ucs"].critical_mode_count,
        "clearance_rows": [list(row) for row in catalogs["clearance"].rows()],
        "scientific_recompute_from_plotting": any(catalog.scientific_recompute for catalog in catalogs.values()),
    }
    if payload["ross_version"] != "2.3.0":
        raise RuntimeError(f"0.21 is qualified only for ROSS 2.3.0; received {payload['ross_version']}.")
    if payload["ross_studio_version"] != "0.21.0":
        raise RuntimeError(f"Expected ROSS Studio 0.21.0; received {payload['ross_studio_version']}.")
    if payload["scientific_recompute_from_plotting"]:
        raise RuntimeError("Native plot catalog unexpectedly reports scientific recomputation.")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
