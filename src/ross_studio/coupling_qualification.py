from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite, pi
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from .domain import (
    BearingSpec,
    CouplingSpec,
    DiskSpec,
    EngineeringError,
    MaterialSpec,
    OperatingCase,
    ProbeSpec,
    RotorProject,
    ShaftSection,
)
from .model_builder_service import RotorModelMutationService
from .model_entity_dialogs import CouplingEditorDialog
from .models import ProjectModel
from .pages.rotor_model import RotorModelPage
from .pages.static_modal_workspace import StaticModalWorkspacePage
from .project_io import load_project, project_fingerprint, save_project
from .ross_backend import RossModelBuilder
from .static_modal_analysis import StaticModalAnalysisService
from .static_modal_decoupled import ModalAnalysisRequest, ModalAnalysisResult


_COUPLING = {
    "name": "QUAL-CPL-025-73149",
    "position_mm": 430.125,
    "length_mm": 57.5,
    "od_mm": 88.875,
    "left_mass_kg": 6.125,
    "right_mass_kg": 7.375,
    "left_id_kg_m2": 0.012345,
    "right_id_kg_m2": 0.023456,
    "left_ip_kg_m2": 0.034567,
    "right_ip_kg_m2": 0.045678,
    "kt_x_n_m": 1.234567e8,
    "kt_y_n_m": 2.345678e8,
    "kt_z_n_m": 3.456789e8,
    "kr_x_n_m_rad": 4.56789e5,
    "kr_y_n_m_rad": 5.678901e5,
    "kr_z_n_m_rad": 6.789012e5,
    "ct_x_n_s_m": 1234.5,
    "ct_y_n_s_m": 2345.6,
    "ct_z_n_s_m": 3456.7,
    "cr_x_n_m_s_rad": 45.678,
    "cr_y_n_m_s_rad": 56.789,
    "cr_z_n_m_s_rad": 67.891,
}
_K_FIELDS = (
    "kt_x_n_m", "kt_y_n_m", "kt_z_n_m",
    "kr_x_n_m_rad", "kr_y_n_m_rad", "kr_z_n_m_rad",
)
_C_FIELDS = (
    "ct_x_n_s_m", "ct_y_n_s_m", "ct_z_n_s_m",
    "cr_x_n_m_s_rad", "cr_y_n_m_s_rad", "cr_z_n_m_s_rad",
)


@dataclass(slots=True)
class CouplingQualification:
    status: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        result = dict(self.payload)
        result["status"] = self.status
        result["declared_scope"] = (
            "ROSS Studio Coupling 0.25: native ROSS 2.3.0 CouplingElement; one positive-length "
            "adjacent two-node shaft interval; 6 DOF/node; finite left/right mass and Id/Ip; "
            "linear independent translational/rotational K/C in SI units."
        )
        result["excluded_scope"] = (
            "Nonlinear/backlash coupling laws, gear-mesh coupling, misalignment fault forcing, "
            "non-adjacent spans, and legacy zero-length single-station couplings are not qualified."
        )
        return result


def _ensure_qapplication():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["ross-studio-coupling-025-qualification"])
    return app


def _base_model() -> ProjectModel:
    steel = MaterialSpec(name="QUAL-Steel-025", density_kg_m3=7850.0, young_pa=207.0e9, poisson=0.3)
    project = RotorProject(
        name="QUAL-Coupling-025",
        reference="Coupling feature qualification",
        line="QUAL",
        frame="025",
        poles=2,
        description="Deterministic native CouplingElement qualification rotor",
        materials={steel.name: steel},
        shaft_sections=[
            ShaftSection(
                section=1,
                length_mm=1000.0,
                od_left_mm=100.0,
                od_right_mm=100.0,
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
                name="QUAL-BRG-L-025",
                position_mm=0.0,
                kxx=1.11e8,
                kyy=1.22e8,
                cxx=1111.0,
                cyy=1222.0,
            ),
            BearingSpec(
                name="QUAL-BRG-R-025",
                position_mm=1000.0,
                kxx=1.33e8,
                kyy=1.44e8,
                cxx=1333.0,
                cyy=1444.0,
            ),
        ],
        disks=[
            DiskSpec(
                name="QUAL-DISK-025",
                position_mm=700.0,
                mass_kg=18.75,
                id_kg_m2=0.08125,
                ip_kg_m2=0.15125,
            )
        ],
        operating_cases=[
            OperatingCase(
                name="Coupling qualification",
                rated_speed_rpm=3600.0,
                speed_min_rpm=0.0,
                speed_max_rpm=4500.0,
                frequency_hz=60.0,
            )
        ],
    )
    project.validate()
    return ProjectModel.from_engineering(project)


