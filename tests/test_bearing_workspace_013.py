from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from ross_studio.bearing_workspace import BearingWorkspaceService
from ross_studio.domain import BearingSpec, EngineeringError
from ross_studio.legacy_import import load_irdin_project
from ross_studio.ross_backend import RossModelBuilder
from ross_studio.rotor_selection import RotorEntityRef, WORKSPACE_SELECTION
from ross_studio.topology import NodeInsertionService


FIXTURE = Path(__file__).parents[1] / "src" / "ross_studio" / "resources" / "OP-W60-500-60Hz-IC611-P3.txt"


def test_bearing_workspace_exposes_both_op_w60_physical_stations() -> None:
    project = load_irdin_project(FIXTURE)
    stations = BearingWorkspaceService.stations(project)
    plan = NodeInsertionService.plan(project)

    assert len(stations) == 2
    assert [station.index for station in stations] == [0, 1]
    assert [station.position_mm for station in stations] == pytest.approx([467.8, 2202.2])
    assert all(station.ross_node is not None for station in stations)
    assert len({station.ross_node for station in stations}) == 2
    assert [station.ross_node for station in stations] == [
        plan.node_for(station.position_mm) for station in stations
    ]
    assert all(station.source_model == "BearingElement" for station in stations)
    assert stations[0].support_names
    assert stations[1].support_names
    assert stations[0].support_names != stations[1].support_names


def test_axial_auxiliary_is_not_a_new_selectable_bearing_station() -> None:
    project = load_irdin_project(FIXTURE)
    project.bearings.append(
        BearingSpec(
            name="ThrustPad axial auxiliary",
            position_mm=project.bearings[0].position_mm,
            ross_class="BearingElement",
            metadata={
                "source_model": "ThrustPad",
                "axial_coefficients": [{"rpm": 3600.0, "kzz": 1.0e8, "czz": 1.0e5}],
            },
        )
    )

    stations = BearingWorkspaceService.stations(project)
    assert [station.index for station in stations] == [0, 1]
    assert BearingWorkspaceService.anchor_index(project, 2) == 0
    with pytest.raises(EngineeringError, match="axial auxiliary"):
        BearingWorkspaceService.resolve_index(project, 2)


def test_station_inventory_separates_radial_anchor_and_axial_auxiliary() -> None:
    project = load_irdin_project(FIXTURE)
    workspace = BearingWorkspaceService()

    baseline_de = workspace.inventory(project, 0)
    baseline_nde = workspace.inventory(project, 1)
    assert baseline_de.radial_anchor.element_index == 0
    assert baseline_de.radial_anchor.role == "radial_anchor"
    assert baseline_de.axial_auxiliaries == ()
    assert baseline_nde.radial_anchor.element_index == 1
    assert baseline_nde.axial_auxiliaries == ()

    project.bearings.append(
        BearingSpec(
            name="DE thrust bearing",
            position_mm=project.bearings[0].position_mm,
            ross_class="BearingElement",
            metadata={
                "source_model": "ThrustPad",
                "axial_coefficients": [{"rpm": 3600.0, "kzz": 2.0e8, "czz": 2.0e5}],
            },
        )
    )

    de = workspace.inventory(project, 0)
    nde = workspace.inventory(project, 1)
    assert [element.element_index for element in de.elements] == [0, 2]
    assert [element.role for element in de.elements] == ["radial_anchor", "axial_auxiliary"]
    assert de.axial_auxiliaries[0].source_model == "ThrustPad"
    assert de.axial_auxiliaries[0].axial is True
    assert de.axial_auxiliaries[0].position_mm == pytest.approx(de.station.position_mm)
    assert de.station.ross_node == NodeInsertionService.plan(project).node_for(de.station.position_mm)
    assert de.station.support_names

    assert [element.element_index for element in nde.elements] == [1]
    assert nde.radial_anchor.element_index == 1
    assert nde.axial_auxiliaries == ()


