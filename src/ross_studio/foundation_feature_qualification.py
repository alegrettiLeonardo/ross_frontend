from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import pi
from tempfile import TemporaryDirectory
from pathlib import Path

import numpy as np

from .domain import FoundationCoefficientPoint, FoundationModel, FoundationSpec
from .foundation_qualification import FoundationQualification, run_foundation_qualification
from .models import ProjectModel, load_reference_project_model
from .pages.foundation_workspace import FoundationEditorDialog, FoundationWorkspacePage
from .pages.static_modal_workspace import StaticModalWorkspacePage
from .project_io import load_project, project_fingerprint, save_project
from .ross_backend import RossModelBuilder
from .static_modal_analysis import StaticModalAnalysisService
from .static_modal_decoupled import ModalAnalysisRequest, ModalAnalysisResult


_BEARING_SENTINEL = {
    "name": "QUAL-BRG-DE-34791",
    "kxx": 2.731e8,
    "kyy": 3.019e8,
    "kxy": -1.234e6,
    "kyx": -1.234e6,
    "cxx": 3210.5,
    "cyy": 4321.75,
    "cxy": -123.25,
    "cyx": -123.25,
}
_SUPPORT_SENTINEL = {
    "name": "QUAL-SUP-DE-58213",
    "mass_kg": 37.125,
    "kxx": 7.654e8,
    "kyy": 8.765e8,
    "kxy": -3.210e6,
    "kyx": -3.210e6,
    "cxx": 54321.0,
    "cyy": 65432.0,
    "cxy": -432.1,
    "cyx": -432.1,
}
_FOUNDATION_SENTINEL = {
    "name": "QUAL-FDN-DE-91357",
    "mass_kg": 143.257,
    "kxx": 1.234567e8,
    "kyy": 1.765432e8,
    "kxy": -5.6789e6,
    "kyx": -5.6789e6,
    "cxx": 21000.5,
    "cyy": 31000.75,
    "cxy": -789.25,
    "cyx": -789.25,
}


@dataclass(slots=True)
class FoundationFeatureQualification:
    status: str
    science: FoundationQualification
    feature_chain: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = self.science.to_dict()
        payload["legacy_scientific_status"] = payload.get("status")
        payload["feature_chain"] = self.feature_chain
        payload["status"] = self.status
        payload["declared_scope"] = (
            "Foundation Studio 0.24 lateral 2-DOF RIGID/LUMPED_KC/LUMPED_KCM/"
            "FREQUENCY_DEPENDENT_KC integrated with qualified flexible supports"
        )
        return payload


def _ensure_qapplication():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["ross-studio-foundation-feature-qualification"])
    return app


def _sentinelize_support_chain(model: ProjectModel) -> None:
    project = model.engineering
    if project is None or not project.bearings or not project.supports:
        raise RuntimeError("Foundation feature qualification requires the OP-W60 bearing/support chain.")
    bearing = project.bearings[0]
    support = project.supports[0]
    if support.bearing_index != 0:
        raise RuntimeError("Foundation feature qualification expected support #0 to own bearing #0.")

    bearing.name = str(_BEARING_SENTINEL["name"])
    bearing.ross_class = "BearingElement"
    bearing.coefficients = []
    bearing.metadata = {"source": "Foundation feature qualification sentinel"}
    for key in ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx"):
        setattr(bearing, key, float(_BEARING_SENTINEL[key]))

    support.name = str(_SUPPORT_SENTINEL["name"])
    for key in ("mass_kg", "kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx"):
        setattr(support, key, float(_SUPPORT_SENTINEL[key]))
    project.foundations = []
    project.validate()
    model.touch()


def _set_combo_data(combo, value) -> None:
    index = combo.findData(value)
    if index < 0:
        raise RuntimeError(f"GUI combo does not expose required Foundation value {value!r}.")
    combo.setCurrentIndex(index)


