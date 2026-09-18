"""Read-only views of the pinned ROSS 2.3 native results; never re-solve fields."""
from __future__ import annotations

from typing import Any

import numpy as np

UNAVAILABLE = "Not available for this ROSS model"


def native_field(result: Any, name: str, index: int):
    """Return dimensional native pressure/temperature fields for one solved speed."""
    attr = {"Pressure": "pressure_fields", "Temperature": "temperature_fields"}.get(name)
    if attr is None:
        return None
    native = getattr(result.native_element, "_results", None)
    if native is None:
        return None
    fields = getattr(native, attr, ())
    if index >= len(fields):
        return None
    return np.asarray(fields[index], dtype=float)


def convergence(result: Any, index: int) -> dict:
    """Expose native convergence evidence without conflating optimizer and physics criteria."""
    native = result.native_element._results
    omega = float(result.native_element.frequency[index])
    key = omega if result.source_model == "PlainJournal" else index
    history = getattr(native, "optimization_history", {}).get(key, [])
    clean_history = [None if x is None or not np.isfinite(x) else float(x) for x in history]

    if result.source_model == "PlainJournal":
        evidence = result.metadata.get("convergence", [])[index]
        solver = evidence["solver_termination"]
        physical = evidence["physical_equilibrium"]
        return {
            "history": clean_history,
            "samples": len(clean_history),
            "iterations": solver["iterations"],
            "success": solver["success"],
            "message": solver["message"],
            "solver_final_objective_n": solver["final_objective_fun_n"],
            "solver_termination_tolerance": solver["termination_tolerance"],
            "solver_tolerance_semantics": solver["termination_tolerance_semantics"],
            "physical_residual_norm_n": physical["equilibrium_residual_norm_n"],
            "physical_relative_residual": physical["relative_equilibrium_residual"],
            "physical_acceptance_threshold": physical["acceptance_threshold"],
            "physical_status": physical["status"],
            "residual_contract": "PlainJournal physical force-equilibrium norm; solver tol is separate",
        }

    if result.source_model == "ThrustPad":
        evidence = result.metadata.get("convergence", [])[index]
        return {
            "history": list(evidence.get("history", clean_history)),
            "samples": len(evidence.get("history", clean_history)),
            "iterations": evidence.get("recorded_outer_iterations"),
            "success": evidence.get("convergence_state") == "PASS",
            "message": evidence.get("component_availability", UNAVAILABLE),
            "solver_final_objective_n": evidence.get("native_combined_force_moment_objective"),
            "solver_termination_tolerance": evidence.get("requested_tolerance"),
            "solver_tolerance_semantics": "ROSS 2.3 explicit outer force/moment convergence criterion",
            "physical_residual_norm_n": evidence.get("native_combined_force_moment_objective"),
            "physical_relative_residual": None,
            "physical_acceptance_threshold": evidence.get("requested_tolerance"),
            "physical_status": evidence.get("status"),
            "residual_contract": evidence.get("objective_definition", "ROSS native force/moment equilibrium objective"),
        }

    opt = getattr(native, "opt_results", {}).get(key)
    residual = (
        float(opt.fun)
        if opt is not None and np.isfinite(opt.fun)
        else (float(history[-1]) if history and history[-1] is not None and np.isfinite(history[-1]) else None)
    )
    return {
        "history": clean_history,
        "samples": len(clean_history),
        "iterations": int(opt.nit) if opt is not None and hasattr(opt, "nit") else None,
        "success": bool(opt.success) if opt is not None and hasattr(opt, "success") else None,
        "message": str(opt.message) if opt is not None and hasattr(opt, "message") else UNAVAILABLE,
        "solver_final_objective_n": residual,
        "solver_termination_tolerance": None,
        "solver_tolerance_semantics": UNAVAILABLE,
        "physical_residual_norm_n": None,
        "physical_relative_residual": None,
        "physical_acceptance_threshold": None,
        "physical_status": None,
        "residual_contract": (
            "ROSS native objective history; optimizer warnflag/iteration count unavailable in ROSS 2.3 TiltingPad"
            if result.source_model == "TiltingPad"
            else "Not applicable: analytical hydrodynamic SFD has no iterative convergence loop"
        ),
    }