def _record_from_gui(model: ProjectModel) -> tuple[CouplingSpec, dict[str, object]]:
    if model.engineering is None:
        raise RuntimeError("Coupling qualification model has no engineering domain.")
    dialog = CouplingEditorDialog(total_length_mm=model.engineering.total_length_mm)
    widget_map = {
        "position_mm": "position",
        "length_mm": "length",
        "od_mm": "od",
        "left_mass_kg": "left_mass",
        "right_mass_kg": "right_mass",
        "left_id_kg_m2": "left_id",
        "right_id_kg_m2": "right_id",
        "left_ip_kg_m2": "left_ip",
        "right_ip_kg_m2": "right_ip",
        "kt_x_n_m": "kt_x",
        "kt_y_n_m": "kt_y",
        "kt_z_n_m": "kt_z",
        "kr_x_n_m_rad": "kr_x",
        "kr_y_n_m_rad": "kr_y",
        "kr_z_n_m_rad": "kr_z",
        "ct_x_n_s_m": "ct_x",
        "ct_y_n_s_m": "ct_y",
        "ct_z_n_s_m": "ct_z",
        "cr_x_n_m_s_rad": "cr_x",
        "cr_y_n_m_s_rad": "cr_y",
        "cr_z_n_m_s_rad": "cr_z",
    }
    dialog.name.setText(str(_COUPLING["name"]))
    for field, widget_name in widget_map.items():
        getattr(dialog, widget_name).setValue(float(_COUPLING[field]))
    record = dialog.record()
    gui = {
        "name": dialog.name.text(),
        **{field: float(getattr(dialog, widget_name).value()) for field, widget_name in widget_map.items()},
        "units": {
            "position_length_od": "mm",
            "mass": "kg",
            "inertia": "kg*m^2",
            "translational_stiffness": "N/m",
            "rotational_stiffness": "N*m/rad",
            "translational_damping": "N*s/m",
            "rotational_damping": "N*m*s/rad",
        },
    }
    dialog.close()
    return record, gui


def _matrix_parity(actual, reference, *, rtol: float, atol: float) -> dict[str, object]:
    actual_array = np.asarray(actual, dtype=float)
    reference_array = np.asarray(reference, dtype=float)
    delta = np.abs(actual_array - reference_array)
    scale = np.maximum(np.abs(reference_array), atol)
    return {
        "shape": list(actual_array.shape),
        "max_abs_error": float(np.max(delta)) if delta.size else 0.0,
        "max_rel_error": float(np.max(delta / scale)) if delta.size else 0.0,
        "rtol": float(rtol),
        "atol": float(atol),
        "pass": bool(np.allclose(actual_array, reference_array, rtol=rtol, atol=atol)),
    }


def _native_coupling(rs, spec: CouplingSpec, node: int):
    return rs.CouplingElement(
        m_l=spec.left_mass_kg,
        m_r=spec.right_mass_kg,
        Ip_l=spec.left_ip_kg_m2,
        Ip_r=spec.right_ip_kg_m2,
        Id_l=spec.left_id_kg_m2,
        Id_r=spec.right_id_kg_m2,
        kt_x=spec.kt_x_n_m,
        kt_y=spec.kt_y_n_m,
        kt_z=spec.kt_z_n_m,
        kr_x=spec.kr_x_n_m_rad,
        kr_y=spec.kr_y_n_m_rad,
        kr_z=spec.kr_z_n_m_rad,
        ct_x=spec.ct_x_n_s_m,
        ct_y=spec.ct_y_n_s_m,
        ct_z=spec.ct_z_n_s_m,
        cr_x=spec.cr_x_n_m_s_rad,
        cr_y=spec.cr_y_n_m_s_rad,
        cr_z=spec.cr_z_n_m_s_rad,
        o_d=None if spec.od_mm <= 0.0 else spec.od_mm / 1000.0,
        L=spec.length_mm / 1000.0,
        n=node,
        tag=spec.name,
    )


def _topology_marker_project(project: RotorProject, coupling: CouplingSpec) -> RotorProject:
    marker = deepcopy(project)
    marker.couplings = []
    marker.probes.extend(
        [
            ProbeSpec("QUAL-CPL-left-topology-marker", coupling.position_mm, 1, 0.0),
            ProbeSpec("QUAL-CPL-right-topology-marker", coupling.end_mm, 1, 0.0),
        ]
    )
    marker.validate()
    return marker