def _baseline_record_from_gui(model: ProjectModel) -> tuple[FoundationSpec, dict[str, object]]:
    dialog = FoundationEditorDialog(model, default_support_index=0)
    dialog.name.setText(str(_FOUNDATION_SENTINEL["name"]))
    _set_combo_data(dialog.support, 0)
    _set_combo_data(dialog.model, FoundationModel.LUMPED_KCM)
    dialog.mass.setValue(float(_FOUNDATION_SENTINEL["mass_kg"]))
    for key in ("kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx"):
        getattr(dialog, key).setValue(float(_FOUNDATION_SENTINEL[key]))
    record = dialog.record()
    gui = {
        "name": dialog.name.text(),
        "support_index": int(dialog.support.currentData()),
        "model": str(dialog.model.currentData()),
        "mass_kg": dialog.mass.value(),
        "kxx_n_m": dialog.kxx.value(),
        "kyy_n_m": dialog.kyy.value(),
        "kxy_n_m": dialog.kxy.value(),
        "kyx_n_m": dialog.kyx.value(),
        "cxx_n_s_m": dialog.cxx.value(),
        "cyy_n_s_m": dialog.cyy.value(),
        "cxy_n_s_m": dialog.cxy.value(),
        "cyx_n_s_m": dialog.cyx.value(),
        "dof": record.dof,
        "units": {
            "mass": "kg",
            "stiffness": "N/m",
            "damping": "N*s/m",
        },
    }
    dialog.close()
    return record, gui


def _frequency_record_from_gui(model: ProjectModel) -> tuple[FoundationSpec, list[float]]:
    dialog = FoundationEditorDialog(model, default_support_index=0)
    dialog.name.setText("QUAL-FDN-FREQ-27183")
    _set_combo_data(dialog.support, 0)
    _set_combo_data(dialog.model, FoundationModel.FREQUENCY_DEPENDENT_KC)
    points = [
        FoundationCoefficientPoint(17.125, 1.11e8, -1.1e6, -1.1e6, 1.33e8, 1.21e4, -120.0, -120.0, 1.43e4),
        FoundationCoefficientPoint(83.375, 2.22e8, -2.2e6, -2.2e6, 2.44e8, 2.32e4, -230.0, -230.0, 2.54e4),
    ]
    for point in points:
        dialog._append_point(point)
    record = dialog.record()
    gui_hz = [float(dialog.coefficients.item(row, 0).text()) for row in range(dialog.coefficients.rowCount())]
    dialog.close()
    return record, gui_hz


def _matrices_from_spec(record) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([[record.kxx, record.kxy], [record.kyx, record.kyy]], dtype=float),
        np.asarray([[record.cxx, record.cxy], [record.cyx, record.cyy]], dtype=float),
    )


def _matrix_parity(actual: np.ndarray, reference: np.ndarray, *, rtol: float, atol: float) -> dict[str, object]:
    actual = np.asarray(actual, dtype=float)
    reference = np.asarray(reference, dtype=float)
    delta = np.abs(actual - reference)
    scale = np.maximum(np.abs(reference), atol)
    return {
        "shape": list(actual.shape),
        "max_abs_error": float(np.max(delta)) if delta.size else 0.0,
        "max_rel_error": float(np.max(delta / scale)) if delta.size else 0.0,
        "rtol": float(rtol),
        "atol": float(atol),
        "pass": bool(np.allclose(actual, reference, rtol=rtol, atol=atol)),
    }


def _positive_modal_hz(rotor, *, count: int = 6) -> tuple[np.ndarray, object]:
    modal = rotor.run_modal(speed=0.0, num_modes=max(16, 2 * count))
    values = np.asarray(modal.wd, dtype=float) / (2.0 * pi)
    values = values[np.isfinite(values) & (values > 1.0e-7)]
    if values.size < count:
        raise RuntimeError(f"Foundation feature gate expected at least {count} positive modes, received {values.size}.")
    return values[:count], modal


