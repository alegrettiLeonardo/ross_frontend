from __future__ import annotations

from copy import deepcopy

import pytest

from ross_studio.navigation_registry import (
    NAVIGATION_NODES,
    canonical_route,
    children,
    navigation_node,
    public_routes,
)
from ross_studio.page_registry import PAGE_ROUTES, route_spec


EXPECTED_ROUTES = (
    "home.project",
    "model.shaft",
    "model.masses",
    "model.bearings.general",
    "model.bearings.fluid_film",
    "model.bearings.amb",
    "model.seals",
    "model.supports.flexible",
    "model.supports.foundation",
    "model.couplings",
    "model.loads.unbalance",
    "model.loads.harmonic",
    "model.loads.electromagnetic",
    "model.probes",
    "analysis.static_modal.lateral",
    "analysis.static_modal.torsional",
    "analysis.time_frequency",
    "analysis.stochastic",
    "analysis.multirotor",
)


def test_navigation_registry_exact_public_routes() -> None:
    assert public_routes() == EXPECTED_ROUTES
    assert tuple(PAGE_ROUTES) == EXPECTED_ROUTES


def test_navigation_hierarchy_matches_approved_architecture() -> None:
    assert [node.id for node in children("home")] == ["home.project"]
    assert [node.id for node in children("model")] == [
        "model.shaft",
        "model.masses",
        "model.bearings",
        "model.seals",
        "model.supports",
        "model.couplings",
        "model.loads",
        "model.probes",
    ]
    assert [node.id for node in children("model.bearings")] == [
        "model.bearings.general",
        "model.bearings.fluid_film",
        "model.bearings.amb",
    ]
    assert [node.id for node in children("model.supports")] == [
        "model.supports.flexible",
        "model.supports.foundation",
    ]
    assert [node.id for node in children("model.loads")] == [
        "model.loads.unbalance",
        "model.loads.harmonic",
        "model.loads.electromagnetic",
    ]
    assert [node.id for node in children("analysis")] == [
        "analysis.static_modal",
        "analysis.time_frequency",
        "analysis.stochastic",
        "analysis.multirotor",
    ]
    assert [node.id for node in children("analysis.static_modal")] == [
        "analysis.static_modal.lateral",
        "analysis.static_modal.torsional",
    ]


def test_no_public_global_ump_or_results_route() -> None:
    routes = set(public_routes())
    assert "ump" not in routes
    assert "results" not in routes
    assert all(not route.endswith(".results") for route in routes)
    assert canonical_route("ump") == "model.loads.electromagnetic"
    assert canonical_route("results") == "analysis.static_modal.lateral"


def test_amb_route_is_visible_but_locked() -> None:
    node = navigation_node("model.bearings.amb")
    spec = route_spec(node.id)
    assert node.kind == "route"
    assert node.locked is True
    assert spec.owner == "bearing"
    assert spec.bearing_group == "AMB"
    assert spec.operational is False


def test_foundation_has_distinct_owner_from_flexible_support() -> None:
    support = route_spec("model.supports.flexible")
    foundation = route_spec("model.supports.foundation")
    assert support.owner == "rotor"
    assert support.editor_key == "supports"
    assert foundation.owner == "foundation"
    assert foundation.editor_key is None
    assert foundation.implementation_phase == "0.19.0"


def test_every_public_route_has_one_page_owner() -> None:
    assert set(PAGE_ROUTES) == set(EXPECTED_ROUTES)
    assert all(PAGE_ROUTES[route].owner for route in EXPECTED_ROUTES)


def test_legacy_flat_aliases_do_not_create_public_states() -> None:
    assert canonical_route("rotor") == "model.shaft"
    assert canonical_route("shaft") == "model.shaft"
    assert canonical_route("bearings") == "model.bearings.general"
    assert canonical_route("supports") == "model.supports.flexible"
    assert canonical_route("response") == "analysis.time_frequency"
    assert canonical_route("stochastic") == "analysis.stochastic"


def test_registry_ids_are_unique() -> None:
    ids = [node.id for node in NAVIGATION_NODES]
    assert len(ids) == len(set(ids))


def test_sidebar_renders_new_tree_and_preserves_frozen_legacy_aliases(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)

    assert set(window.sidebar.route_buttons) == set(EXPECTED_ROUTES)
    # Compatibility aliases keep the already-qualified frozen 0.15 smoke usable,
    # without reintroducing the duplicate visible Shaft state.
    assert {"rotor", "disks", "bearings", "seals", "supports", "couplings", "loads", "ump", "probes"} <= set(window.sidebar.buttons)
    assert "shaft" not in window.sidebar.buttons
    assert window.sidebar.route_buttons["model.bearings.amb"].isEnabled() is False


def test_home_foundation_and_analysis_have_dedicated_page_owners(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow
    from ross_studio.pages.architecture_workspaces import AnalysisRoutePage, FoundationWorkspacePage
    from ross_studio.pages.project_home import ProjectHomePage
    from ross_studio.pages.stochastic_workspace import StochasticWorkspacePage

    window = RossStudioWindow()
    qtbot.addWidget(window)

    window._navigate("home.project")
    assert isinstance(window.stack.currentWidget(), ProjectHomePage)

    window._navigate("model.supports.foundation")
    foundation = window.stack.currentWidget()
    assert isinstance(foundation, FoundationWorkspacePage)
    assert foundation is not window.rotor_page

    analysis_pages = []
    for route in (
        "analysis.static_modal.lateral",
        "analysis.static_modal.torsional",
        "analysis.time_frequency",
        "analysis.stochastic",
        "analysis.multirotor",
    ):
        window._navigate(route)
        page = window.stack.currentWidget()
        if route == "analysis.stochastic":
            assert isinstance(page, StochasticWorkspacePage)
            assert route_spec(route).operational is True
        else:
            assert isinstance(page, AnalysisRoutePage)
            assert page.spec.route_id == route
        assert page is not window.results_page
        analysis_pages.append(page)
    assert len({id(page) for page in analysis_pages}) == len(analysis_pages)


def test_navigation_never_mutates_engineering_model(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    engineering = window.project.engineering
    assert engineering is not None
    before = deepcopy(engineering)

    for route in EXPECTED_ROUTES:
        if route == "model.bearings.amb":
            # Public UI blocks this route; direct application routing is still
            # deterministic and must not mutate the physical model.
            window._navigate(route)
        else:
            window.sidebar.set_active(route)
    assert engineering == before


def test_bearing_family_routes_reuse_single_bearing_workspace(qtbot) -> None:
    pytest.importorskip("ross")
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    page = window.bearing_page

    window._navigate("model.bearings.general")
    assert window.stack.currentWidget() is page
    assert page.current_group.value == "General / Parametric"

    window._navigate("model.bearings.fluid_film")
    assert window.stack.currentWidget() is page
    assert page.current_group.value == "THD"
