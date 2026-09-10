from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from ross_studio.bearing_workspace import BearingWorkspaceService
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_bearing_workspace_exposes_both_op_w60_physical_stations() -> None:
    project = load_irdin_project(FIXTURE)
    stations = BearingWorkspaceService.stations(project)

    assert len(stations) == 2
    assert [station.index for station in stations] == [0, 1]
    assert [station.position_mm for station in stations] == pytest.approx([467.8, 2202.2])
    assert [station.ross_node for station in stations] == [5, 23]
    assert all(station.source_model == "BearingElement" for station in stations)
    assert stations[0].support_names
    assert stations[1].support_names
    assert stations[0].support_names != stations[1].support_names


def test_bearing_studio_2_routes_directly_to_workspace_and_selects_nde(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)

    window._navigate("bearings")
    assert window.stack.currentWidget() is window.bearing_page
    assert window.stack.count() == 3
    assert not hasattr(window, "bearing_groups_page")
    assert window.bearing_page.bearing_selector.count() == 2

    nde_row = window.bearing_page.bearing_selector.findData(1)
    assert nde_row >= 0
    window.bearing_page.bearing_selector.setCurrentIndex(nde_row)
    qtbot.wait(1)

    assert window.bearing_index == 1
    assert window.bearing.name == window.project.engineering.bearings[1].name
    assert window.bearing_page.bearing_index == 1
    assert window.bearing_page.bearing_selector.currentData() == 1


def test_nde_ball_calculate_preview_apply_isolated_from_de(qtbot, monkeypatch) -> None:
    rs = pytest.importorskip("ross")
    import ross_studio.app as app_module

    captured: dict[str, object] = {}

    class FakeBearingInputDialog:
        def __init__(self, project, index, ross_class, parent=None):
            captured["index"] = index
            captured["ross_class"] = ross_class

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "n_balls": 9,
                "d_balls_m": 0.028,
                "static_load_n": 900.0,
                "contact_angle_rad": 0.15,
            }

    monkeypatch.setattr(app_module, "BearingInputDialog", FakeBearingInputDialog)

    window = app_module.RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None

    de_before = deepcopy(engineering.bearings[0])
    nde_before = deepcopy(engineering.bearings[1])

    window._select_bearing(1)
    key = window._bearing_key_for_class(window.bearing_page, "BallBearingElement")
    assert key is not None
    window.bearing_page.set_group("General / Parametric", announce=False)
    window.bearing_page._select_type(key, announce=False)

    window._calculate_bearing()

    assert captured == {"index": 1, "ross_class": "BallBearingElement"}
    assert window.bearing_context is not None
    assert window.bearing_context.bearing_index == 1
    assert window.bearing_calculation is not None
    assert window.bearing_calculation.source_model == "BallBearingElement"
    assert engineering.bearings[0] == de_before
    assert engineering.bearings[1] == nde_before
    assert window.bearing_page.apply_button.isEnabled()

    window._apply_bearing()

    assert engineering.bearings[0] == de_before
    assert engineering.bearings[1] != nde_before
    assert engineering.bearings[1].metadata["source_model"] == "BallBearingElement"
    assert engineering.bearings[1].metadata["n_balls"] == 9
    assert window.bearing_index == 1
    assert not window.bearing_page.apply_button.isEnabled()

    built = RossModelBuilder(rs).build(engineering, strict=True)
    links = [element.n_link for element in built.rotor.bearing_elements[:2]]
    assert links == [28, 29]


def test_switching_station_invalidates_unapplied_preview(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None
    before = deepcopy(engineering.bearings)

    window._select_bearing(1)
    window.bearing_page.set_group("General / Parametric", announce=False)
    kc_key = window._bearing_key_for_class(window.bearing_page, "BearingElement")
    assert kc_key is not None
    window.bearing_page._select_type(kc_key, announce=False)
    window._calculate_bearing()
    assert window.bearing_context is not None
    assert window.bearing_page.apply_button.isEnabled()

    window._select_bearing(0)

    assert window.bearing_context is None
    assert window.bearing_calculation is None
    assert not window.bearing_page.apply_button.isEnabled()
    assert engineering.bearings == before
