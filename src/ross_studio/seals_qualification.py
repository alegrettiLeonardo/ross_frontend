from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Any, Mapping
import warnings

import numpy as np

from .app import RossStudioWindow
from .domain import (
    BearingSpec,
    DiskSpec,
    EngineeringError,
    MaterialSpec,
    OperatingCase,
    RotorProject,
    SealModel,
    SealSpec,
    ShaftSection,
)
from .models import ProjectModel
from .pages.seal_workspace import SealStudioPage
from .pages.static_modal_workspace import StaticModalWorkspacePage
from .project_io import load_project, save_project
from .ross_backend import RossModelBuilder
from .seal_studio_service import SealStudioService


_COEFFS = ("kxx", "kxy", "kyx", "kyy", "cxx", "cxy", "cyx", "cyy")


_INPUTS: dict[SealModel, dict[str, Any]] = {
    SealModel.DIRECT: {
        "frequency_rpm": [1800.0, 3600.0, 5400.0],
        "kxx": [1.13791e6, 1.24823e6, 1.35947e6],
        "kxy": [2.17311e5, 2.28419e5, 2.39527e5],
        "kyx": [-3.21913e5, -3.32817e5, -3.43729e5],
        "kyy": [0.0, 0.0, 0.0],
        "cxx": [1137.91, 1248.23, 1359.47],
        "cxy": [217.311, 228.419, 239.527],
        "cyx": [-321.913, -332.817, -343.729],
        "cyy": [0.0, 0.0, 0.0],
    },
    SealModel.LABYRINTH: {
        "shaft_diameter_mm": 145.0,
        "radial_clearance_mm": 0.30,
        "n_teeth": 16,
        "pitch_mm": 3.175,
        "tooth_height_mm": 3.175,
        "tooth_width_mm": 0.1524,
        "seal_type": "inter",
        "inlet_pressure_bar": 3.08,
        "outlet_pressure_bar": 0.943,
        "inlet_temperature_c": 10.0,
        "frequency_rpm": [5000.0, 8000.0],
        "preswirl": 0.98,
        "gas_composition": {"Nitrogen": 0.79, "Oxygen": 0.21},
        "use_jenny_kanki": False,
    },
    SealModel.HOLE_PATTERN: {
        "shaft_diameter_mm": 145.0,
        "radial_clearance_mm": 0.30,
        "axial_length_mm": 46.99,
        "relative_roughness": 1.0e-4,
        "cell_length_mm": 3.175,
        "cell_width_mm": 3.175,
        "cell_depth_mm": 2.5,
        "inlet_pressure_bar": 6.89,
        "outlet_pressure_bar": 0.943,
        "inlet_temperature_c": 48.85,
        "frequency_rpm": [7000.0, 8000.0],
        "preswirl": 0.8,
        "entrance_loss_coefficient": 0.5,
        "exit_loss_coefficient": 1.0,
        "excitation_ratio": 1.0,
        "nz": 18,
        "max_iterations": 180,
        "tolerance": 1.0e-4,
        "first_step_size": 0.01,
        "relaxation_factor": 0.1,
        "gas_composition": {"Nitrogen": 0.79, "Oxygen": 0.21},
    },
    SealModel.HYBRID: {
        "shaft_diameter_mm": 50.0,
        "inlet_pressure_bar": 5.0,
        "outlet_pressure_bar": 1.0,
        "inlet_temperature_c": 26.85,
        "frequency_rpm": [2000.0, 3000.0],
        "gas_composition": {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092},
        "hole_radial_clearance_mm": 0.30,
        "hole_axial_length_mm": 40.0,
        "hole_relative_roughness": 1.0e-4,
        "hole_cell_length_mm": 3.0,
        "hole_cell_width_mm": 3.0,
        "hole_cell_depth_mm": 2.0,
        "hole_preswirl": 0.8,
        "hole_entrance_loss_coefficient": 0.5,
        "hole_exit_loss_coefficient": 1.0,
        "hole_excitation_ratio": 1.0,
        "hole_nz": 18,
        "hole_max_iterations": 180,
        "hole_tolerance": 1.0e-4,
        "hole_first_step_size": 0.01,
        "hole_relaxation_factor": 0.1,
        "lab_radial_clearance_mm": 0.25,
        "lab_n_teeth": 10,
        "lab_pitch_mm": 3.0,
        "lab_tooth_height_mm": 3.0,
        "lab_tooth_width_mm": 0.15,
        "lab_seal_type": "inter",
        "lab_preswirl": 0.9,
        "tolerance": 1.0e-6,
        "max_iterations": 100,
    },
}


@dataclass(slots=True)
class SealsQualification:
    status: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        result = dict(self.payload)
        result["status"] = self.status
        result["declared_scope"] = (
            "ROSS Studio Seals 0.26 on ross-rotordynamics==2.3.0: native SealElement "
            "frequency-dependent lateral K/C, LabyrinthSeal, HolePatternSeal and HybridSeal; "
            "positive-speed compressible-gas operating states; exact-node rotor assembly; "
            "explicit thermodynamic-backend evidence and fail-closed iterative convergence."
        )
        result["excluded_scope"] = (
            "Liquid seals, user-selected EOS overrides not accepted by the ROSS 2.3.0 native constructors, "
            "zero/negative speed advanced-gas seal operation, non-native seal solvers and scientific "
            "equivalence between REFPROP and HEOS/CoolProp are not claimed."
        )
        return result


def _ensure_qapplication():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["ross-studio-seals-026-qualification"])
    return app


