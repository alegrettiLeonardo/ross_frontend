from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .domain import BearingSpec, DiskSpec, OperatingCase, RotorProject, ShaftSection
from .stochastic_analysis import (
    RandomInputSpec,
    StochasticCampbellRequest,
    StochasticFrequencyRequest,
    StochasticRotorService,
    StochasticSamplingConfig,
    StochasticTimeRequest,
    StochasticUnbalanceRequest,
    StochasticVariableSpec,
)
from .stochastic_native import (
    StochasticCampbellCatalog,
    StochasticFrequencyCatalog,
    StochasticInputCatalog,
    StochasticTimeCatalog,
    StochasticUnbalanceCatalog,
)


@dataclass(slots=True, frozen=True)
class FrozenStochastic022Result:
    status: str
    ross_version: str
    project: str
    sample_count: int
    native_st_rotor: bool
    native_input_types: tuple[str, ...]
    input_histogram_traces: int
    campbell_traces: int
    frequency_traces: int
    unbalance_traces: int
    time_1d_traces: int
    time_2d_traces: int
    time_3d_traces: int
    sample_seed_reproducible: bool
    scientific_recompute: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _project() -> RotorProject:
    return RotorProject(
        name="Frozen-Stochastic-022",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec("DE", 0.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
            BearingSpec("NDE", 1000.0, kxx=1.0e6, kyy=1.0e6, cxx=500.0, cyy=500.0),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        operating_cases=[OperatingCase("Frozen", 1200.0, 600.0, 1800.0, 20.0)],
    )


def _traces(figure: Any) -> int:
    return len(getattr(figure, "data", ()))


def run_frozen_stochastic_022_test() -> FrozenStochastic022Result:
    import ross
    import ross.stochastic as srs

    if str(ross.__version__) != "2.3.0":
        raise RuntimeError(f"Frozen 0.22 is qualified for ROSS 2.3.0; received {ross.__version__}.")

    project = _project()
    project.validate()
    sampling = StochasticSamplingConfig(
        samples=2,
        seed=22022,
        variables=(
            StochasticVariableSpec(
                "bearing", 0, "kxx", RandomInputSpec("normal", "relative", 0.0, 1.0)
            ),
        ),
    )
    service = StochasticRotorService()
    first = service.build(project, sampling)
    second = service.build(project, sampling)
    reproducible = all(
        np.allclose(first.sampled_values[key], second.sampled_values[key])
        for key in first.sampled_values
    )
    if not reproducible:
        raise RuntimeError("Frozen 0.22 stochastic seed is not reproducible.")
    if not isinstance(first.stochastic_rotor, srs.ST_Rotor):
        raise RuntimeError("Frozen 0.22 did not instantiate native ross.stochastic.ST_Rotor.")

    input_catalog = StochasticInputCatalog(first)
    plottable = next(
        index
        for index, wrapper in enumerate(first.input_wrappers)
        if tuple(value for value in wrapper.variables if value != "material")
    )
    input_count = _traces(input_catalog.figure(plottable))

    camp = service.run_campbell(project, sampling, StochasticCampbellRequest(600.0, 1200.0, 3, 4))
    camp_catalog = StochasticCampbellCatalog(camp)
    camp_count = _traces(camp_catalog.figure("combined", percentile=[50], conf_interval=[90]))

    fr = service.run_frequency_response(
        project, sampling, StochasticFrequencyRequest(600.0, 1200.0, 4, 2, 1, 2, 1)
    )
    fr_catalog = StochasticFrequencyCatalog(fr)
    fr_count = _traces(fr_catalog.figure("combined", percentile=[50], conf_interval=[90]))

    ub = service.run_unbalance_response(
        project,
        sampling,
        StochasticUnbalanceRequest(
            600.0,
            1200.0,
            4,
            2,
            1.0e-4,
            0.0,
            magnitude_random=RandomInputSpec("uniform", "relative", -1.0, 1.0),
        ),
    )
    ub_catalog = StochasticUnbalanceCatalog(ub)
    ub_count = _traces(ub_catalog.figure("combined", percentile=[50], conf_interval=[90]))

    tr = service.run_time_response(
        project,
        sampling,
        StochasticTimeRequest(
            1200.0,
            0.03,
            16,
            2,
            10.0,
            2.0,
            force_random=RandomInputSpec("normal", "relative", 0.0, 1.0),
        ),
    )
    tr_catalog = StochasticTimeCatalog(tr)
    tr_counts = (
        _traces(tr_catalog.figure("time_1d", percentile=[50], conf_interval=[90])),
        _traces(tr_catalog.figure("orbit_2d", percentile=[50], conf_interval=[90])),
        _traces(tr_catalog.figure("orbits_3d", percentile=[50], conf_interval=[90])),
    )

    counts = (input_count, camp_count, fr_count, ub_count, *tr_counts)
    if any(value <= 0 for value in counts):
        raise RuntimeError(f"Frozen 0.22 native Plotly trace check failed: {counts}")
    if not np.all(np.isfinite(np.asarray(tr.native.yout, dtype=float))):
        raise RuntimeError("Frozen 0.22 stochastic time response contains non-finite values.")
    recompute = any(
        catalog.scientific_recompute
        for catalog in (camp_catalog, fr_catalog, ub_catalog, tr_catalog)
    )
    if recompute:
        raise RuntimeError("Frozen 0.22 plot generation unexpectedly reports scientific recomputation.")

    return FrozenStochastic022Result(
        status="PASS",
        ross_version=str(ross.__version__),
        project=project.name,
        sample_count=first.sample_count,
        native_st_rotor=True,
        native_input_types=tuple(wrapper.native.__class__.__name__ for wrapper in first.input_wrappers),
        input_histogram_traces=input_count,
        campbell_traces=camp_count,
        frequency_traces=fr_count,
        unbalance_traces=ub_count,
        time_1d_traces=tr_counts[0],
        time_2d_traces=tr_counts[1],
        time_3d_traces=tr_counts[2],
        sample_seed_reproducible=reproducible,
        scientific_recompute=recompute,
    )


__all__ = ["FrozenStochastic022Result", "run_frozen_stochastic_022_test"]
