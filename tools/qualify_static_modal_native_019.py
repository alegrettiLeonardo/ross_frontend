from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ROSS_STUDIO_DISABLE_WEBENGINE", "1")

from PySide6.QtWidgets import QApplication

from ross_studio import __version__
from ross_studio.models import ProjectModel, load_reference_project_model
from ross_studio.pages.static_modal_workspace import StaticModalWorkspacePage
from ross_studio.static_modal_analysis import StaticModalAnalysisService, StaticModalRequest
from ross_studio.static_modal_native import StaticModalNativeFigureCatalog


OUT = Path("artifacts/static_modal_native_019")
QUALIFICATION = Path("artifacts/static_modal_native_019_qualification.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    import ross

    project = load_reference_project_model()
    engineering = deepcopy(project.engineering)
    require(engineering is not None, "Reference project lost RotorProject")
    engineering.loads = [load for load in engineering.loads if load.kind.strip().casefold() != "unbalance"]
    model = ProjectModel.from_engineering(engineering)
    case = engineering.operating_cases[0]

    request = StaticModalRequest(
        speed_rpm=case.rated_speed_rpm,
        num_modes=32,
        campbell_points=13,
        campbell_frequencies=8,
        include_static=True,
    )
    result = StaticModalAnalysisService().run(engineering, request)
    require(result.build.unresolved_positions_mm == [], "Static/Modal strict rotor has unresolved positions")
    require(result.static is not None, "Native ROSS StaticResults missing")
    require(result.modal is not None, "Native ROSS ModalResults missing")
    require(result.campbell is not None, "Native ROSS CampbellResults missing")
    require(not any(load.kind.strip().casefold() == "unbalance" for load in engineering.loads), "Unbalance leaked into dedicated Static/Modal input")

    catalog = StaticModalNativeFigureCatalog(result)
    OUT.mkdir(parents=True, exist_ok=True)

    static_exports: dict[str, str] = {}
    static_sources: dict[str, str] = {}
    for key in ("free_body", "deformation", "shearing_force", "bending_moment"):
        figure = catalog.static_figure(key)
        require(len(getattr(figure, "data", ())) > 0, f"Native ROSS static figure {key} is empty")
        path = catalog.export_png(figure, OUT / f"static_{key}.png")
        static_exports[key] = str(path)
        static_sources[key] = catalog.static_spec(key).source_method

    lateral = catalog.mode_indices("Lateral")
    torsional = catalog.mode_indices("Torsional")
    require(bool(lateral), "No lateral mode returned by ROSS")
    require(bool(torsional), "No torsional mode returned by ROSS; cannot qualify torsional workspace")

    lateral_mode = lateral[0]
    torsional_mode = torsional[0]
    lateral_2d = catalog.mode_figure(lateral_mode, dimension="2d")
    lateral_3d = catalog.mode_figure(lateral_mode, dimension="3d")
    lateral_anim = catalog.mode_figure(lateral_mode, dimension="3d", animation=True)
    torsional_anim = catalog.mode_figure(torsional_mode, dimension="3d", animation=True)
    require(len(getattr(lateral_anim, "frames", ())) > 0, "ROSS lateral 3D animation contains no frames")
    require(len(getattr(torsional_anim, "frames", ())) > 0, "ROSS torsional 3D animation contains no frames")

    modal_exports = {
        "lateral_2d_png": str(catalog.export_png(lateral_2d, OUT / "mode_lateral_2d.png")),
        "lateral_3d_png": str(catalog.export_png(lateral_3d, OUT / "mode_lateral_3d.png")),
        "lateral_animation_html": str(catalog.export_html(lateral_anim, OUT / "mode_lateral_3d_animated.html")),
        "torsional_animation_html": str(catalog.export_html(torsional_anim, OUT / "mode_torsional_3d_animated.html")),
    }

    campbell = catalog.campbell_figure((0.5, 1.0))
    require(len(getattr(campbell, "data", ())) > 0, "Native ROSS Campbell plot is empty")
    campbell_png = catalog.export_png(campbell, OUT / "campbell_harmonics_0p5_1p0.png")

    app = QApplication.instance() or QApplication([])
    lateral_page = StaticModalWorkspacePage(model, mode_filter="Lateral")
    torsional_page = StaticModalWorkspacePage(model, mode_filter="Torsional")
    lateral_page.set_result(result)
    torsional_page.set_result(result)
    app.processEvents()
    require(lateral_page.mode_table.rowCount() == len(lateral), "Lateral GUI mode filtering mismatch")
    require(torsional_page.mode_table.rowCount() == len(torsional), "Torsional GUI mode filtering mismatch")
    torsional_page.animate.setChecked(True)
    app.processEvents()
    require(len(getattr(torsional_page.mode_view.figure, "frames", ())) > 0, "GUI did not retain native ROSS animation frames")

    payload = {
        "status": "PASS",
        "ross_version": ross.__version__,
        "ross_studio_version": __version__,
        "project": model.name,
        "strict_rotor": True,
        "unresolved_positions_mm": result.build.unresolved_positions_mm,
        "unbalance_required": False,
        "scientific_calls": ["Rotor.run_static", "Rotor.run_modal", "Rotor.run_campbell"],
        "scientific_recompute_on_plot_change": catalog.scientific_recompute,
        "native_static_sources": static_sources,
        "native_static_png": static_exports,
        "modal": {
            "mode_count": len(result.modal_modes),
            "lateral_indices": list(lateral),
            "torsional_indices": list(torsional),
            "plot_2d": "ModalResults.plot_mode_2d",
            "plot_3d": "ModalResults.plot_mode_3d",
            "animation_call": "ModalResults.plot_mode_3d(mode, animation=True)",
            "lateral_animation_frames": len(getattr(lateral_anim, "frames", ())),
            "torsional_animation_frames": len(getattr(torsional_anim, "frames", ())),
            "exports": modal_exports,
        },
        "campbell": {
            "source": "CampbellResults.plot",
            "harmonics": [0.5, 1.0],
            "png": str(campbell_png),
        },
        "gui": {
            "lateral_workspace": True,
            "torsional_workspace": True,
            "animation_toggle": True,
            "html_preserves_animation": True,
            "global_results_sidebar_route_added": False,
        },
        "tutorial_contract": [
            "static.plot_free_body_diagram()",
            "static.plot_deformation()",
            "static.plot_shearing_force()",
            "static.plot_bending_moment()",
            "modal.plot_mode_2d(mode)",
            "modal.plot_mode_3d(mode)",
            "modal.plot_mode_3d(torsional_mode, animation=True)",
            "campbell.plot(harmonics=[0.5, 1])",
        ],
    }
    QUALIFICATION.parent.mkdir(parents=True, exist_ok=True)
    QUALIFICATION.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    lateral_page.close()
    torsional_page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