def _manual_lumped_kcm_rotor(rs, no_foundation_build, support, foundation: FoundationSpec):
    support_node = no_foundation_build.support_link_nodes[support.name]
    foundation_node = max(no_foundation_build.support_link_nodes.values()) + 1
    bearings = [
        element
        for element in no_foundation_build.rotor.bearing_elements
        if getattr(element, "tag", "") != f"{support.name} / ground"
    ]
    bearings.extend(
        [
            rs.BearingElement(
                n=support_node,
                n_link=foundation_node,
                kxx=support.kxx,
                kyy=support.kyy,
                kxy=support.kxy,
                kyx=support.kyx,
                cxx=support.cxx,
                cyy=support.cyy,
                cxy=support.cxy,
                cyx=support.cyx,
                tag=f"{support.name} / foundation",
            ),
            rs.BearingElement(
                n=foundation_node,
                kxx=foundation.kxx,
                kyy=foundation.kyy,
                kxy=foundation.kxy,
                kyx=foundation.kyx,
                cxx=foundation.cxx,
                cyy=foundation.cyy,
                cxy=foundation.cxy,
                cyx=foundation.cyx,
                tag=f"{foundation.name} / ground",
            ),
        ]
    )
    masses = list(no_foundation_build.rotor.point_mass_elements)
    masses.append(rs.PointMass(n=foundation_node, m=foundation.mass_kg, tag=f"{foundation.name} mass"))
    rotor = rs.Rotor(
        shaft_elements=list(no_foundation_build.rotor.shaft_elements),
        disk_elements=list(no_foundation_build.rotor.disk_elements) or None,
        bearing_elements=bearings or None,
        point_mass_elements=masses or None,
        tag=no_foundation_build.rotor.tag,
    )
    return rotor, foundation_node


def _scaled_foundation(source: FoundationSpec, scale: float, name: str) -> FoundationSpec:
    result = deepcopy(source)
    result.name = name
    for key in ("kxx", "kyy", "kxy", "kyx"):
        setattr(result, key, float(getattr(result, key)) * float(scale))
    return result


def _case_payload(rs, no_foundation_model: ProjectModel, foundation: FoundationSpec | None) -> tuple[dict[str, object], object, object]:
    model = deepcopy(no_foundation_model)
    if model.engineering is None:
        raise RuntimeError("Foundation case lost its engineering domain.")
    if foundation is not None:
        model.engineering.foundations.append(deepcopy(foundation))
    builder = RossModelBuilder(rs)
    build = builder.build(model.engineering, strict=True)
    modes_hz, modal = _positive_modal_hz(build.rotor)
    return (
        {
            "matrix_shape": list(np.asarray(build.rotor.M()).shape),
            "m_norm": float(np.linalg.norm(np.asarray(build.rotor.M(), dtype=float))),
            "k0_norm": float(np.linalg.norm(np.asarray(build.rotor.K(0.0), dtype=float))),
            "c0_norm": float(np.linalg.norm(np.asarray(build.rotor.C(0.0), dtype=float))),
            "first_six_modal_hz": [float(value) for value in modes_hz],
        },
        build,
        modal,
    )


def _compliance_um_per_n(support, foundation: FoundationSpec | None) -> float:
    ks, _ = _matrices_from_spec(support)
    if foundation is None:
        compliance = np.linalg.inv(ks)
    else:
        kf, _ = _matrices_from_spec(foundation)
        compliance = np.linalg.inv(ks) + np.linalg.inv(kf)
    return float(0.5 * np.trace(compliance) * 1.0e6)


def _minimal_modal_result(project: ProjectModel, build, modal) -> ModalAnalysisResult:
    modes = StaticModalAnalysisService._mode_summaries(modal)
    request = ModalAnalysisRequest(speed_rpm=0.0, num_modes=16, campbell_points=5, campbell_frequencies=2)
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


def _table_modal_evidence(page: StaticModalWorkspacePage, result: ModalAnalysisResult, fingerprint: str) -> dict[str, object]:
    page.modal_result = result
    page.modal_fingerprint = fingerprint
    page.modal_request_key = result.request.cache_key()
    page._populate_mode_table()
    lateral = [row for row in result.modal_modes if row.mode_type == "Lateral"]
    if not lateral:
        return {"pass": False, "reason": "No Lateral modes returned", "row_count": page.mode_table.rowCount()}
    first = lateral[0]
    actual = page.mode_table.item(0, 3).text() if page.mode_table.item(0, 3) is not None else ""
    expected = f"{first.wd_hz:.6g}"
    return {
        "row_count": page.mode_table.rowCount(),
        "first_mode_number": first.mode_number,
        "native_wd_hz": float(first.wd_hz),
        "gui_wd_hz_text": actual,
        "expected_gui_text": expected,
        "pass": bool(page.mode_table.rowCount() == len(lateral) and actual == expected),
    }


