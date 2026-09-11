from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .domain import BearingSpec, DiskSpec, LoadSpec, OperatingCase, ProbeSpec, RotorProject, ShaftSection
from .time_frequency_analysis import (
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
from .time_frequency_native import (
    ClearanceNativeCatalog,
    FrequencyResponseNativeCatalog,
    HarmonicBalanceNativeCatalog,
    TimeResponseNativeCatalog,
    UCSNativeCatalog,
    UnbalanceResponseNativeCatalog,
)


@dataclass(slots=True, frozen=True)
class FrozenTimeFrequency021Result:
    status: str
    ross_version: str
    project: str
    frequency_traces: int
    unbalance_traces: int
    time_traces: int
    hbm_traces: int
    ucs_traces: int
    clearance_traces: int
    clearance_rows: int
    scientific_recompute: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _project() -> RotorProject:
    return RotorProject(
        name="Frozen-TF-021",
        shaft_sections=[ShaftSection(1, 1000.0, 50.0, fe_elements=4)],
        bearings=[
            BearingSpec("DE", 0.0, kxx=1e6, kyy=1e6, cxx=500.0, cyy=500.0, metadata={"radial_clearance_m": 100e-6}),
            BearingSpec("NDE", 1000.0, kxx=1e6, kyy=1e6, cxx=500.0, cyy=500.0, metadata={"radial_clearance_m": 120e-6}),
        ],
        disks=[DiskSpec("Rotor", 500.0, 8.0, 0.02, 0.04)],
        loads=[LoadSpec("U1", "unbalance", 500.0, 100.0, 0.0, metadata={"source_unit": "g*mm"})],
        probes=[ProbeSpec("PX", 500.0, 1, 0.0), ProbeSpec("PY", 500.0, 1, 90.0)],
        operating_cases=[OperatingCase("Frozen", 1200.0, 600.0, 1800.0, 20.0)],
    )


def _traces(figure: Any) -> int:
    return len(getattr(figure, "data", ()))


def run_frozen_time_frequency_021_test() -> FrozenTimeFrequency021Result:
    import ross

    if str(ross.__version__) != "2.3.0":
        raise RuntimeError(f"Frozen 0.21 is qualified for ROSS 2.3.0; received {ross.__version__}.")
    project = _project()
    project.validate()

    fr = FrequencyResponseService().run(project, FrequencyResponseRequest(600, 1800, 5, 500, 1, 500, 1))
    ub = UnbalanceResponseService().run(project, UnbalanceResponseRequest(600, 1800, 5))
    tr = TimeResponseService().run(project, TimeResponseRequest(1200, 1200, 0.05, 41, "newmark"))
    hb = HarmonicBalanceService().run(project, HarmonicBalanceRequest(1200, 0.05, 41, 1))
    ucs = UCSService().run(project, UCSRequest(5.0, 8.0, 3, 8, False))
    clr = ClearanceService().run(project, ClearanceRequest(1200, 0.0, 1))

    catalogs = (
        FrequencyResponseNativeCatalog(fr),
        UnbalanceResponseNativeCatalog(ub),
        TimeResponseNativeCatalog(tr),
        HarmonicBalanceNativeCatalog(hb),
        UCSNativeCatalog(ucs),
        ClearanceNativeCatalog(clr),
    )
    figures = (
        catalogs[0].figure("all"),
        catalogs[1].figure("deflected", speed_rpm=1200.0),
        catalogs[2].figure("time_1d"),
        catalogs[3].figure("frequency"),
        catalogs[4].figure("map"),
        catalogs[5].figure(),
    )
    counts = tuple(_traces(fig) for fig in figures)
    if any(value <= 0 for value in counts):
        raise RuntimeError(f"Frozen 0.21 native Plotly trace check failed: {counts}")
    if not np.all(np.isfinite(np.asarray(tr.native.yout, dtype=float))):
        raise RuntimeError("Frozen 0.21 time response contains non-finite values.")
    recompute = any(catalog.scientific_recompute for catalog in catalogs)
    if recompute:
        raise RuntimeError("Plotting unexpectedly reports scientific recomputation in frozen 0.21 runtime.")

    return FrozenTimeFrequency021Result(
        status="PASS",
        ross_version=str(ross.__version__),
        project=project.name,
        frequency_traces=counts[0],
        unbalance_traces=counts[1],
        time_traces=counts[2],
        hbm_traces=counts[3],
        ucs_traces=counts[4],
        clearance_traces=counts[5],
        clearance_rows=len(catalogs[5].rows()),
        scientific_recompute=recompute,
    )


__all__ = ["FrozenTimeFrequency021Result", "run_frozen_time_frequency_021_test"]
