from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any

from .domain import BearingGroup


@dataclass(slots=True, frozen=True)
class FrozenGuiSmokeResult:
    status: str
    window_title: str
    project: str
    sidebar_routes: tuple[str, ...]
    view_modes: tuple[str, ...]
    rotor_editor_count: int
    bearing_station_count: int
    bearing_direct_route: bool
    bearing_selection_synced: bool
    bearing_station_inventory: tuple[tuple[str, ...], ...]
    general_executable: tuple[str, ...]
    thd_executable: tuple[str, ...]
    amb_blocked: tuple[str, ...]
    bearing_model_icon_count: int
    bearing_inline_input: bool
    bearing_results_below: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_frozen_gui_smoke() -> FrozenGuiSmokeResult:
    """Construct the production Qt window and qualify the current non-modal workflow.

    The scientific self-test validates the backend. This companion gate proves the
    frozen desktop shell exposes the physical bearing stations and the 0.14.1 inline
    Bearing Studio: direct model icons, visible engineering inputs and results below
    the editor. No legacy bearing-input modal is allowed on the production path.
    """

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QTabWidget

    from .app import RossStudioWindow
    from .rotor_selection import RotorEntityRef, WORKSPACE_SELECTION

    app = QApplication.instance() or QApplication([])
    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    try:
        project = window.project
        if project.engineering is None:
            raise RuntimeError("GUI startup did not load the OP-W60 engineering model.")

        expected_routes = {
            "rotor", "shaft", "disks", "bearings", "seals", "supports",
            "couplings", "loads", "ump", "probes",
        }
        available_routes = set(window.sidebar.buttons)
        missing_routes = expected_routes - available_routes
        if missing_routes:
            raise RuntimeError(f"Frozen sidebar is missing model routes: {sorted(missing_routes)}")

        if window.rotor_page.findChildren(QTabWidget):
            raise RuntimeError("Frozen Rotor workspace unexpectedly contains a duplicate QTabWidget model navigator.")
        if window.rotor_page.editor_stack.count() != 8:
            raise RuntimeError(
                f"Frozen Rotor workspace expected 8 engineering editor pages, received {window.rotor_page.editor_stack.count()}."
            )

        view_modes = tuple(window.toolbar.view_combo.itemText(i) for i in range(window.toolbar.view_combo.count()))
        if view_modes != ("Engineering 2D", "ROSS Native"):
            raise RuntimeError(f"Frozen model-view selector mismatch: {view_modes}")

        executable_by_group: dict[BearingGroup, list[str]] = {}
        blocked_by_group: dict[BearingGroup, list[str]] = {}
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            rows = window.catalog.entries(group)
            executable_by_group[group] = sorted(str(row["class"]) for row in rows if bool(row["can_execute"]))
            blocked_by_group[group] = sorted(str(row["class"]) for row in rows if not bool(row["can_execute"]))

        if len(executable_by_group[BearingGroup.GENERAL]) != 4:
            raise RuntimeError(
                "Frozen General Bearing Studio did not expose 4 executable adapters: "
                f"{executable_by_group[BearingGroup.GENERAL]}"
            )
        if len(executable_by_group[BearingGroup.THD]) != 4:
            raise RuntimeError(
                "Frozen THD Bearing Studio did not expose 4 executable adapters: "
                f"{executable_by_group[BearingGroup.THD]}"
            )
        if blocked_by_group[BearingGroup.AMB] != ["MagneticBearingElement"]:
            raise RuntimeError(f"Frozen AMB gate mismatch: {blocked_by_group[BearingGroup.AMB]}")

        for route in ("shaft", "disks", "supports", "loads", "ump", "probes"):
            window._navigate(route)
            if window.stack.currentWidget() is not window.rotor_page:
                raise RuntimeError(f"Frozen route {route!r} did not open the Rotor engineering workspace.")

        window._navigate("bearings")
        bearing_direct_route = window.stack.currentWidget() is window.bearing_page
        if not bearing_direct_route:
            raise RuntimeError("Frozen Bearings route did not open Bearing Studio 2.0 directly.")
        stations = window.bearing_workspace.stations(project.engineering)
        expected_stations = len(stations)
        station_count = window.bearing_page.bearing_selector.count()
        if station_count != expected_stations:
            raise RuntimeError(
                f"Frozen Bearing Studio exposes {station_count} stations; expected {expected_stations}."
            )
        inventories = tuple(window.bearing_workspace.inventory(project.engineering, station.index) for station in stations)
        inventory_roles = tuple(tuple(element.role for element in inventory.elements) for inventory in inventories)
        if inventory_roles != tuple(("radial_anchor",) for _ in stations):
            raise RuntimeError(f"Frozen baseline bearing station inventory mismatch: {inventory_roles}")

        bearing_selection_synced = True
        if expected_stations > 1:
            last = stations[-1]
            row = window.bearing_page.bearing_selector.findData(last.index)
            window.bearing_page.bearing_selector.setCurrentIndex(row)
            app.processEvents()
            current = WORKSPACE_SELECTION.current
            if window.bearing_index != last.index:
                raise RuntimeError("Frozen bearing selector did not update the application station identity.")
            if current is None or current.kind != "bearings" or current.index != last.index:
                raise RuntimeError("Frozen bearing selector did not update the shared rotor bearing selection.")

            first = stations[0]
            WORKSPACE_SELECTION.select(RotorEntityRef("bearings", first.index, first.name, first.position_mm))
            app.processEvents()
            if window.bearing_index != first.index or window.bearing_page.bearing_selector.currentData() != first.index:
                raise RuntimeError("Frozen rotor bearing selection did not synchronize back to Bearing Studio.")

        page = window.bearing_page
        if not page.group_selector.isHidden():
            raise RuntimeError("Frozen Bearing Studio reintroduced the redundant visible family selector.")
        if len(page.type_buttons) != 9 or any(button.isHidden() for button in page.type_buttons.values()):
            raise RuntimeError("Frozen Bearing Studio must expose all nine bearing model icons directly.")
        if page.result_card.isVisible() or not page.result_card.isHidden():
            raise RuntimeError("Frozen Bearing Studio results must start collapsed below the engineering inputs.")

        expected_fields = {
            "ball": {"n_balls", "d_balls_mm", "static_load_n", "contact_angle_deg"},
            "sfd": {"speed_rpm", "journal_diameter_mm", "radial_clearance_um", "lubricant", "axial_length_mm", "eccentricity_ratio", "geometry", "cavitation"},
            "thrust": {"speed_rpm", "inner_radius_mm", "outer_radius_mm", "axial_load_n", "n_theta", "n_radial"},
        }
        for key, required in expected_fields.items():
            page._select_type(key, announce=False)
            actual = set(page.input_panel.fields)
            if not required.issubset(actual):
                raise RuntimeError(f"Frozen inline {key} editor missing fields: {sorted(required - actual)}")

        # A fast General model proves the production Calculate path consumes the
        # visible inline controls and does not require a modal input dialog.
        page._select_type("ball", announce=False)
        page.input_panel.fields["n_balls"].setValue(9)
        page.input_panel.fields["d_balls_mm"].setValue(28.0)
        window._calculate_bearing()
        if window.bearing_calculation is None or window.bearing_calculation.source_model != "BallBearingElement":
            raise RuntimeError("Frozen inline BallBearing calculation did not reach the qualified service.")
        if not page.results_button.isEnabled() or not page.result_card.isHidden():
            raise RuntimeError("Frozen result disclosure must be enabled after Calculate and remain collapsed initially.")
        page.set_results_visible(True)
        app.processEvents()
        if page.result_card.isHidden():
            raise RuntimeError("Frozen View Results did not reveal the result section below the input editor.")
        page.set_results_visible(False)
        if not page.result_card.isHidden():
            raise RuntimeError("Frozen Hide Results did not collapse the result section.")

        # Capability gating remains scientific: AMB is visible but not executable.
        page._select_type("amb", announce=False)
        if page.calculate_button.isEnabled():
            raise RuntimeError("Frozen AMB became executable without a qualified controller-domain contract.")

        app.processEvents()
        return FrozenGuiSmokeResult(
            status="PASS",
            window_title=window.windowTitle(),
            project=project.name,
            sidebar_routes=tuple(sorted(expected_routes)),
            view_modes=view_modes,
            rotor_editor_count=window.rotor_page.editor_stack.count(),
            bearing_station_count=station_count,
            bearing_direct_route=bearing_direct_route,
            bearing_selection_synced=bearing_selection_synced,
            bearing_station_inventory=inventory_roles,
            general_executable=tuple(executable_by_group[BearingGroup.GENERAL]),
            thd_executable=tuple(executable_by_group[BearingGroup.THD]),
            amb_blocked=tuple(blocked_by_group[BearingGroup.AMB]),
            bearing_model_icon_count=len(page.type_buttons),
            bearing_inline_input=True,
            bearing_results_below=True,
        )
    finally:
        WORKSPACE_SELECTION.clear()
        window.close()
        app.processEvents()


__all__ = ["FrozenGuiSmokeResult", "run_frozen_gui_smoke"]