def _manual_reference_rotor(rs, project: RotorProject, coupling: CouplingSpec):
    marker = _topology_marker_project(project, coupling)
    base_build = RossModelBuilder(rs).build(marker, strict=True)
    plan = base_build.node_insertion_plan
    left_node = plan.node_for(coupling.position_mm)
    right_node = plan.node_for(coupling.end_mm)
    if left_node is None or right_node != left_node + 1:
        raise RuntimeError(
            f"Independent Coupling reference expected adjacent nodes; received {left_node}, {right_node}."
        )
    reference_element = _native_coupling(rs, coupling, left_node)
    replaced = 0
    shaft = []
    for element in base_build.rotor.shaft_elements:
        if int(element.n) == left_node:
            shaft.append(reference_element)
            replaced += 1
        else:
            shaft.append(element)
    if replaced != 1:
        raise RuntimeError(f"Independent Coupling reference replaced {replaced} shaft intervals; expected one.")
    rotor = rs.Rotor(
        shaft_elements=shaft,
        disk_elements=list(base_build.rotor.disk_elements) or None,
        bearing_elements=list(base_build.rotor.bearing_elements) or None,
        point_mass_elements=list(base_build.rotor.point_mass_elements) or None,
        tag=project.name,
    )
    return rotor, reference_element, base_build


def _positive_modal_hz(rotor, *, count: int = 6):
    modal = rotor.run_modal(speed=0.0, num_modes=max(20, 2 * count))
    values = np.asarray(modal.wd, dtype=float) / (2.0 * pi)
    positive = values[np.isfinite(values) & (values > 1.0e-7)]
    if positive.size < count:
        raise RuntimeError(f"Coupling gate expected at least {count} positive modal frequencies; received {positive.size}.")
    return positive[:count], modal


def _minimal_modal_result(project: ProjectModel, build, modal) -> ModalAnalysisResult:
    modes = StaticModalAnalysisService._mode_summaries(modal)
    request = ModalAnalysisRequest(speed_rpm=0.0, num_modes=20, campbell_points=5, campbell_frequencies=2)
    return ModalAnalysisResult(
        project_name=project.name,
        build=build,
        request=request,
        modal=modal,
        campbell=None,
        campbell_speed_rpm=np.asarray([], dtype=float),
        modal_modes=modes,
        audits=[],
        stage_elapsed_s={"Modal": 0.0},
    )


def _table_modal_evidence(page: StaticModalWorkspacePage, result: ModalAnalysisResult, fingerprint: str):
    page.modal_result = result
    page.modal_fingerprint = fingerprint
    page.modal_request_key = result.request.cache_key()
    page._populate_mode_table()
    rows = [row for row in result.modal_modes if row.mode_type == "Lateral"]
    if not rows:
        return {"pass": False, "reason": "No Lateral modes returned", "row_count": page.mode_table.rowCount()}
    first = rows[0]
    actual = page.mode_table.item(0, 3).text() if page.mode_table.item(0, 3) is not None else ""
    expected = f"{first.wd_hz:.6g}"
    return {
        "row_count": page.mode_table.rowCount(),
        "native_wd_hz": float(first.wd_hz),
        "gui_wd_hz_text": actual,
        "expected_gui_text": expected,
        "pass": bool(page.mode_table.rowCount() == len(rows) and actual == expected),
    }


def _scaled_coupling(source: CouplingSpec, stiffness_scale: float, name: str) -> CouplingSpec:
    result = deepcopy(source)
    result.name = name
    for field in _K_FIELDS:
        setattr(result, field, float(getattr(result, field)) * float(stiffness_scale))
    return result


def _fixed_left_lateral_compliance_um_per_n(element) -> float:
    k = np.asarray(element.K(), dtype=float)
    if k.shape != (12, 12):
        raise RuntimeError(f"Expected 12x12 coupling/shaft matrix, received {k.shape}.")
    right = k[6:, 6:]
    compliance = np.linalg.pinv(right, rcond=1.0e-14)
    value = 0.5 * (float(compliance[0, 0]) + float(compliance[1, 1])) * 1.0e6
    if not isfinite(value) or value <= 0.0:
        raise RuntimeError(f"Invalid fixed-left lateral compliance {value!r}.")
    return value


def _expect_rejected(label: str, callback, terms: tuple[str, ...]) -> dict[str, object]:
    try:
        callback()
    except EngineeringError as exc:
        text = str(exc)
        folded = text.casefold()
        return {
            "label": label,
            "pass": all(term.casefold() in folded for term in terms),
            "message": text,
            "required_terms": list(terms),
        }
    except Exception as exc:
        return {
            "label": label,
            "pass": False,
            "message": f"Unexpected {type(exc).__name__}: {exc}",
            "required_terms": list(terms),
        }
    return {"label": label, "pass": False, "message": "Mutation unexpectedly accepted.", "required_terms": list(terms)}