def run_foundation_feature_chain() -> dict[str, object]:
    import ross as rs

    if rs.__version__ != "2.3.0":
        raise RuntimeError(f"Foundation feature chain is pinned to ROSS 2.3.0, received {rs.__version__}.")

    app = _ensure_qapplication()
    model = load_reference_project_model()
    _sentinelize_support_chain(model)
    no_foundation_model = deepcopy(model)
    project = model.engineering
    no_project = no_foundation_model.engineering
    if project is None or no_project is None:
        raise RuntimeError("Reference project lost its engineering domain.")

    bearing = project.bearings[0]
    support = project.supports[0]
    distinct_sentinels = bool(
        bearing.name != support.name != str(_FOUNDATION_SENTINEL["name"])
        and len({bearing.kxx, support.kxx, float(_FOUNDATION_SENTINEL["kxx"])}) == 3
        and len({bearing.cxx, support.cxx, float(_FOUNDATION_SENTINEL["cxx"])}) == 3
    )

    foundation_page = FoundationWorkspacePage(model)
    baseline_record, gui_inputs = _baseline_record_from_gui(model)
    preview = foundation_page.mutations.preview_add(project, "foundation", baseline_record)
    foundation_page._commit_preview(preview)
    app.processEvents()
    committed = project.foundations[0]
    gui_table = {
        "name": foundation_page.table.item(0, 0).text(),
        "support_owner": foundation_page.table.item(0, 1).text(),
        "bearing_station": foundation_page.table.item(0, 2).text(),
        "model": foundation_page.table.item(0, 3).text(),
        "mass": foundation_page.table.item(0, 4).text(),
        "kxx": foundation_page.table.item(0, 5).text(),
        "kyy": foundation_page.table.item(0, 6).text(),
        "cxx": foundation_page.table.item(0, 7).text(),
        "frequency_rows": foundation_page.table.item(0, 8).text(),
    }
    gui_commit_pass = bool(
        committed == baseline_record
        and gui_table["name"] == committed.name
        and gui_table["support_owner"] == support.name
        and gui_table["mass"] == f"{committed.mass_kg:.6g}"
        and gui_table["kxx"] == f"{committed.kxx:.6g}"
        and gui_table["kyy"] == f"{committed.kyy:.6g}"
        and gui_table["cxx"] == f"{committed.cxx:.6g}"
        and gui_table["frequency_rows"] == "0"
    )

    no_builder = RossModelBuilder(rs)
    no_build = no_builder.build(no_project, strict=True)
    baseline_builder = RossModelBuilder(rs)
    baseline_build = baseline_builder.build(project, strict=True)
    baseline_rotor = baseline_build.rotor

    shaft_node = baseline_builder.map_position(project, bearing.position_mm).node
    support_node = baseline_build.support_link_nodes[support.name]
    foundation_node = baseline_builder.last_foundation_nodes[committed.name]
    bearing_element = next(element for element in baseline_rotor.bearing_elements if element.tag == bearing.name)
    support_element = next(element for element in baseline_rotor.bearing_elements if element.tag == f"{support.name} / foundation")
    foundation_element = next(element for element in baseline_rotor.bearing_elements if element.tag == f"{committed.name} / ground")
    foundation_mass = next(element for element in baseline_rotor.point_mass_elements if element.tag == f"{committed.name} mass")

    kb, cb = _matrices_from_spec(bearing)
    ks, cs = _matrices_from_spec(support)
    kf, cf = _matrices_from_spec(committed)
    local_matrix_evidence = {
        "bearing_k": _matrix_parity(bearing_element.K(0.0)[:2, :2], kb, rtol=0.0, atol=1.0e-9),
        "bearing_c": _matrix_parity(bearing_element.C(0.0)[:2, :2], cb, rtol=0.0, atol=1.0e-12),
        "support_k": _matrix_parity(support_element.K(0.0)[:2, :2], ks, rtol=0.0, atol=1.0e-9),
        "support_c": _matrix_parity(support_element.C(0.0)[:2, :2], cs, rtol=0.0, atol=1.0e-12),
        "foundation_k": _matrix_parity(foundation_element.K(0.0)[:2, :2], kf, rtol=0.0, atol=1.0e-9),
        "foundation_c": _matrix_parity(foundation_element.C(0.0)[:2, :2], cf, rtol=0.0, atol=1.0e-12),
    }
    local_matrix_pass = all(bool(row["pass"]) for row in local_matrix_evidence.values())

    topology = {
        "bearing_position_mm": float(bearing.position_mm),
        "shaft_node": int(shaft_node) if shaft_node is not None else None,
        "node_position_mm": None if shaft_node is None else float(baseline_build.node_positions_mm[shaft_node]),
        "bearing_n": int(bearing_element.n),
        "bearing_n_link": int(bearing_element.n_link),
        "support_node": int(support_node),
        "support_n": int(support_element.n),
        "support_n_link": int(support_element.n_link),
        "foundation_node": int(foundation_node),
        "foundation_n": int(foundation_element.n),
        "foundation_n_link": foundation_element.n_link,
        "foundation_mass_node": int(foundation_mass.n),
        "foundation_dof_contract": int(committed.dof),
        "native_classes": {
            "bearing": type(bearing_element).__name__,
            "support": type(support_element).__name__,
            "foundation": type(foundation_element).__name__,
            "foundation_mass": type(foundation_mass).__name__,
        },
    }
    topology_pass = bool(
        shaft_node is not None
        and abs(float(baseline_build.node_positions_mm[shaft_node]) - float(bearing.position_mm)) <= 1.0e-9
        and bearing_element.n == shaft_node
        and bearing_element.n_link == support_node
        and support_element.n == support_node
        and support_element.n_link == foundation_node
        and foundation_element.n == foundation_node
        and foundation_element.n_link is None
        and foundation_mass.n == foundation_node
        and abs(float(foundation_mass.m) - committed.mass_kg) <= 1.0e-12
        and committed.dof == 2
        and all(name == "BearingElement" for name in (
            type(bearing_element).__name__, type(support_element).__name__, type(foundation_element).__name__
        ))
    )

    manual_rotor, manual_foundation_node = _manual_lumped_kcm_rotor(rs, no_build, no_project.supports[0], committed)
    global_parity = {
        "M": _matrix_parity(baseline_rotor.M(), manual_rotor.M(), rtol=1.0e-12, atol=1.0e-10),
        "K0": _matrix_parity(baseline_rotor.K(0.0), manual_rotor.K(0.0), rtol=1.0e-12, atol=1.0e-6),
        "C0": _matrix_parity(baseline_rotor.C(0.0), manual_rotor.C(0.0), rtol=1.0e-12, atol=1.0e-9),
        "manual_foundation_node": int(manual_foundation_node),
    }
    global_parity_pass = all(bool(global_parity[key]["pass"]) for key in ("M", "K0", "C0"))

    m_global = np.asarray(baseline_rotor.M(), dtype=float)
    m_symmetric = bool(np.allclose(m_global, m_global.T, rtol=0.0, atol=1.0e-10))
    m_sym = 0.5 * (m_global + m_global.T)
    m_eigs = np.linalg.eigvalsh(m_sym)
    m_scale = max(float(np.max(np.abs(m_eigs))), 1.0)
    m_psd = bool(float(np.min(m_eigs)) >= -1.0e-10 * m_scale)
    local_k_eigs = np.linalg.eigvalsh(0.5 * (kf + kf.T))
    local_c_eigs = np.linalg.eigvalsh(0.5 * (cf + cf.T))
    structural = {
        "global_m_symmetric": m_symmetric,
        "global_m_min_eigenvalue": float(np.min(m_eigs)),
        "global_m_psd": m_psd,
        "foundation_k_symmetric_part_min_eigenvalue": float(np.min(local_k_eigs)),
        "foundation_c_symmetric_part_min_eigenvalue": float(np.min(local_c_eigs)),
        "foundation_k_positive_definite": bool(np.min(local_k_eigs) > 0.0),
        "foundation_c_positive_definite": bool(np.min(local_c_eigs) > 0.0),
    }
    structural_pass = bool(
        structural["global_m_symmetric"]
        and structural["global_m_psd"]
        and structural["foundation_k_positive_definite"]
        and structural["foundation_c_positive_definite"]
    )

    no_case, _, no_modal = _case_payload(rs, no_foundation_model, None)
    baseline_case, baseline_case_build, baseline_modal = _case_payload(rs, no_foundation_model, committed)
    stiff_foundation = _scaled_foundation(committed, 100.0, "QUAL-FDN-STIFF-91357")
    flexible_foundation = _scaled_foundation(committed, 0.1, "QUAL-FDN-FLEX-91357")
    stiff_case, stiff_build, stiff_modal = _case_payload(rs, no_foundation_model, stiff_foundation)
    flexible_case, _, flexible_modal = _case_payload(rs, no_foundation_model, flexible_foundation)

    compliance = {
        "no_foundation_um_per_n": _compliance_um_per_n(no_project.supports[0], None),
        "stiffer_um_per_n": _compliance_um_per_n(no_project.supports[0], stiff_foundation),
        "baseline_um_per_n": _compliance_um_per_n(no_project.supports[0], committed),
        "more_flexible_um_per_n": _compliance_um_per_n(no_project.supports[0], flexible_foundation),
    }
    response_coherence = bool(
        compliance["no_foundation_um_per_n"]
        < compliance["stiffer_um_per_n"]
        < compliance["baseline_um_per_n"]
        < compliance["more_flexible_um_per_n"]
        and not np.allclose(np.asarray(stiff_modal.wd), np.asarray(baseline_modal.wd), rtol=1.0e-7, atol=1.0e-7)
        and not np.allclose(np.asarray(flexible_modal.wd), np.asarray(baseline_modal.wd), rtol=1.0e-7, atol=1.0e-7)
    )
    cases = {
        "no_foundation": no_case,
        "baseline_foundation": baseline_case,
        "stiffer_foundation": stiff_case,
        "more_flexible_foundation": flexible_case,
        "zero_frequency_path_compliance_response": compliance,
        "physically_coherent_response_pass": response_coherence,
    }

    baseline_fp = project_fingerprint(model)
    modal_result = _minimal_modal_result(model, baseline_case_build, baseline_modal)
    modal_page = StaticModalWorkspacePage(model, mode_filter="Lateral")
    gui_result = _table_modal_evidence(modal_page, modal_result, baseline_fp)

    persistence: dict[str, object]
    with TemporaryDirectory(prefix="ross_foundation_qualification_") as temp_dir:
        target = save_project(model, Path(temp_dir) / "foundation-feature.rossproj")
        reopened = load_project(target)
        if reopened.engineering is None:
            raise RuntimeError("Reopened Foundation qualification project lost the engineering domain.")
        reopened_builder = RossModelBuilder(rs)
        reopened_build = reopened_builder.build(reopened.engineering, strict=True)
        _, reopened_modal = _positive_modal_hz(reopened_build.rotor)
        persistence = {
            "foundation_equal": reopened.engineering.foundations == project.foundations,
            "support_equal": reopened.engineering.supports[0] == project.supports[0],
            "bearing_equal": reopened.engineering.bearings[0] == project.bearings[0],
            "M": _matrix_parity(reopened_build.rotor.M(), baseline_rotor.M(), rtol=1.0e-12, atol=1.0e-10),
            "K0": _matrix_parity(reopened_build.rotor.K(0.0), baseline_rotor.K(0.0), rtol=1.0e-12, atol=1.0e-6),
            "C0": _matrix_parity(reopened_build.rotor.C(0.0), baseline_rotor.C(0.0), rtol=1.0e-12, atol=1.0e-9),
            "modal_wd": _matrix_parity(np.asarray(reopened_modal.wd), np.asarray(baseline_modal.wd), rtol=1.0e-11, atol=1.0e-9),
        }
    persistence_pass = bool(
        persistence["foundation_equal"]
        and persistence["support_equal"]
        and persistence["bearing_equal"]
        and all(bool(persistence[key]["pass"]) for key in ("M", "K0", "C0", "modal_wd"))
    )

    stale_model = deepcopy(model)
    stale_modal_result = _minimal_modal_result(stale_model, baseline_case_build, baseline_modal)
    stale_page = StaticModalWorkspacePage(stale_model, mode_filter="Lateral")
    stale_fp = project_fingerprint(stale_model)
    _table_modal_evidence(stale_page, stale_modal_result, stale_fp)
    stale_foundation_page = FoundationWorkspacePage(stale_model)
    stale_project = stale_model.engineering
    if stale_project is None:
        raise RuntimeError("Stale-result probe lost engineering domain.")
    stiff_update = _scaled_foundation(stale_project.foundations[0], 2.0, stale_project.foundations[0].name)
    update_preview = stale_foundation_page.mutations.preview_update(
        stale_project, "foundation", 0, stale_foundation_page._changes(stiff_update)
    )
    stale_foundation_page._commit_preview(update_preview)
    stale_page._invalidate_if_project_changed()
    stale_results_pass = bool(
        stale_page.modal_result is None
        and stale_page.mode_table.rowCount() == 0
        and "invalidated" in stale_page.modal_state.text().casefold()
    )

    race_model = deepcopy(model)
    race_project = race_model.engineering
    if race_project is None:
        raise RuntimeError("Race-protection probe lost engineering domain.")
    old_fp = project_fingerprint(race_model)
    old_result = _minimal_modal_result(race_model, baseline_case_build, baseline_modal)
    race_foundation_page = FoundationWorkspacePage(race_model)
    race_stiff = _scaled_foundation(race_project.foundations[0], 100.0, race_project.foundations[0].name)
    race_preview = race_foundation_page.mutations.preview_update(
        race_project, "foundation", 0, race_foundation_page._changes(race_stiff)
    )
    race_foundation_page._commit_preview(race_preview)
    new_fp = project_fingerprint(race_model)
    new_result = _minimal_modal_result(race_model, stiff_build, stiff_modal)
    race_page = StaticModalWorkspacePage(race_model, mode_filter="Lateral")
    new_gui = _table_modal_evidence(race_page, new_result, new_fp)
    before_text = race_page.mode_table.item(0, 3).text() if race_page.mode_table.item(0, 3) is not None else ""
    race_page._on_modal_success(old_result, old_fp)
    after_text = race_page.mode_table.item(0, 3).text() if race_page.mode_table.item(0, 3) is not None else ""
    race_protection_pass = bool(
        new_gui["pass"]
        and race_page.modal_result is new_result
        and before_text == after_text
        and "discarded" in race_page.modal_state.text().casefold()
    )

    fd_model = deepcopy(no_foundation_model)
    fd_project = fd_model.engineering
    if fd_project is None:
        raise RuntimeError("Frequency-conversion probe lost engineering domain.")
    fd_record, gui_hz = _frequency_record_from_gui(fd_model)
    fd_page = FoundationWorkspacePage(fd_model)
    fd_preview = fd_page.mutations.preview_add(fd_project, "foundation", fd_record)
    fd_page._commit_preview(fd_preview)
    fd_builder = RossModelBuilder(rs)
    fd_build = fd_builder.build(fd_project, strict=True)
    fd_element = next(
        element for element in fd_build.rotor.bearing_elements
        if element.tag == f"{fd_record.name} / condensed ground"
    )
    expected_rad_s = np.asarray(gui_hz, dtype=float) * 2.0 * pi
    native_rad_s = np.asarray(fd_element.frequency, dtype=float)
    frequency_conversion = {
        "gui_unit": "Hz",
        "native_unit": "rad/s",
        "formula": "omega = 2*pi*f",
        "gui_hz": [float(value) for value in gui_hz],
        "expected_rad_s": [float(value) for value in expected_rad_s],
        "native_rad_s": [float(value) for value in native_rad_s],
        "max_abs_error": float(np.max(np.abs(native_rad_s - expected_rad_s))),
        "pass": bool(np.allclose(native_rad_s, expected_rad_s, rtol=0.0, atol=1.0e-12)),
    }

    unit_identity = {
        "foundation_mass": {"gui": gui_inputs["mass_kg"], "native": float(foundation_mass.m), "unit": "kg"},
        "foundation_kxx": {"gui": gui_inputs["kxx_n_m"], "native": float(foundation_element.K(0.0)[0, 0]), "unit": "N/m"},
        "foundation_kyx": {"gui": gui_inputs["kyx_n_m"], "native": float(foundation_element.K(0.0)[1, 0]), "unit": "N/m"},
        "foundation_cxx": {"gui": gui_inputs["cxx_n_s_m"], "native": float(foundation_element.C(0.0)[0, 0]), "unit": "N*s/m"},
        "foundation_cyx": {"gui": gui_inputs["cyx_n_s_m"], "native": float(foundation_element.C(0.0)[1, 0]), "unit": "N*s/m"},
    }
    unit_identity_pass = all(
        abs(float(item["gui"]) - float(item["native"])) <= 1.0e-9
        for item in unit_identity.values()
    )

    no_silent_fallback = bool(
        topology_pass
        and local_matrix_pass
        and committed.model_type == FoundationModel.LUMPED_KCM
        and committed.name in baseline_builder.last_foundation_nodes
        and not any("condensed ground" in str(getattr(element, "tag", "")) for element in baseline_rotor.bearing_elements if committed.name in str(getattr(element, "tag", "")))
    )

    gates = {
        "distinct_bearing_support_foundation_sentinels": distinct_sentinels,
        "gui_input_to_domain_commit": gui_commit_pass,
        "unit_identity_si_boundary": unit_identity_pass,
        "frequency_hz_to_rad_s_conversion": bool(frequency_conversion["pass"]),
        "identity_topology_station_dof_signs": topology_pass and local_matrix_pass,
        "independent_global_mck_parity": global_parity_pass,
        "matrix_structural_properties": structural_pass,
        "four_case_physical_response": response_coherence,
        "native_modal_numeric_result": bool(np.all(np.isfinite(np.asarray(baseline_modal.wd, dtype=float)))),
        "gui_result_rendering": bool(gui_result["pass"]),
        "save_reopen_recompute": persistence_pass,
        "stale_result_invalidation": stale_results_pass,
        "async_race_obsolete_result_rejected": race_protection_pass,
        "no_silent_fallback": no_silent_fallback,
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    for widget in (
        foundation_page,
        modal_page,
        stale_page,
        stale_foundation_page,
        race_foundation_page,
        race_page,
        fd_page,
    ):
        widget.close()
    app.processEvents()

    return {
        "status": status,
        "ross_version": rs.__version__,
        "gates": gates,
        "gui_inputs": gui_inputs,
        "gui_committed_table": gui_table,
        "sentinels": {
            "bearing": dict(_BEARING_SENTINEL),
            "support": dict(_SUPPORT_SENTINEL),
            "foundation": dict(_FOUNDATION_SENTINEL),
        },
        "unit_identity": unit_identity,
        "frequency_conversion": frequency_conversion,
        "topology": topology,
        "local_matrix_evidence": local_matrix_evidence,
        "global_matrix_parity": global_parity,
        "structural_matrix_properties": structural,
        "cases": cases,
        "gui_result": gui_result,
        "persistence": persistence,
        "stale_results": {
            "pass": stale_results_pass,
            "state": stale_page.modal_state.text(),
        },
        "race_protection": {
            "pass": race_protection_pass,
            "old_fingerprint": old_fp,
            "new_fingerprint": new_fp,
            "new_gui_wd_before": before_text,
            "new_gui_wd_after_stale_completion": after_text,
            "state": race_page.modal_state.text(),
        },
        "no_silent_fallback": no_silent_fallback,
    }


def run_foundation_feature_qualification() -> FoundationFeatureQualification:
    science = run_foundation_qualification()
    feature_chain = run_foundation_feature_chain()
    status = "PASS" if science.status == "PASS" and feature_chain.get("status") == "PASS" else "FAIL"
    return FoundationFeatureQualification(status=status, science=science, feature_chain=feature_chain)


__all__ = [
    "FoundationFeatureQualification",
    "run_foundation_feature_chain",
    "run_foundation_feature_qualification",
]
