"""Read-only views of the pinned ROSS 2.3 native results; never re-solve fields."""
from __future__ import annotations

import numpy as np

from .thd_bearing_service import THDBearingCalculationResult

UNAVAILABLE = "Not available for this ROSS model"


def native_field(result: THDBearingCalculationResult, name: str, index: int):
    """Return dimensional (axial, circumferential[, pad]) native fields."""
    attr = {"Pressure": "pressure_fields", "Temperature": "temperature_fields"}.get(name)
    if attr is None:
        return None
    fields = getattr(result.native_element._results, attr, ())
    if index >= len(fields):
        return None
    return np.asarray(fields[index], dtype=float)


def convergence(result: THDBearingCalculationResult, index: int) -> dict:
    native = result.native_element._results
    omega = float(result.native_element.frequency[index])
    key = omega if result.source_model == "PlainJournal" else index
    history = getattr(native, "optimization_history", {}).get(key, [])
    opt = getattr(native, "opt_results", {}).get(key)
    # History samples can be objective evaluations, not optimizer iterations.
    return {
        "history": [None if x is None or not np.isfinite(x) else float(x) for x in history],
        "samples": len(history),
        "iterations": int(opt.nit) if opt is not None and hasattr(opt, "nit") else None,
        "residual_final": float(opt.fun) if opt is not None and np.isfinite(opt.fun) else
            (float(history[-1]) if history and history[-1] is not None and np.isfinite(history[-1]) else None),
        "success": bool(opt.success) if opt is not None and hasattr(opt, "success") else None,
        "message": str(opt.message) if opt is not None and hasattr(opt, "message") else UNAVAILABLE,
        "residual_contract": "force norm (N)" if result.source_model == "PlainJournal" else "ROSS native objective (model-dependent scaling)",
    }