def run_coupling_qualification() -> CouplingQualification:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise RuntimeError(f"Coupling qualification is pinned to ROSS 2.3.0, received {rs.__version__}.")

    app = _ensure_qapplication()
    model = _base_model()
    project = model.engineering
    if project is None:
        raise RuntimeError("Coupling qualification lost its engineering domain.")

    record, gui_inputs = _record_from_gui(model)
    rotor_page = RotorModelPage(model)
    rotor_page.select_editor("couplings")
    preview = rotor_page.model_builder.preview_add(project, "coupling", record)
    audit = rotor_page.model_builder.commit(project, preview)
    rotor_page._after_model_commit("couplings", audit, selected_row=0)
    app.processEvents()

    committed = project.couplings[0]
    table = rotor_page.editor_tables["couplings"]
    gui_table = {
        "name": table.item(0, 0).text(),
        "position_mm": table.item(0, 1).text(),
        "ross_node": table.item(0, 2).text(),
        "left_mass_kg": table.item(0, 3).text(),
        "right_mass_kg": table.item(0, 4).text(),
        "left_ip_kg_m2": table.item(0, 5).text(),
        "right_ip_kg_m2": table.item(0, 6).text(),
        "kt_x_n_m": table.item(0, 7).text(),
        "kt_y_n_m": table.item(0, 8).text(),
        "kt_z_n_m": table.item(0, 9).text(),
        "kr_x_n_m_rad": table.item(0, 10).text(),
        "kr_y_n_m_rad": table.item(0, 11).text(),
        "kr_z_n_m_rad": table.item(0, 12).text(),
    }
    gui_commit_pass = bool(
        committed == record
        and gui_table["name"] == committed.name
        and gui_table["position_mm"] == f"{committed.position_mm:g}"
        and gui_table["left_mass_kg"] == f"{committed.left_mass_kg:g}"
        and gui_table["right_mass_kg"] == f"{committed.right_mass_kg:g}"
        and gui_table["left_ip_kg_m2"] == f"{committed.left_ip_kg_m2:.6g}"
        and gui_table["right_ip_kg_m2"] == f"{committed.right_ip_kg_m2:.6g}"
        and gui_table["kt_x_n_m"] == f"{committed.kt_x_n_m:.3e}"
        and gui_table["kr_z_n_m_rad"] == f"{committed.kr_z_n_m_rad:.3e}"
    )

    builder = RossModelBuilder(rs)
    build = builder.build(project, strict=True)
    rotor = build.rotor
    coupling_elements = [element for element in rotor.shaft_elements if type(element).__name__ == "CouplingElement"]
    if len(coupling_elements) != 1:
        raise RuntimeError(f"Expected one native CouplingElement, received {len(coupling_elements)}.")
    native = coupling_elements[0]
    left_node = build.node_insertion_plan.node_for(committed.position_mm)
    right_node = build.node_insertion_plan.node_for(committed.end_mm)
    if left_node is None or right_node is None:
        raise RuntimeError("Coupling stations did not map to exact FE nodes.")

    independent_rotor, independent_element, no_coupling_build = _manual_reference_rotor(rs, project, committed)
    local_parity = {
        "M": _matrix_parity(native.M(), independent_element.M(), rtol=0.0, atol=1.0e-12),
        "K": _matrix_parity(native.K(), independent_element.K(), rtol=0.0, atol=1.0e-9),
        "C": _matrix_parity(native.C(), independent_element.C(), rtol=0.0, atol=1.0e-12),
        "G": _matrix_parity(native.G(), independent_element.G(), rtol=0.0, atol=1.0e-12),
    }
    global_parity = {
        "M": _matrix_parity(rotor.M(), independent_rotor.M(), rtol=1.0e-12, atol=1.0e-10),
        "K0": _matrix_parity(rotor.K(0.0), independent_rotor.K(0.0), rtol=1.0e-12, atol=1.0e-6),
        "C0": _matrix_parity(rotor.C(0.0), independent_rotor.C(0.0), rtol=1.0e-12, atol=1.0e-9),
        "G": _matrix_parity(rotor.G(), independent_rotor.G(), rtol=1.0e-12, atol=1.0e-12),
    }

    native_fields = {
        "m_l": float(native.m_l),
        "m_r": float(native.m_r),
        "Id_l": float(native.Id_l),
        "Id_r": float(native.Id_r),
        "Ip_l": float(native.Ip_l),
        "Ip_r": float(native.Ip_r),
        "L_m": float(native.L),
        "o_d_m": float(native.o_d),
        "kt_x": float(native.kt_x),
        "kt_y": float(native.kt_y),
        "kt_z": float(native.kt_z),
        "kr_x": float(native.kr_x),
        "kr_y": float(native.kr_y),
        "kr_z": float(native.kr_z),
        "ct_x": float(native.ct_x),
        "ct_y": float(native.ct_y),
        "ct_z": float(native.ct_z),
        "cr_x": float(native.cr_x),
        "cr_y": float(native.cr_y),
        "cr_z": float(native.cr_z),
    }
    expected_native_fields = {
        "m_l": gui_inputs["left_mass_kg"],
        "m_r": gui_inputs["right_mass_kg"],
        "Id_l": gui_inputs["left_id_kg_m2"],
        "Id_r": gui_inputs["right_id_kg_m2"],
        "Ip_l": gui_inputs["left_ip_kg_m2"],
        "Ip_r": gui_inputs["right_ip_kg_m2"],
        "L_m": gui_inputs["length_mm"] / 1000.0,
        "o_d_m": gui_inputs["od_mm"] / 1000.0,
        "kt_x": gui_inputs["kt_x_n_m"],
        "kt_y": gui_inputs["kt_y_n_m"],
        "kt_z": gui_inputs["kt_z_n_m"],
        "kr_x": gui_inputs["kr_x_n_m_rad"],
        "kr_y": gui_inputs["kr_y_n_m_rad"],
        "kr_z": gui_inputs["kr_z_n_m_rad"],
        "ct_x": gui_inputs["ct_x_n_s_m"],
        "ct_y": gui_inputs["ct_y_n_s_m"],
        "ct_z": gui_inputs["ct_z_n_s_m"],
        "cr_x": gui_inputs["cr_x_n_m_s_rad"],
        "cr_y": gui_inputs["cr_y_n_m_s_rad"],
        "cr_z": gui_inputs["cr_z_n_m_s_rad"],
    }
    unit_identity = {
        key: {
            "gui_or_expected_si": float(expected_native_fields[key]),
            "native": float(native_fields[key]),
            "abs_error": abs(float(native_fields[key]) - float(expected_native_fields[key])),
        }
        for key in native_fields
    }
    unit_identity_pass = all(item["abs_error"] <= 1.0e-10 for item in unit_identity.values())

    k_local = np.asarray(native.K(), dtype=float)
    c_local = np.asarray(native.C(), dtype=float)
    m_local = np.asarray(native.M(), dtype=float)
    g_local = np.asarray(native.G(), dtype=float)
    k_eigs = np.linalg.eigvalsh(0.5 * (k_local + k_local.T))
    c_eigs = np.linalg.eigvalsh(0.5 * (c_local + c_local.T))
    m_eigs = np.linalg.eigvalsh(0.5 * (m_local + m_local.T))
    structural = {
        "local_shapes": {
            "M": list(m_local.shape),
            "K": list(k_local.shape),
            "C": list(c_local.shape),
            "G": list(g_local.shape),
        },
        "mass_symmetric": bool(np.allclose(m_local, m_local.T, rtol=0.0, atol=1.0e-12)),
        "stiffness_symmetric": bool(np.allclose(k_local, k_local.T, rtol=0.0, atol=1.0e-12)),
        "damping_symmetric": bool(np.allclose(c_local, c_local.T, rtol=0.0, atol=1.0e-12)),
        "gyroscopic_antisymmetric": bool(np.allclose(g_local, -g_local.T, rtol=0.0, atol=1.0e-12)),
        "mass_min_eigenvalue": float(np.min(m_eigs)),
        "stiffness_min_eigenvalue": float(np.min(k_eigs)),
        "damping_min_eigenvalue": float(np.min(c_eigs)),
        "mass_psd": bool(np.min(m_eigs) >= -1.0e-12),
        "stiffness_psd": bool(np.min(k_eigs) >= -1.0e-6),
        "damping_psd": bool(np.min(c_eigs) >= -1.0e-9),
    }
    structural_pass = bool(
        all(shape == [12, 12] for shape in structural["local_shapes"].values())
        and structural["mass_symmetric"]
        and structural["stiffness_symmetric"]
        and structural["damping_symmetric"]
        and structural["gyroscopic_antisymmetric"]
        and structural["mass_psd"]
        and structural["stiffness_psd"]
        and structural["damping_psd"]
    )

    sign_structure = {
        "K_x_positive": float(k_local[0, 0]),
        "K_x_cross_negative": float(k_local[0, 6]),
        "K_torsion_positive": float(k_local[5, 5]),
        "K_torsion_cross_negative": float(k_local[5, 11]),
        "C_x_positive": float(c_local[0, 0]),
        "C_x_cross_negative": float(c_local[0, 6]),
        "C_torsion_positive": float(c_local[5, 5]),
        "C_torsion_cross_negative": float(c_local[5, 11]),
    }
    sign_pass = bool(
        np.isclose(k_local[0, 0], committed.kt_x_n_m)
        and np.isclose(k_local[0, 6], -committed.kt_x_n_m)
        and np.isclose(k_local[5, 5], committed.kr_z_n_m_rad)
        and np.isclose(k_local[5, 11], -committed.kr_z_n_m_rad)
        and np.isclose(c_local[0, 0], committed.ct_x_n_s_m)
        and np.isclose(c_local[0, 6], -committed.ct_x_n_s_m)
        and np.isclose(c_local[5, 5], committed.cr_z_n_m_s_rad)
        and np.isclose(c_local[5, 11], -committed.cr_z_n_m_s_rad)
    )

    topology = {
        "left_position_mm": committed.position_mm,
        "right_position_mm": committed.end_mm,
        "left_node": int(left_node),
        "right_node": int(right_node),
        "native_n": int(native.n),
        "native_n_r": int(native.n_r),
        "left_node_position_mm": float(build.node_positions_mm[left_node]),
        "right_node_position_mm": float(build.node_positions_mm[right_node]),
        "adjacent": bool(right_node == left_node + 1),
        "dof_per_node": 6,
        "local_matrix_dof": int(k_local.shape[0]),
        "native_class": type(native).__name__,
        "tag": str(native.tag),
    }
    topology_pass = bool(
        right_node == left_node + 1
        and int(native.n) == left_node
        and int(native.n_r) == right_node
        and abs(build.node_positions_mm[left_node] - committed.position_mm) <= 1.0e-9
        and abs(build.node_positions_mm[right_node] - committed.end_mm) <= 1.0e-9
        and k_local.shape == (12, 12)
        and type(native).__name__ == "CouplingElement"
        and native.tag == committed.name
    )

    baseline_hz, baseline_modal = _positive_modal_hz(rotor)
    no_hz, no_modal = _positive_modal_hz(no_coupling_build.rotor)
    stiff_spec = _scaled_coupling(committed, 100.0, "QUAL-CPL-STIFF-025")
    soft_spec = _scaled_coupling(committed, 0.1, "QUAL-CPL-SOFT-025")

    def build_case(spec: CouplingSpec):
        case_project = deepcopy(project)
        case_project.couplings = [deepcopy(spec)]
        case_build = RossModelBuilder(rs).build(case_project, strict=True)
        case_hz, case_modal = _positive_modal_hz(case_build.rotor)
        case_native = next(element for element in case_build.rotor.shaft_elements if type(element).__name__ == "CouplingElement")
        return case_build, case_hz, case_modal, case_native

    stiff_build, stiff_hz, stiff_modal, stiff_native = build_case(stiff_spec)
    soft_build, soft_hz, soft_modal, soft_native = build_case(soft_spec)
    no_span_element = next(element for element in no_coupling_build.rotor.shaft_elements if int(element.n) == left_node)
    compliance = {
        "no_coupling_shaft_interval_um_per_n": _fixed_left_lateral_compliance_um_per_n(no_span_element),
        "stiffer_coupling_um_per_n": _fixed_left_lateral_compliance_um_per_n(stiff_native),
        "baseline_coupling_um_per_n": _fixed_left_lateral_compliance_um_per_n(native),
        "softer_coupling_um_per_n": _fixed_left_lateral_compliance_um_per_n(soft_native),
    }
    physical_response_pass = bool(
        compliance["stiffer_coupling_um_per_n"]
        < compliance["baseline_coupling_um_per_n"]
        < compliance["softer_coupling_um_per_n"]
        and not np.allclose(stiff_modal.wd, baseline_modal.wd, rtol=1.0e-7, atol=1.0e-7)
        and not np.allclose(soft_modal.wd, baseline_modal.wd, rtol=1.0e-7, atol=1.0e-7)
        and not np.allclose(no_modal.wd, baseline_modal.wd, rtol=1.0e-7, atol=1.0e-7)
    )
    cases = {
        "no_coupling": {"first_six_modal_hz": [float(v) for v in no_hz]},
        "baseline": {"first_six_modal_hz": [float(v) for v in baseline_hz]},
        "stiffer_x100": {"first_six_modal_hz": [float(v) for v in stiff_hz]},
        "softer_x0_1": {"first_six_modal_hz": [float(v) for v in soft_hz]},
        "fixed_left_lateral_compliance": compliance,
        "physically_coherent_response_pass": physical_response_pass,
    }

    baseline_fp = project_fingerprint(model)
    modal_result = _minimal_modal_result(model, build, baseline_modal)
    modal_page = StaticModalWorkspacePage(model, mode_filter="Lateral")
    gui_result = _table_modal_evidence(modal_page, modal_result, baseline_fp)

    with TemporaryDirectory(prefix="ross_coupling_025_") as temp_dir:
        target = save_project(model, Path(temp_dir) / "coupling-025.rossproj")
        reopened = load_project(target)
        if reopened.engineering is None:
            raise RuntimeError("Reopened Coupling qualification project lost engineering data.")
        reopened_build = RossModelBuilder(rs).build(reopened.engineering, strict=True)
        _, reopened_modal = _positive_modal_hz(reopened_build.rotor)
        persistence = {
            "coupling_equal": reopened.engineering.couplings == project.couplings,
            "M": _matrix_parity(reopened_build.rotor.M(), rotor.M(), rtol=1.0e-12, atol=1.0e-10),
            "K0": _matrix_parity(reopened_build.rotor.K(0.0), rotor.K(0.0), rtol=1.0e-12, atol=1.0e-6),
            "C0": _matrix_parity(reopened_build.rotor.C(0.0), rotor.C(0.0), rtol=1.0e-12, atol=1.0e-9),
            "G": _matrix_parity(reopened_build.rotor.G(), rotor.G(), rtol=1.0e-12, atol=1.0e-12),
            "modal_wd": _matrix_parity(reopened_modal.wd, baseline_modal.wd, rtol=1.0e-11, atol=1.0e-9),
        }
    persistence_pass = bool(
        persistence["coupling_equal"]
        and all(persistence[key]["pass"] for key in ("M", "K0", "C0", "G", "modal_wd"))
    )

    stale_preview_model = deepcopy(model)
    stale_preview_project = stale_preview_model.engineering
    if stale_preview_project is None:
        raise RuntimeError("Stale preview probe lost engineering domain.")
    stale_service = RotorModelMutationService(rs)
    stale_preview = stale_service.preview_update(
        stale_preview_project,
        "coupling",
        0,
        {"kt_x_n_m": stale_preview_project.couplings[0].kt_x_n_m * 1.1},
    )
    stale_preview_project.couplings[0].kt_y_n_m *= 1.001
    stale_preview_rejection = _expect_rejected(
        "stale preview",
        lambda: stale_service.commit(stale_preview_project, stale_preview),
        ("inputs changed after preview",),
    )

    stale_model = deepcopy(model)
    stale_project = stale_model.engineering
    if stale_project is None:
        raise RuntimeError("Stale result probe lost engineering domain.")
    stale_page = StaticModalWorkspacePage(stale_model, mode_filter="Lateral")
    _table_modal_evidence(stale_page, _minimal_modal_result(stale_model, build, baseline_modal), project_fingerprint(stale_model))
    stale_rotor_page = RotorModelPage(stale_model)
    stale_mutation = stale_rotor_page.model_builder.preview_update(
        stale_project, "coupling", 0, {"kt_x_n_m": stale_project.couplings[0].kt_x_n_m * 1.2}
    )
    stale_audit = stale_rotor_page.model_builder.commit(stale_project, stale_mutation)
    stale_rotor_page._after_model_commit("couplings", stale_audit, selected_row=0)
    stale_page._invalidate_if_project_changed()
    stale_result_pass = bool(
        stale_page.modal_result is None
        and stale_page.mode_table.rowCount() == 0
        and "invalidated" in stale_page.modal_state.text().casefold()
    )

    race_model = deepcopy(model)
    race_project = race_model.engineering
    if race_project is None:
        raise RuntimeError("Race probe lost engineering domain.")
    old_fp = project_fingerprint(race_model)
    old_result = _minimal_modal_result(race_model, build, baseline_modal)
    race_rotor_page = RotorModelPage(race_model)
    race_mutation = race_rotor_page.model_builder.preview_update(
        race_project, "coupling", 0, {field: getattr(race_project.couplings[0], field) * 100.0 for field in _K_FIELDS}
    )
    race_audit = race_rotor_page.model_builder.commit(race_project, race_mutation)
    race_rotor_page._after_model_commit("couplings", race_audit, selected_row=0)
    new_fp = project_fingerprint(race_model)
    race_build = RossModelBuilder(rs).build(race_project, strict=True)
    _, race_modal = _positive_modal_hz(race_build.rotor)
    new_result = _minimal_modal_result(race_model, race_build, race_modal)
    race_page = StaticModalWorkspacePage(race_model, mode_filter="Lateral")
    new_gui = _table_modal_evidence(race_page, new_result, new_fp)
    before_text = race_page.mode_table.item(0, 3).text() if race_page.mode_table.item(0, 3) is not None else ""
    race_page._on_modal_success(old_result, old_fp)
    after_text = race_page.mode_table.item(0, 3).text() if race_page.mode_table.item(0, 3) is not None else ""
    race_pass = bool(
        new_gui["pass"]
        and race_page.modal_result is new_result
        and before_text == after_text
        and "discarded" in race_page.modal_state.text().casefold()
    )

    invalid_base = _base_model()
    invalid_project = invalid_base.engineering
    if invalid_project is None:
        raise RuntimeError("Fail-closed probe lost engineering domain.")
    invalid_service = RotorModelMutationService(rs)

    zero_length = deepcopy(record)
    zero_length.length_mm = 0.0
    zero_gate = _expect_rejected(
        "zero-length legacy coupling",
        lambda: invalid_service.preview_add(invalid_project, "coupling", zero_length),
        ("COUPLING_TWO_NODE_REQUIRED",),
    )

    midpoint_project = deepcopy(invalid_project)
    midpoint_project.probes.append(ProbeSpec("QUAL-CPL-midpoint-blocker", record.position_mm + 0.5 * record.length_mm, 1, 0.0))
    intermediate_gate = _expect_rejected(
        "intermediate node inside span",
        lambda: invalid_service.preview_add(midpoint_project, "coupling", deepcopy(record)),
        ("COUPLING_NOT_ADJACENT",),
    )

    duplicate_model = deepcopy(model)
    duplicate_project = duplicate_model.engineering
    if duplicate_project is None:
        raise RuntimeError("Duplicate probe lost engineering domain.")
    duplicate = deepcopy(record)
    duplicate.name = "QUAL-CPL-DUPLICATE-025"
    duplicate_gate = _expect_rejected(
        "duplicate interval",
        lambda: invalid_service.preview_add(duplicate_project, "coupling", duplicate),
        ("more than one coupling occupies interval",),
    )

    outside = deepcopy(record)
    outside.position_mm = 980.0
    outside.length_mm = 50.0
    outside_gate = _expect_rejected(
        "span outside shaft",
        lambda: invalid_service.preview_add(invalid_project, "coupling", outside),
        ("outside the shaft",),
    )

    nonfinite = deepcopy(record)
    nonfinite.kt_x_n_m = float("nan")
    nonfinite_gate = _expect_rejected(
        "NaN stiffness",
        lambda: invalid_service.preview_add(invalid_project, "coupling", nonfinite),
        ("finite physical value",),
    )

    negative_mass = deepcopy(record)
    negative_mass.left_mass_kg = -1.0
    negative_gate = _expect_rejected(
        "negative mass",
        lambda: invalid_service.preview_add(invalid_project, "coupling", negative_mass),
        ("non-negative",),
    )

    fail_closed = {
        row["label"]: row
        for row in (
            zero_gate,
            intermediate_gate,
            duplicate_gate,
            outside_gate,
            nonfinite_gate,
            negative_gate,
            stale_preview_rejection,
        )
    }
    fail_closed_pass = all(row["pass"] for row in fail_closed.values())

    no_silent_fallback = bool(
        len(coupling_elements) == 1
        and len(rotor.shaft_elements) == len(build.shaft_plan)
        and not any(
            int(element.n) == left_node and type(element).__name__ != "CouplingElement"
            for element in rotor.shaft_elements
        )
        and topology_pass
        and all(row["pass"] for row in local_parity.values())
        and all(row["pass"] for row in global_parity.values())
    )

    gates = {
        "gui_input_to_domain_commit": gui_commit_pass,
        "unit_conversion_and_native_field_identity": unit_identity_pass,
        "exact_two_node_topology_and_6dof_contract": topology_pass,
        "local_12x12_mckg_independent_parity": all(row["pass"] for row in local_parity.values()),
        "assembled_global_mckg_independent_parity": all(row["pass"] for row in global_parity.values()),
        "matrix_structure_and_signs": structural_pass and sign_pass,
        "no_coupling_baseline_stiffer_softer_physical_response": physical_response_pass,
        "native_modal_numeric_result": bool(np.all(np.isfinite(np.asarray(baseline_modal.wd, dtype=float)))),
        "gui_result_rendering": bool(gui_result["pass"]),
        "save_reopen_recompute": persistence_pass,
        "stale_preview_rejected": bool(stale_preview_rejection["pass"]),
        "stale_result_invalidation": stale_result_pass,
        "async_race_obsolete_result_rejected": race_pass,
        "fail_closed_invalid_contracts": fail_closed_pass,
        "no_silent_fallback": no_silent_fallback,
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    for widget in (rotor_page, modal_page, stale_page, stale_rotor_page, race_page, race_rotor_page):
        widget.close()
    app.processEvents()

    payload = {
        "ross_version": rs.__version__,
        "gates": gates,
        "gui_inputs": gui_inputs,
        "gui_committed_table": gui_table,
        "domain_record": asdict(committed),
        "unit_identity": unit_identity,
        "topology": topology,
        "local_matrix_parity": local_parity,
        "global_matrix_parity": global_parity,
        "matrix_structure": structural,
        "matrix_sign_structure": sign_structure,
        "cases": cases,
        "gui_result": gui_result,
        "persistence": persistence,
        "stale_preview": stale_preview_rejection,
        "stale_results": {
            "pass": stale_result_pass,
            "state": stale_page.modal_state.text(),
        },
        "race_protection": {
            "pass": race_pass,
            "old_fingerprint": old_fp,
            "new_fingerprint": new_fp,
            "new_gui_wd_before": before_text,
            "new_gui_wd_after_old_completion": after_text,
            "state": race_page.modal_state.text(),
        },
        "fail_closed": fail_closed,
        "no_silent_fallback": no_silent_fallback,
    }
    return CouplingQualification(status=status, payload=payload)


__all__ = ["CouplingQualification", "run_coupling_qualification"]