def _rated(model: SealModel) -> float:
    values = _INPUTS[model].get("frequency_rpm", [3600.0])
    return float(values[len(values) // 2])


def _base_model(model: SealModel) -> ProjectModel:
    steel = MaterialSpec(
        name="QUAL-Seal-Steel-026",
        density_kg_m3=7850.0,
        young_pa=207.0e9,
        poisson=0.3,
    )
    speed = [float(item) for item in _INPUTS[model]["frequency_rpm"]]
    rated = _rated(model)
    project = RotorProject(
        name=f"QUAL-Seals-026-{model.value}",
        reference="Seals 0.26 end-to-end feature qualification",
        line="QUAL",
        frame="026",
        poles=2,
        description=f"Deterministic {model.value} seal qualification rotor",
        materials={steel.name: steel},
        shaft_sections=[
            ShaftSection(
                section=1,
                length_mm=600.0,
                od_left_mm=50.0,
                od_right_mm=50.0,
                id_left_mm=0.0,
                id_right_mm=0.0,
                material=steel.name,
                fe_elements=4,
                shear_effects=True,
                rotary_inertia=True,
                gyroscopic=True,
            )
        ],
        bearings=[
            BearingSpec(
                name="QUAL-BRG-L-026",
                position_mm=0.0,
                kxx=8.713e7,
                kyy=9.127e7,
                cxx=871.3,
                cyy=912.7,
            ),
            BearingSpec(
                name="QUAL-BRG-R-026",
                position_mm=600.0,
                kxx=1.031e8,
                kyy=1.117e8,
                cxx=1031.0,
                cyy=1117.0,
            ),
        ],
        disks=[
            DiskSpec(
                name="QUAL-DISK-026",
                position_mm=450.0,
                mass_kg=18.731,
                id_kg_m2=0.08137,
                ip_kg_m2=0.15291,
            )
        ],
        seals=[
            SealSpec(
                name=f"QUAL-SEAL-{model.value}-026",
                position_mm=300.0,
                kxx=0.0,
                kyy=0.0,
                cxx=0.0,
                cyy=0.0,
                kxy=0.0,
                kyx=0.0,
                cxy=0.0,
                cyx=0.0,
                model=model,
            )
        ],
        operating_cases=[
            OperatingCase(
                name=f"{model.value} qualification",
                rated_speed_rpm=rated,
                speed_min_rpm=min(speed),
                speed_max_rpm=max(speed),
                frequency_hz=rated / 60.0,
            )
        ],
    )
    project.validate()
    return ProjectModel.from_engineering(project)


def _encode(value: Any) -> str:
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _find_parameter_row(page: SealStudioPage, key: str) -> int:
    for row in range(page.parameters.rowCount()):
        item = page.parameters.item(row, 0)
        if item is not None and item.text().strip() == key:
            return row
    raise RuntimeError(f"Seal Studio GUI does not expose required parameter {key!r}.")


def _set_gui_inputs(page: SealStudioPage, model: SealModel, values: Mapping[str, Any]) -> dict[str, object]:
    index = page.model.findData(model.value)
    if index < 0:
        raise RuntimeError(f"Seal Studio GUI does not expose model {model.value}.")
    page.model.setCurrentIndex(index)
    for key, value in values.items():
        row = _find_parameter_row(page, key)
        page.parameters.item(row, 1).setText(_encode(value))
    return {
        "model": str(page.model.currentData()),
        "values": deepcopy(page._input_values()),
        "units": {
            "geometry": "mm",
            "pressure": "bar",
            "temperature": "degC",
            "speed": "rpm",
            "stiffness": "N/m",
            "damping": "N*s/m",
        },
    }


def _mutated_text(value: Any) -> str:
    if isinstance(value, list):
        changed = list(value)
        changed[0] = float(changed[0]) * 1.0001 + 1.0e-6
        return _encode(changed)
    if isinstance(value, bool):
        return _encode(not value)
    if isinstance(value, (int, float)):
        return str(float(value) * 1.0001 + 1.0e-6)
    return str(value) + "_changed"


def _stale_preview_gates(page: SealStudioPage, model: SealModel, inputs: Mapping[str, Any], app) -> dict[str, object]:
    key = "kxx" if model is SealModel.DIRECT else (
        "preswirl" if model in {SealModel.LABYRINTH, SealModel.HOLE_PATTERN} else "hole_preswirl"
    )
    row = _find_parameter_row(page, key)
    item = page.parameters.item(row, 1)
    original = item.text()

    page.calculate.click()
    app.processEvents()
    if page.preview is None or not page.apply.isEnabled():
        raise RuntimeError(f"{model.value}: nominal Calculate did not produce a Ready preview: {page.state.text()}")

    item.setText(_mutated_text(inputs[key]))
    app.processEvents()
    normal_pass = page.preview is None and not page.apply.isEnabled()

    item.setText(original)
    page.calculate.click()
    app.processEvents()
    if page.preview is None or not page.apply.isEnabled():
        raise RuntimeError(f"{model.value}: second Calculate failed before blocked-signal stale test: {page.state.text()}")

    page.parameters.blockSignals(True)
    try:
        item.setText(_mutated_text(inputs[key]))
    finally:
        page.parameters.blockSignals(False)
    suppressed_signal_left_preview = page.preview is not None and page.apply.isEnabled()
    page.apply.click()
    app.processEvents()
    blocked_pass = (
        suppressed_signal_left_preview
        and page.preview is None
        and not page.apply.isEnabled()
        and "inputs changed" in page.state.text().casefold()
    )

    item.setText(original)
    page.calculate.click()
    app.processEvents()
    if page.preview is None or not page.apply.isEnabled():
        raise RuntimeError(f"{model.value}: final Calculate failed before Apply: {page.state.text()}")
    return {
        "scientific_field": key,
        "qt_signal_path_invalidated": normal_pass,
        "blocked_signals_preview_was_still_present_before_apply": suppressed_signal_left_preview,
        "apply_fingerprint_rejected_blocked_signal_change": blocked_pass,
        "pass": bool(normal_pass and blocked_pass),
    }


def _manual_seal(rs, model: SealModel, value: Mapping[str, Any], *, node: int):
    if model is SealModel.DIRECT:
        frequency = np.asarray(value["frequency_rpm"], dtype=float) * 2.0 * pi / 60.0
        return rs.SealElement(
            n=node,
            frequency=frequency,
            kxx=np.asarray(value["kxx"], dtype=float),
            kyy=np.asarray(value["kyy"], dtype=float),
            kxy=np.asarray(value["kxy"], dtype=float),
            kyx=np.asarray(value["kyx"], dtype=float),
            cxx=np.asarray(value["cxx"], dtype=float),
            cyy=np.asarray(value["cyy"], dtype=float),
            cxy=np.asarray(value["cxy"], dtype=float),
            cyx=np.asarray(value["cyx"], dtype=float),
            tag=f"QUAL-SEAL-{model.value}-026",
        )

    common = dict(
        n=node,
        shaft_radius=float(value["shaft_diameter_mm"]) / 2000.0,
        inlet_pressure=float(value["inlet_pressure_bar"]) * 1.0e5,
        outlet_pressure=float(value["outlet_pressure_bar"]) * 1.0e5,
        inlet_temperature=float(value["inlet_temperature_c"]) + 273.15,
        frequency=np.asarray(value["frequency_rpm"], dtype=float) * 2.0 * pi / 60.0,
        gas_composition=value["gas_composition"],
        tag=f"QUAL-SEAL-{model.value}-026",
    )
    if model is SealModel.LABYRINTH:
        from ross.seals.labyrinth_seal import LabyrinthSeal
        return LabyrinthSeal(
            **common,
            radial_clearance=float(value["radial_clearance_mm"]) / 1000.0,
            n_teeth=int(value["n_teeth"]),
            pitch=float(value["pitch_mm"]) / 1000.0,
            tooth_height=float(value["tooth_height_mm"]) / 1000.0,
            tooth_width=float(value["tooth_width_mm"]) / 1000.0,
            seal_type=str(value["seal_type"]),
            preswirl=float(value["preswirl"]),
            iopt1=int(bool(value["use_jenny_kanki"])),
        )
    if model is SealModel.HOLE_PATTERN:
        from ross.seals.holepattern_seal import HolePatternSeal
        return HolePatternSeal(
            **common,
            radial_clearance=float(value["radial_clearance_mm"]) / 1000.0,
            length=float(value["axial_length_mm"]) / 1000.0,
            roughness=float(value["relative_roughness"]),
            cell_length=float(value["cell_length_mm"]) / 1000.0,
            cell_width=float(value["cell_width_mm"]) / 1000.0,
            cell_depth=float(value["cell_depth_mm"]) / 1000.0,
            preswirl=float(value["preswirl"]),
            entr_coef=float(value["entrance_loss_coefficient"]),
            exit_coef=float(value["exit_loss_coefficient"]),
            whirl_ratio=float(value["excitation_ratio"]),
            nz=int(value["nz"]),
            max_iterations=int(value["max_iterations"]),
            tolerance=float(value["tolerance"]),
            first_step_size=float(value["first_step_size"]),
            rlx_factor=float(value["relaxation_factor"]),
        )

    from ross.seals.hybrid_seal import HybridSeal
    hole = {
        "radial_clearance": float(value["hole_radial_clearance_mm"]) / 1000.0,
        "length": float(value["hole_axial_length_mm"]) / 1000.0,
        "roughness": float(value["hole_relative_roughness"]),
        "cell_length": float(value["hole_cell_length_mm"]) / 1000.0,
        "cell_width": float(value["hole_cell_width_mm"]) / 1000.0,
        "cell_depth": float(value["hole_cell_depth_mm"]) / 1000.0,
        "preswirl": float(value["hole_preswirl"]),
        "entr_coef": float(value["hole_entrance_loss_coefficient"]),
        "exit_coef": float(value["hole_exit_loss_coefficient"]),
        "whirl_ratio": float(value["hole_excitation_ratio"]),
        "nz": int(value["hole_nz"]),
        "max_iterations": int(value["hole_max_iterations"]),
        "tolerance": float(value["hole_tolerance"]),
        "first_step_size": float(value["hole_first_step_size"]),
        "rlx_factor": float(value["hole_relaxation_factor"]),
    }
    lab = {
        "radial_clearance": float(value["lab_radial_clearance_mm"]) / 1000.0,
        "n_teeth": int(value["lab_n_teeth"]),
        "pitch": float(value["lab_pitch_mm"]) / 1000.0,
        "tooth_height": float(value["lab_tooth_height_mm"]) / 1000.0,
        "tooth_width": float(value["lab_tooth_width_mm"]) / 1000.0,
        "seal_type": str(value["lab_seal_type"]),
        "preswirl": float(value["lab_preswirl"]),
    }
    return HybridSeal(
        **common,
        hole_pattern_parameters=hole,
        labyrinth_parameters=lab,
        tolerance=float(value["tolerance"]),
        max_iterations=int(value["max_iterations"]),
    )


def _manual_rotor(rs, seal=None):
    steel = rs.Material(
        name="QUAL-Seal-Steel-026",
        rho=7850.0,
        E=207.0e9,
        G_s=207.0e9 / (2.0 * 1.3),
    )
    shaft = [
        rs.ShaftElement(
            L=0.15,
            idl=0.0,
            odl=0.05,
            idr=0.0,
            odr=0.05,
            material=steel,
            n=index,
            shear_effects=True,
            rotary_inertia=True,
            gyroscopic=True,
        )
        for index in range(4)
    ]
    disk = rs.DiskElement(3, 18.731, 0.08137, 0.15291, tag="QUAL-DISK-026")
    bearings = [
        rs.BearingElement(n=0, kxx=8.713e7, kyy=9.127e7, cxx=871.3, cyy=912.7, tag="QUAL-BRG-L-026"),
        rs.BearingElement(n=4, kxx=1.031e8, kyy=1.117e8, cxx=1031.0, cyy=1117.0, tag="QUAL-BRG-R-026"),
    ]
    if seal is not None:
        bearings.append(seal)
    return rs.Rotor(
        shaft_elements=shaft,
        disk_elements=[disk],
        bearing_elements=bearings,
        tag="QUAL-Seals-026-manual",
    )


def _coefficient_row(element, rpm: float) -> dict[str, float]:
    omega = float(rpm) * 2.0 * pi / 60.0
    k = np.asarray(element.K(omega), dtype=float)
    c = np.asarray(element.C(omega), dtype=float)
    return {
        "kxx": float(k[0, 0]),
        "kxy": float(k[0, 1]),
        "kyx": float(k[1, 0]),
        "kyy": float(k[1, 1]),
        "cxx": float(c[0, 0]),
        "cxy": float(c[0, 1]),
        "cyx": float(c[1, 0]),
        "cyy": float(c[1, 1]),
    }


def _parity_rows(studio, direct, rpms: list[float]) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    passed = True
    for rpm in rpms:
        a = _coefficient_row(studio, rpm)
        b = _coefficient_row(direct, rpm)
        for quantity in _COEFFS:
            atol = 1.0e-6 if quantity.startswith("k") else 1.0e-9
            rtol = 1.0e-9
            absolute = abs(a[quantity] - b[quantity])
            relative = absolute / max(abs(b[quantity]), atol)
            ok = bool(np.isclose(a[quantity], b[quantity], rtol=rtol, atol=atol))
            passed &= ok
            rows.append(
                {
                    "rpm": rpm,
                    "quantity": quantity,
                    "studio": a[quantity],
                    "independent_ross": b[quantity],
                    "absolute_error": absolute,
                    "relative_error": relative,
                    "rtol": rtol,
                    "atol": atol,
                    "pass": ok,
                }
            )
    return rows, passed


def _matrix_delta(with_seal, without_seal, omega: float) -> dict[str, object]:
    matrices = {
        "M": (np.asarray(with_seal.M(omega)), np.asarray(without_seal.M(omega))),
        "K": (np.asarray(with_seal.K(omega)), np.asarray(without_seal.K(omega))),
        "C": (np.asarray(with_seal.C(omega)), np.asarray(without_seal.C(omega))),
        "G": (np.asarray(with_seal.G()), np.asarray(without_seal.G())),
    }
    result: dict[str, object] = {}
    for name, (actual, baseline) in matrices.items():
        delta = actual - baseline
        result[name] = {
            "frobenius_norm_delta": float(np.linalg.norm(delta)),
            "max_abs_delta": float(np.max(np.abs(delta))),
        }
    result["required_k_changed"] = bool(result["K"]["frobenius_norm_delta"] > 0.0)
    result["required_c_changed"] = bool(result["C"]["frobenius_norm_delta"] > 0.0)
    result["pass"] = bool(result["required_k_changed"] and result["required_c_changed"])
    return result


def _native_constructor_evidence(model: SealModel, value: Mapping[str, Any], native) -> dict[str, object]:
    if model is SealModel.DIRECT:
        return {
            "frequency_rpm": list(value["frequency_rpm"]),
            "frequency_rad_s": [float(item) for item in np.asarray(native.frequency, dtype=float)],
            "Kyy_zero_preserved": bool(np.all(np.asarray(value["kyy"], dtype=float) == 0.0)),
            "Cyy_zero_preserved": bool(np.all(np.asarray(value["cyy"], dtype=float) == 0.0)),
        }
    if model is SealModel.HYBRID:
        lab = native.laby
        hole = native.hole_pattern
        return {
            "gui_shaft_diameter_mm": float(value["shaft_diameter_mm"]),
            "ross_shaft_radius_m": float(hole.shaft_radius),
            "gui_hole_clearance_mm": float(value["hole_radial_clearance_mm"]),
            "ross_hole_clearance_m": float(hole.radial_clearance),
            "gui_hole_length_mm": float(value["hole_axial_length_mm"]),
            "ross_hole_length_m": float(hole.length),
            "gui_lab_clearance_mm": float(value["lab_radial_clearance_mm"]),
            "ross_lab_clearance_m": float(np.asarray(lab.radial_clearance).ravel()[0]),
            "gui_inlet_pressure_bar": float(value["inlet_pressure_bar"]),
            "ross_inlet_pressure_pa": float(hole.inlet_pressure),
            "gui_outlet_pressure_bar": float(value["outlet_pressure_bar"]),
            "ross_outlet_pressure_pa": float(lab.outlet_pressure),
            "gui_inlet_temperature_c": float(value["inlet_temperature_c"]),
            "ross_inlet_temperature_k": float(hole.inlet_temperature),
            "gui_frequency_rpm": list(value["frequency_rpm"]),
            "ross_frequency_rad_s": [float(item) for item in np.asarray(native.frequency, dtype=float)],
            "fluid": deepcopy(value["gas_composition"]),
        }
    result = {
        "gui_shaft_diameter_mm": float(value["shaft_diameter_mm"]),
        "ross_shaft_radius_m": float(native.shaft_radius),
        "gui_inlet_pressure_bar": float(value["inlet_pressure_bar"]),
        "ross_inlet_pressure_pa": float(native.inlet_pressure),
        "gui_outlet_pressure_bar": float(value["outlet_pressure_bar"]),
        "ross_outlet_pressure_pa": float(native.outlet_pressure),
        "gui_inlet_temperature_c": float(value["inlet_temperature_c"]),
        "ross_inlet_temperature_k": float(native.inlet_temperature),
        "gui_frequency_rpm": list(value["frequency_rpm"]),
        "ross_frequency_rad_s": [float(item) for item in np.asarray(native.frequency, dtype=float)],
        "fluid": deepcopy(value["gas_composition"]),
    }
    if model is SealModel.LABYRINTH:
        result.update(
            {
                "gui_clearance_mm": float(value["radial_clearance_mm"]),
                "ross_clearance_m": float(np.asarray(native.radial_clearance).ravel()[0]),
                "gui_pitch_mm": float(value["pitch_mm"]),
                "ross_pitch_m": float(np.asarray(native.pitch).ravel()[0]),
                "n_teeth": int(native.n_teeth),
                "derived_axial_span_m": float(native.n_teeth * np.asarray(native.pitch).ravel()[0]),
            }
        )
    else:
        result.update(
            {
                "gui_clearance_mm": float(value["radial_clearance_mm"]),
                "ross_clearance_m": float(native.radial_clearance),
                "gui_length_mm": float(value["axial_length_mm"]),
                "ross_length_m": float(native.length),
                "cell_length_m": float(native.cell_length),
                "cell_width_m": float(native.cell_width),
                "cell_depth_m": float(native.cell_depth),
                "nz": int(native.nz),
                "max_iterations": int(native.max_iterations),
                "tolerance": float(native.tolerance),
            }
        )
    return result


def _conversion_pass(model: SealModel, evidence: Mapping[str, object]) -> bool:
    if model is SealModel.DIRECT:
        rpm = np.asarray(evidence["frequency_rpm"], dtype=float)
        omega = np.asarray(evidence["frequency_rad_s"], dtype=float)
        return bool(np.allclose(omega, rpm * 2.0 * pi / 60.0) and evidence["Kyy_zero_preserved"] and evidence["Cyy_zero_preserved"])
    checks = [
        np.isclose(float(evidence["ross_shaft_radius_m"]), float(evidence["gui_shaft_diameter_mm"]) / 2000.0),
        np.isclose(float(evidence["ross_inlet_pressure_pa"]), float(evidence["gui_inlet_pressure_bar"]) * 1.0e5),
        np.isclose(float(evidence["ross_outlet_pressure_pa"]), float(evidence["gui_outlet_pressure_bar"]) * 1.0e5),
        np.isclose(float(evidence["ross_inlet_temperature_k"]), float(evidence["gui_inlet_temperature_c"]) + 273.15),
        np.allclose(
            np.asarray(evidence["ross_frequency_rad_s"], dtype=float),
            np.asarray(evidence["gui_frequency_rpm"], dtype=float) * 2.0 * pi / 60.0,
        ),
    ]
    if model is SealModel.HYBRID:
        checks.extend(
            [
                np.isclose(float(evidence["ross_hole_clearance_m"]), float(evidence["gui_hole_clearance_mm"]) / 1000.0),
                np.isclose(float(evidence["ross_hole_length_m"]), float(evidence["gui_hole_length_mm"]) / 1000.0),
                np.isclose(float(evidence["ross_lab_clearance_m"]), float(evidence["gui_lab_clearance_mm"]) / 1000.0),
            ]
        )
    else:
        checks.append(
            np.isclose(float(evidence["ross_clearance_m"]), float(evidence["gui_clearance_mm"]) / 1000.0)
        )
        if model is SealModel.LABYRINTH:
            checks.append(
                np.isclose(float(evidence["ross_pitch_m"]), float(evidence["gui_pitch_mm"]) / 1000.0)
            )
        else:
            checks.append(
                np.isclose(float(evidence["ross_length_m"]), float(evidence["gui_length_mm"]) / 1000.0)
            )
    return bool(all(checks))


def _wait_modal(page: StaticModalWorkspacePage, app, *, timeout_s: float = 180.0) -> None:
    page.num_modes.setValue(12)
    page.campbell_points.setValue(5)
    page.campbell_frequencies.setValue(2)
    page.run_modal()
    deadline = time.monotonic() + timeout_s
    while page._modal_thread is not None and page._modal_thread.isRunning():
        app.processEvents()
        time.sleep(0.01)
        if time.monotonic() > deadline:
            page._modal_thread.requestInterruption()
            raise RuntimeError("Timed out waiting for real GUI Modal/Campbell worker.")
    app.processEvents()
    if page.modal_result is None:
        raise RuntimeError(f"GUI Modal/Campbell did not produce a current result: {page.modal_state.text()}")


def _scientific_mutation(spec: SealSpec) -> None:
    data = spec.metadata.get("engineering_input")
    if not isinstance(data, dict):
        spec.kxx += 17.0
        return
    if spec.model is SealModel.DIRECT:
        values = list(data["kxx"])
        values[0] = float(values[0]) + 17.0
        data["kxx"] = values
    elif spec.model is SealModel.LABYRINTH:
        data["radial_clearance_mm"] = float(data["radial_clearance_mm"]) * 1.001
    elif spec.model is SealModel.HOLE_PATTERN:
        data["cell_depth_mm"] = float(data["cell_depth_mm"]) * 1.001
    else:
        data["hole_radial_clearance_mm"] = float(data["hole_radial_clearance_mm"]) * 1.001


def _validation_regressions(service: SealStudioService) -> dict[str, object]:
    model = _base_model(SealModel.HOLE_PATTERN)
    project = model.engineering
    assert project is not None
    base = deepcopy(_INPUTS[SealModel.HOLE_PATTERN])
    cases: list[tuple[str, dict[str, Any]]] = []
    for label, key, value in (
        ("nan_geometry", "radial_clearance_mm", float("nan")),
        ("inf_geometry", "cell_depth_mm", float("inf")),
        ("zero_clearance", "radial_clearance_mm", 0.0),
        ("pressure_ordering", "outlet_pressure_bar", 99.0),
        ("absolute_temperature", "inlet_temperature_c", -273.15),
        ("nonmonotonic_frequency", "frequency_rpm", [8000.0, 7000.0]),
        ("invalid_tolerance", "tolerance", 0.0),
        ("invalid_max_iterations", "max_iterations", 0),
    ):
        row = deepcopy(base)
        row[key] = value
        cases.append((label, row))
    mismatch = deepcopy(_INPUTS[SealModel.DIRECT])
    mismatch["kxx"] = [1.0, 2.0]
    direct_model = _base_model(SealModel.DIRECT)
    direct_project = direct_model.engineering
    assert direct_project is not None
    results: dict[str, object] = {}
    for label, row in cases:
        try:
            service.normalize_inputs(project, project.seals[0], SealModel.HOLE_PATTERN, row)
        except EngineeringError as exc:
            results[label] = {"pass": True, "message": str(exc)}
        else:
            results[label] = {"pass": False, "message": "unexpectedly accepted"}
    try:
        service.normalize_inputs(direct_project, direct_project.seals[0], SealModel.DIRECT, mismatch)
    except EngineeringError as exc:
        results["mismatched_coefficient_arrays"] = {"pass": True, "message": str(exc)}
    else:
        results["mismatched_coefficient_arrays"] = {"pass": False, "message": "unexpectedly accepted"}
    results["pass"] = all(bool(value["pass"]) for key, value in results.items() if key != "pass")
    return results


class _FailingHole:
    def __init__(self, *args, **kwargs) -> None:
        warnings.warn("Error calculating for frequency 733.0 RPM: synthetic upstream failure", RuntimeWarning)
        self.frequency = np.atleast_1d(kwargs.get("frequency", [1.0])).astype(float)
        self.seal_leakage = np.zeros(len(self.frequency))
        self.p = [np.zeros(8) for _ in self.frequency]

    def K(self, frequency):
        return np.zeros((3, 3))

    def C(self, frequency):
        return np.zeros((3, 3))


class _FailingHoleService(SealStudioService):
    @staticmethod
    def _class(module: str, name: str):
        if name == "HolePatternSeal":
            return _FailingHole
        return SealStudioService._class(module, name)


def _hole_failure_regression() -> dict[str, object]:
    model = _base_model(SealModel.HOLE_PATTERN)
    project = model.engineering
    assert project is not None
    try:
        _FailingHoleService().calculate(
            project,
            0,
            SealModel.HOLE_PATTERN,
            _INPUTS[SealModel.HOLE_PATTERN],
        )
    except EngineeringError as exc:
        message = str(exc)
        return {
            "pass": "failure warning" in message.casefold() or "all-zero" in message.casefold(),
            "message": message,
            "preview_ready": False,
            "apply_enabled": False,
        }
    return {
        "pass": False,
        "message": "Synthetic ROSS 2.3.0 warning+zero failure signature was accepted.",
        "preview_ready": True,
        "apply_enabled": True,
    }


def _hybrid_nonconvergence_regression() -> dict[str, object]:
    model = _base_model(SealModel.HYBRID)
    project = model.engineering
    assert project is not None
    values = deepcopy(_INPUTS[SealModel.HYBRID])
    values["max_iterations"] = 1
    values["tolerance"] = 1.0e-14
    try:
        SealStudioService().calculate(project, 0, SealModel.HYBRID, values)
    except EngineeringError as exc:
        return {
            "pass": True,
            "message": str(exc),
            "requested_tolerance": values["tolerance"],
            "max_iterations": values["max_iterations"],
            "preview_ready": False,
            "apply_enabled": False,
        }
    return {
        "pass": False,
        "message": "Hybrid max_iterations=1 / tolerance=1e-14 unexpectedly accepted.",
        "requested_tolerance": values["tolerance"],
        "max_iterations": values["max_iterations"],
        "preview_ready": True,
        "apply_enabled": True,
    }


def _physical_variation(service: SealStudioService, model: SealModel) -> dict[str, object]:
    if model is SealModel.DIRECT:
        return {
            "pass": True,
            "basis": "Frequency-table interpolation already supplies controlled frequency variation.",
        }
    project_model = _base_model(model)
    project = project_model.engineering
    assert project is not None
    nominal = deepcopy(_INPUTS[model])
    varied = deepcopy(nominal)
    key = "radial_clearance_mm" if model in {SealModel.LABYRINTH, SealModel.HOLE_PATTERN} else "hole_radial_clearance_mm"
    varied[key] = float(varied[key]) * 1.05
    nominal_result = service.calculate(project, 0, model, nominal)
    varied_result = service.calculate(project, 0, model, varied)
    a = np.asarray([
        getattr(nominal_result.coefficients[0], name)
        for name in _COEFFS
    ], dtype=float)
    b = np.asarray([
        getattr(varied_result.coefficients[0], name)
        for name in _COEFFS
    ], dtype=float)
    return {
        "input_changed": key,
        "nominal": float(nominal[key]),
        "varied": float(varied[key]),
        "finite_nominal": bool(np.all(np.isfinite(a))),
        "finite_varied": bool(np.all(np.isfinite(b))),
        "coefficient_delta_norm": float(np.linalg.norm(b - a)),
        "pass": bool(np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and np.linalg.norm(b - a) > 0.0),
        "note": "Sensitivity only; no universal monotonic trend is asserted.",
    }


def _qualify_model(rs, model: SealModel, app, *, frozen_mode: bool) -> dict[str, object]:
    model_data = _base_model(model)
    project = model_data.engineering
    if project is None:
        raise RuntimeError("Qualification model lost its engineering RotorProject.")

    window = RossStudioWindow()
    window.project = model_data
    window.show()
    app.processEvents()
    window._navigate("model.seals")
    app.processEvents()
    page = window.stack.currentWidget()
    if not isinstance(page, SealStudioPage):
        raise RuntimeError(f"Main-window model.seals route returned {type(page).__name__}, expected SealStudioPage.")

    gui_input = _set_gui_inputs(page, model, _INPUTS[model])
    stale_preview = _stale_preview_gates(page, model, _INPUTS[model], app)

    if page.preview is None:
        raise RuntimeError(f"{model.value}: final preview unexpectedly absent.")
    preview = page.preview
    native_preview = preview.native_element
    normalized = deepcopy(preview.applied_spec.metadata["engineering_input"])

    constructor = _native_constructor_evidence(model, normalized, native_preview)
    units_pass = _conversion_pass(model, constructor)

    independent = _manual_seal(rs, model, normalized, node=2)
    rpms = [float(item) for item in normalized["frequency_rpm"]]
    if len(rpms) >= 2:
        rpms = [rpms[0], 0.5 * (rpms[0] + rpms[1]), *rpms[1:]]
    parity, parity_pass = _parity_rows(native_preview, independent, rpms)

    zero_preservation = True
    if model is SealModel.DIRECT:
        zero_preservation = all(
            row["quantity"] not in {"kyy", "cyy"} or (row["studio"] == 0.0 and row["independent_ross"] == 0.0)
            for row in parity
        )

    page.apply.click()
    app.processEvents()
    applied = project.seals[0]
    apply_pass = (
        not page.apply.isEnabled()
        and page.preview is None
        and "Applied" in page.state.text()
        and applied.model is model
        and isinstance(applied.metadata.get("engineering_input"), dict)
    )
    if not apply_pass:
        raise RuntimeError(f"{model.value}: real GUI Apply failed: {page.state.text()}")

    build = RossModelBuilder(rs).build(project, strict=True)
    native_rotor_seals = [
        element for element in build.rotor.bearing_elements
        if type(element).__name__ in {"SealElement", "LabyrinthSeal", "HolePatternSeal", "HybridSeal"}
        and getattr(element, "tag", None) == applied.name
    ]
    if len(native_rotor_seals) != 1:
        raise RuntimeError(f"{model.value}: expected exactly one assembled native seal, found {len(native_rotor_seals)}.")
    assembled = native_rotor_seals[0]
    seal_node = build.node_insertion_plan.node_for(applied.position_mm)
    node_pass = seal_node == 2 and int(assembled.n) == 2

    independent_rotor = _manual_rotor(rs, independent)
    no_seal_rotor = _manual_rotor(rs, None)
    omega = _rated(model) * 2.0 * pi / 60.0
    matrix_delta = _matrix_delta(build.rotor, no_seal_rotor, omega)
    global_parity = {
        "K_max_abs_error": float(np.max(np.abs(build.rotor.K(omega) - independent_rotor.K(omega)))),
        "C_max_abs_error": float(np.max(np.abs(build.rotor.C(omega) - independent_rotor.C(omega)))),
    }
    global_parity["pass"] = bool(
        np.allclose(build.rotor.K(omega), independent_rotor.K(omega), rtol=1.0e-9, atol=1.0e-5)
        and np.allclose(build.rotor.C(omega), independent_rotor.C(omega), rtol=1.0e-9, atol=1.0e-8)
    )

    modal = build.rotor.run_modal(speed=omega, num_modes=12)
    modal_values = np.asarray(modal.wd, dtype=float)
    solver_pass = bool(np.any(np.isfinite(modal_values) & (modal_values > 0.0)))

    window._navigate("analysis.static_modal.lateral")
    app.processEvents()
    analysis_page = window.stack.currentWidget()
    if not isinstance(analysis_page, StaticModalWorkspacePage):
        raise RuntimeError(f"Main-window analysis route returned {type(analysis_page).__name__}.")
    analysis_page.speed_rpm.setValue(_rated(model))
    _wait_modal(analysis_page, app, timeout_s=240.0 if frozen_mode else 180.0)
    gui_result = {
        "row_count": analysis_page.mode_table.rowCount(),
        "state": analysis_page.modal_state.text(),
        "first_wd_hz": (
            analysis_page.mode_table.item(0, 3).text()
            if analysis_page.mode_table.rowCount() and analysis_page.mode_table.item(0, 3)
            else ""
        ),
    }
    gui_result["pass"] = bool(gui_result["row_count"] > 0 and gui_result["first_wd_hz"])

    saved_spec = deepcopy(project.seals[0])
    _scientific_mutation(project.seals[0])
    analysis_page._invalidate_if_project_changed()
    stale_result_pass = (
        analysis_page.modal_result is None
        and "invalidated" in analysis_page.modal_state.text().casefold()
    )
    project.seals[0] = deepcopy(saved_spec)

    analysis_page.run_modal()
    if analysis_page._modal_thread is None:
        raise RuntimeError("GUI async-race gate did not start a Modal worker.")
    _scientific_mutation(project.seals[0])
    race_deadline = time.monotonic() + (240.0 if frozen_mode else 180.0)
    while analysis_page._modal_thread is not None and analysis_page._modal_thread.isRunning():
        app.processEvents()
        time.sleep(0.01)
        if time.monotonic() > race_deadline:
            analysis_page._modal_thread.requestInterruption()
            raise RuntimeError("Timed out waiting for stale Modal worker in async-race gate.")
    app.processEvents()
    late_worker_pass = (
        analysis_page.modal_result is None
        and "discarded" in analysis_page.modal_state.text().casefold()
    )
    project.seals[0] = deepcopy(saved_spec)

    with TemporaryDirectory() as temp:
        path = save_project(model_data, Path(temp) / f"{model.value.lower()}_026.rossproj")
        reopened_model = load_project(path)
        reopened = reopened_model.engineering
        if reopened is None:
            raise RuntimeError("Reopened project lost engineering domain.")
        rebuilt = RossModelBuilder(rs).build(reopened, strict=True)
        reopened_spec = reopened.seals[0]
        persistence = {
            "model_type_equal": reopened_spec.model == saved_spec.model,
            "engineering_input_equal": reopened_spec.metadata.get("engineering_input") == saved_spec.metadata.get("engineering_input"),
            "thermodynamic_backend_equal": reopened_spec.metadata.get("thermodynamic_backend") == saved_spec.metadata.get("thermodynamic_backend"),
            "scalar_kc_equal": all(
                np.isclose(float(getattr(reopened_spec, key)), float(getattr(saved_spec, key)))
                for key in _COEFFS
            ),
            "rebuilt_native_class": type(
                next(
                    element for element in rebuilt.rotor.bearing_elements
                    if getattr(element, "tag", None) == saved_spec.name
                )
            ).__name__,
        }
        persistence["pass"] = bool(
            persistence["model_type_equal"]
            and persistence["engineering_input_equal"]
            and persistence["thermodynamic_backend_equal"]
            and persistence["scalar_kc_equal"]
        )

    backend = deepcopy(preview.fluid_backend)
    convergence = {
        "residual": preview.residual,
        "iterations": preview.iterations,
        "native_warnings": list(preview.native_warnings),
    }
    if model is SealModel.HYBRID:
        history = list(getattr(native_preview, "convergence_history", ()) or ())
        lab = list(getattr(native_preview, "leakage_laby_history", ()) or ())
        hole = list(getattr(native_preview, "leakage_hole_history", ()) or ())
        convergence.update(
            {
                "requested_tolerance": float(normalized["tolerance"]),
                "max_iterations": int(normalized["max_iterations"]),
                "history_length": len(history),
                "final_labyrinth_mass_flow": float(lab[-1]),
                "final_hole_mass_flow": float(hole[-1]),
                "independent_mass_flow_residual": abs(float(lab[-1]) - float(hole[-1])) / abs(float(hole[-1])),
            }
        )
        convergence["pass"] = bool(
            preview.residual is not None
            and np.isfinite(preview.residual)
            and preview.residual <= float(normalized["tolerance"])
            and convergence["independent_mass_flow_residual"] <= float(normalized["tolerance"])
            and int(preview.iterations or 0) <= int(normalized["max_iterations"])
        )
    elif model is SealModel.HOLE_PATTERN:
        convergence.update(
            {
                "requested_tolerance": float(normalized["tolerance"]),
                "pressure_residual": preview.residual,
            }
        )
        convergence["pass"] = bool(
            preview.residual is None
            or (np.isfinite(preview.residual) and preview.residual <= float(normalized["tolerance"]))
        )
    else:
        convergence["pass"] = True

    page.close()
    analysis_page.close()
    window.close()
    app.processEvents()

    gates = {
        "gui_input_to_preview_apply": bool(apply_pass),
        "units_to_native_constructor": bool(units_pass),
        "numeric_parity": bool(parity_pass and zero_preservation),
        "exact_node_rotor_assembly": bool(node_pass),
        "global_matrix_delta": bool(matrix_delta["pass"]),
        "global_independent_ross_parity": bool(global_parity["pass"]),
        "native_solver_result": bool(solver_pass),
        "gui_analysis_result": bool(gui_result["pass"]),
        "save_reopen_recompute": bool(persistence["pass"]),
        "stale_preview_and_blocked_signals": bool(stale_preview["pass"]),
        "stale_analysis_result": bool(stale_result_pass),
        "late_worker_result_rejected": bool(late_worker_pass),
        "convergence": bool(convergence["pass"]),
        "thermodynamic_backend_visible": bool(
            model is SealModel.DIRECT
            or (
                isinstance(backend, dict)
                and backend.get("actual_backend")
                and "fallback_occurred" in backend
                and "warning" in backend
            )
        ),
    }
    passed = all(gates.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "gates": gates,
        "gui_input": gui_input,
        "constructor_and_unit_conversion": constructor,
        "parity": parity,
        "zero_preservation": zero_preservation,
        "rotor_node": {
            "position_mm": applied.position_mm,
            "expected_node": 2,
            "actual_node": int(assembled.n),
        },
        "global_matrix_deltas": matrix_delta,
        "global_independent_parity": global_parity,
        "solver": {
            "speed_rpm": _rated(model),
            "positive_finite_modal": solver_pass,
            "wd_rad_s": [float(item) for item in modal_values[:6]],
        },
        "gui_result": gui_result,
        "persistence": persistence,
        "stale_preview": stale_preview,
        "stale_result": {
            "cache_invalidated_after_seal_edit": stale_result_pass,
            "old_worker_callback_rejected": late_worker_pass,
        },
        "thermodynamic_backend": backend,
        "convergence": convergence,
    }


def run_seals_qualification(*, frozen_mode: bool = False) -> SealsQualification:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise RuntimeError(f"Seals 0.26 qualification is pinned to ROSS 2.3.0, received {rs.__version__}.")

    app = _ensure_qapplication()
    service = SealStudioService(rs)

    model_ledgers: dict[str, object] = {}
    for model in (SealModel.DIRECT, SealModel.LABYRINTH, SealModel.HOLE_PATTERN, SealModel.HYBRID):
        model_ledgers[model.value] = _qualify_model(rs, model, app, frozen_mode=frozen_mode)

    validation = _validation_regressions(service)
    hole_failure = _hole_failure_regression()
    hybrid_failure = _hybrid_nonconvergence_regression()
    physical_variations = {
        model.value: _physical_variation(service, model)
        for model in (SealModel.DIRECT, SealModel.LABYRINTH, SealModel.HOLE_PATTERN, SealModel.HYBRID)
    }

    qualification_matrix = {
        "DIRECT SEAL": model_ledgers[SealModel.DIRECT.value]["status"],
        "LABYRINTH SEAL": model_ledgers[SealModel.LABYRINTH.value]["status"],
        "HOLE PATTERN SEAL": model_ledgers[SealModel.HOLE_PATTERN.value]["status"],
        "HYBRID SEAL": model_ledgers[SealModel.HYBRID.value]["status"],
    }
    release_pass = bool(
        all(value == "PASS" for value in qualification_matrix.values())
        and validation["pass"]
        and hole_failure["pass"]
        and hybrid_failure["pass"]
        and all(item["pass"] for item in physical_variations.values())
    )
    payload: dict[str, object] = {
        "ross_version": rs.__version__,
        "studio_version": "0.30.0",
        "frozen_mode": bool(frozen_mode),
        "qualification_matrix": qualification_matrix,
        "models": model_ledgers,
        "input_validation": validation,
        "hole_pattern_failure_regression": hole_failure,
        "hybrid_nonconvergence_regression": hybrid_failure,
        "controlled_physical_variations": physical_variations,
        "unit_conversion_contract": {
            "mm_to_m": "x / 1000; shaft diameter -> radius uses diameter / 2000",
            "bar_to_pa": "x * 1e5",
            "degC_to_K": "x + 273.15",
            "rpm_to_rad_s": "x * 2*pi/60",
            "K": "N/m identity",
            "C": "N*s/m identity",
        },
        "thermodynamic_backend_policy": (
            "ROSS 2.3.0 seal classes use ccp. ROSS Studio records REFPROP availability, configured EOS, "
            "effective backend and fallback warning. Upstream HEOS/CoolProp fallback is visible and is not "
            "declared scientifically equivalent to REFPROP."
        ),
    }
    return SealsQualification(status="PASS" if release_pass else "FAIL", payload=payload)


__all__ = ["SealsQualification", "run_seals_qualification"]
