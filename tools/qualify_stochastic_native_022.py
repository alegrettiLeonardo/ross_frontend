from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ross_studio.domain import BearingSpec, DiskSpec, OperatingCase, RotorProject, ShaftSection
from ross_studio.stochastic_analysis import (
    RandomInputSpec,
    StochasticCampbellRequest,
    StochasticFrequencyRequest,
    StochasticRotorService,
    StochasticSamplingConfig,
    StochasticTimeRequest,
    StochasticUnbalanceRequest,
    StochasticVariableSpec,
)
from ross_studio.stochastic_native import (
    STOCHASTIC_NATIVE_OUTPUTS,
    StochasticCampbellCatalog,
    StochasticFrequencyCatalog,
    StochasticInputCatalog,
    StochasticTimeCatalog,
    StochasticUnbalanceCatalog,
)


def project() -> RotorProject:
    value = RotorProject(
        name="Stochastic-022-qualification",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec("DE", 0.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
            BearingSpec("NDE", 1000.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        operating_cases=[OperatingCase("Q", 1200.0, 600.0, 1800.0, 20.0)],
    )
    value.validate()
    return value


def has_traces(fig) -> bool:
    return len(getattr(fig, "data", ())) > 0


def main() -> int:
    import ross
    import ross.stochastic as srs

    out = Path("artifacts/stochastic_native_022")
    out.mkdir(parents=True, exist_ok=True)
    service = StochasticRotorService()
    cfg = StochasticSamplingConfig(
        samples=3,
        seed=22022,
        variables=(
            StochasticVariableSpec("bearing", 0, "kxx", RandomInputSpec("normal", "relative", 0.0, 2.0)),
            StochasticVariableSpec("disk", 0, "m", RandomInputSpec("uniform", "relative", -1.0, 1.0)),
        ),
    )
    model = project()

    first = service.build(model, cfg)
    second = service.build(model, cfg)
    reproducible = all(np.allclose(first.sampled_values[key], second.sampled_values[key]) for key in first.sampled_values)
    native_types = [wrapper.native.__class__.__name__ for wrapper in first.input_wrappers]
    input_catalog = StochasticInputCatalog(first)
    plottable = next(i for i, wrapper in enumerate(first.input_wrappers) if [v for v in wrapper.variables if v != "material"])
    input_fig = input_catalog.figure(plottable)
    input_fig.write_html(out / "random_variable_histogram.html", include_plotlyjs=True)

    camp = service.run_campbell(model, cfg, StochasticCampbellRequest(600.0, 1200.0, 3, 4))
    camp_catalog = StochasticCampbellCatalog(camp)
    camp_fig = camp_catalog.figure("combined", percentile=[5, 50, 95], conf_interval=[90], harmonics=[0.5, 1.0])
    camp_fig.write_html(out / "campbell_mean_percentile_confidence.html", include_plotlyjs=True)

    fr = service.run_frequency_response(model, cfg, StochasticFrequencyRequest(600.0, 1200.0, 5, 2, 1, 2, 1))
    fr_catalog = StochasticFrequencyCatalog(fr)
    fr_fig = fr_catalog.figure("combined", percentile=[5, 50, 95], conf_interval=[90], amplitude_units="m/N")
    fr_fig.write_html(out / "frequency_response_mean_percentile_confidence.html", include_plotlyjs=True)

    ub = service.run_unbalance_response(
        model,
        cfg,
        StochasticUnbalanceRequest(
            600.0, 1200.0, 5, 2, 1.0e-4, 0.0,
            magnitude_random=RandomInputSpec("uniform", "relative", -2.0, 2.0),
        ),
    )
    ub_catalog = StochasticUnbalanceCatalog(ub)
    ub_fig = ub_catalog.figure("combined", percentile=[5, 50, 95], conf_interval=[90])
    ub_fig.write_html(out / "unbalance_response_mean_percentile_confidence.html", include_plotlyjs=True)

    tr = service.run_time_response(
        model,
        cfg,
        StochasticTimeRequest(
            1200.0, 0.05, 24, 2, 10.0, 2.0,
            force_random=RandomInputSpec("normal", "relative", 0.0, 2.0),
        ),
    )
    tr_catalog = StochasticTimeCatalog(tr)
    tr_1d = tr_catalog.figure("time_1d", percentile=[50], conf_interval=[90])
    tr_2d = tr_catalog.figure("orbit_2d", percentile=[50], conf_interval=[90])
    tr_3d = tr_catalog.figure("orbits_3d", percentile=[50], conf_interval=[90])
    tr_1d.write_html(out / "time_response_1d.html", include_plotlyjs=True)
    tr_2d.write_html(out / "time_response_orbit_2d.html", include_plotlyjs=True)
    tr_3d.write_html(out / "time_response_orbits_3d.html", include_plotlyjs=True)

    native_json = camp_catalog.export_native_result(out / "campbell_native_result.json")

    checks = {
        "ross_version": getattr(ross, "__version__", "unknown"),
        "st_rotor_native": isinstance(first.stochastic_rotor, srs.ST_Rotor),
        "sample_count": first.sample_count,
        "sample_seed_reproducible": reproducible,
        "random_input_native_types": native_types,
        "all_random_arrays_same_size": all(np.asarray(value).shape[-1] == cfg.samples for value in first.sampled_values.values()),
        "random_variable_plot_traces": len(input_fig.data),
        "campbell_plot_traces": len(camp_fig.data),
        "frequency_plot_traces": len(fr_fig.data),
        "unbalance_plot_traces": len(ub_fig.data),
        "time_1d_plot_traces": len(tr_1d.data),
        "time_2d_plot_traces": len(tr_2d.data),
        "time_3d_plot_traces": len(tr_3d.data),
        "campbell_raw_shape": list(camp_catalog.raw_arrays()["natural_frequency_rad_s"].shape),
        "frequency_raw_shape": list(fr_catalog.raw_arrays()["displacement_frf"].shape),
        "unbalance_raw_shape": list(ub_catalog.raw_arrays()["displacement_response"].shape),
        "time_raw_shape": list(tr_catalog.raw_arrays()["displacement_time"].shape),
        "native_save_created": native_json.is_file() and native_json.stat().st_size > 0,
        "scientific_recompute_on_plot_change": False,
        "native_output_inventory": {key: list(value) for key, value in STOCHASTIC_NATIVE_OUTPUTS.items()},
        "random_force_contract": "ROSS_2_3_FIRST_AXIS_IS_RV_SIZE",
        "random_ic_contract": "DOCUMENTED_BUT_NOT_QUALIFIED_IN_ROSS_2_3_IMPLEMENTATION",
        "synthetic_monte_carlo_solver": False,
    }
    mandatory = [
        checks["st_rotor_native"], checks["sample_seed_reproducible"], checks["all_random_arrays_same_size"],
        checks["random_variable_plot_traces"] > 0, checks["campbell_plot_traces"] > 0,
        checks["frequency_plot_traces"] > 0, checks["unbalance_plot_traces"] > 0,
        checks["time_1d_plot_traces"] > 0, checks["time_2d_plot_traces"] > 0,
        checks["time_3d_plot_traces"] > 0, checks["native_save_created"],
    ]
    payload = {"status": "PASS" if all(mandatory) else "FAIL", **checks}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/stochastic_native_022_qualification.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