def test_orphan_axial_auxiliary_is_fail_closed() -> None:
    project = load_irdin_project(FIXTURE)
    project.bearings.append(
        BearingSpec(
            name="orphan thrust",
            position_mm=1000.0,
            ross_class="BearingElement",
            metadata={
                "source_model": "ThrustPad",
                "axial_coefficients": [{"rpm": 3600.0, "kzz": 1.0e8, "czz": 1.0e5}],
            },
        )
    )
    with pytest.raises(EngineeringError, match="no physical radial station anchor"):
        BearingWorkspaceService.anchor_index(project, 2)


def test_bearing_studio_2_routes_directly_to_workspace_and_selects_nde(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    WORKSPACE_SELECTION.clear()
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
    assert WORKSPACE_SELECTION.current is not None
    assert WORKSPACE_SELECTION.current.kind == "bearings"
    assert WORKSPACE_SELECTION.current.index == 1


def test_rotor_selection_drives_bearing_station_and_axial_selection_canonicalizes(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None

    nde = engineering.bearings[1]
    WORKSPACE_SELECTION.select(RotorEntityRef("bearings", 1, nde.name, nde.position_mm))
    qtbot.waitUntil(lambda: window.bearing_index == 1)
    assert window.stack.currentWidget() is window.bearing_page
    assert window.bearing_page.bearing_selector.currentData() == 1

    de = engineering.bearings[0]
    engineering.bearings.append(
        BearingSpec(
            name="DE thrust bearing",
            position_mm=de.position_mm,
            ross_class="BearingElement",
            metadata={
                "source_model": "ThrustPad",
                "axial_coefficients": [{"rpm": 3600.0, "kzz": 2.0e8, "czz": 2.0e5}],
            },
        )
    )
    axial_index = len(engineering.bearings) - 1

    WORKSPACE_SELECTION.select(RotorEntityRef("bearings", axial_index, "DE thrust bearing", de.position_mm))
    qtbot.waitUntil(lambda: window.bearing_index == 0)
    assert window.bearing_page.bearing_selector.count() == 2
    assert window.bearing_page.bearing_selector.currentData() == 0
    assert window.bearing_page.inventory is not None
    assert [element.role for element in window.bearing_page.inventory.elements] == [
        "radial_anchor",
        "axial_auxiliary",
    ]
    assert any("ThrustPad" in label.text() for label in window.bearing_page.findChildren(QLabel))
    assert WORKSPACE_SELECTION.current is not None
    assert WORKSPACE_SELECTION.current.index == 0
    assert WORKSPACE_SELECTION.current.position_mm == pytest.approx(de.position_mm)

    WORKSPACE_SELECTION.clear()


def test_nde_ball_calculate_preview_apply_isolated_from_de(qtbot) -> None:
    rs = pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None

    de_before = deepcopy(engineering.bearings[0])
    nde_before = deepcopy(engineering.bearings[1])

    window._select_bearing(1)
    key = window._bearing_key_for_class(window.bearing_page, "BallBearingElement")
    assert key is not None
    window.bearing_page._select_type(key, announce=False)

    panel = window.bearing_page.input_panel
    panel.fields["n_balls"].setValue(9)
    panel.fields["d_balls_mm"].setValue(28.0)
    panel.fields["static_load_n"].setValue(900.0)
    panel.fields["contact_angle_deg"].setValue(0.15 * 180.0 / 3.141592653589793)
    entered = panel.values()
    assert entered["n_balls"] == 9
    assert entered["d_balls_m"] == pytest.approx(0.028)
    assert entered["static_load_n"] == pytest.approx(900.0)
    assert entered["contact_angle_rad"] == pytest.approx(0.15)

    window._calculate_bearing()

    assert window.bearing_context is not None
    assert window.bearing_context.bearing_index == 1
    assert window.bearing_calculation is not None
    assert window.bearing_calculation.source_model == "BallBearingElement"
    assert engineering.bearings[0] == de_before
    assert engineering.bearings[1] == nde_before
    assert window.bearing_page.apply_button.isEnabled()
    assert window.bearing_page.results_button.isEnabled()

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

    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None
    before = deepcopy(engineering.bearings)

    window._select_bearing(1)
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
