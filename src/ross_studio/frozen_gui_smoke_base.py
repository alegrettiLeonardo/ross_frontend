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
    """Construct the frozen desktop and qualify the 0.15 model/Bearing Studio UX.

    Scientific solver qualification remains in the frozen self-test. This companion
    gate verifies that packaging preserves one Rotor Model navigation state, removes
    the obsolete Engineering-2D/ROSS selector, exposes Rotor Completo explicitly and
    ships the requested Bearing Studio model/output contract.
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
            "rotor", "disks", "bearings", "seals", "supports",
            "couplings", "loads", "ump", "probes",
        }
        available_routes = set(window.sidebar.buttons)
        missing_routes = expected_routes - available_routes
        if missing_routes:
            raise RuntimeError(f"Frozen sidebar is missing model routes: {sorted(missing_routes)}")
        if "shaft" in available_routes:
            raise RuntimeError("Frozen sidebar reintroduced the duplicate Shaft navigation state.")

        if window.rotor_page.findChildren(QTabWidget):
            raise RuntimeError("Frozen Rotor workspace unexpectedly contains a duplicate QTabWidget model navigator.")
        if window.rotor_page.editor_stack.count() != 8:
            raise RuntimeError(
                f"Frozen Rotor workspace expected 8 engineering editor pages, received {window.rotor_page.editor_stack.count()}."
            )

        if hasattr(window.toolbar, "view_combo"):
            raise RuntimeError("Frozen toolbar reintroduced the obsolete Engineering 2D / ROSS Native selector.")
        if not hasattr(window.toolbar, "full_rotor_button"):
            raise RuntimeError("Frozen toolbar is missing the explicit Rotor Completo action.")
        view_modes: tuple[str, ...] = ()

        executable_by_group: dict[BearingGroup, list[str]] = {}
        blocked_by_group: dict[BearingGroup, list[str]] = {}
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            rows = window.catalog.entries(group)
            executable_by_group[group] = sorted(str(row["class"]) for row in rows if bool(row["can_execute"]))
            blocked_by_group[group] = sorted(str(row["class"]) for row in rows if not bool(row["can_execute"]))

        if len(executable_by_group[BearingGroup.GENERAL]) != 4:
            raise RuntimeError(
                "Frozen General registry did not retain 4 qualified adapters: "
                f"{executable_by_group[BearingGroup.GENERAL]}"
            )
        if len(executable_by_group[BearingGroup.THD]) != 4:
            raise RuntimeError(
                "Frozen THD registry did not retain 4 qualified adapters: "
                f"{executable_by_group[BearingGroup.THD]}"
            )
        if blocked_by_group[BearingGroup.AMB] or executable_by_group[BearingGroup.AMB] != ["MagneticBearingElement"]:
            raise RuntimeError(f"Frozen AMB gate mismatch: {blocked_by_group[BearingGroup.AMB]}")

        for route in ("shaft", "disks", "supports", "loads", "ump", "probes"):
            # shaft remains a programmatic alias to the single Rotor Model page.
            window._navigate(route)
            if window.stack.currentWidget() is not window.rotor_page:
                raise RuntimeError(f"Frozen route {route!r} did not open the unified Rotor workspace.")

        window._navigate("bearings")
        bearing_direct_route = window.stack.currentWidget() is window.bearing_page
        if not bearing_direct_route:
            raise RuntimeError("Frozen Bearings route did not open Bearing Studio directly.")
        if not window.bearing_page.__class__.__module__.endswith("bearing_workspace_page"):
            raise RuntimeError("Frozen application is not composed with the 0.15 Bearing Studio workspace.")
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
        expected_models = {"ball", "roller", "cyl", "plain", "tilting", "thrust", "sfd", "amb"}
        if set(page.type_buttons) != expected_models or any(button.isHidden() for button in page.type_buttons.values()):
            raise RuntimeError(
                f"Frozen Bearing Studio model surface mismatch: {sorted(page.type_buttons)}"
            )
        if "kc" in page.type_buttons:
            raise RuntimeError("Direct BearingElement K/C must not appear as a Bearing Studio calculation-model tile.")
        if page.result_card.isVisible() or not page.result_card.isHidden():
            raise RuntimeError("Frozen Bearing Studio output must start collapsed below the engineering inputs.")
        if "exact ROSS node" not in page.target_node_label.text():
            raise RuntimeError("Frozen Bearing Studio does not expose the exact target node.")

        expected_fields = {
            "ball": {"n_balls", "d_balls_mm", "static_load_n", "contact_angle_deg"},
            "sfd": {"speed_rpm", "journal_diameter_mm", "radial_clearance_um", "lubricant", "axial_length_mm", "eccentricity_ratio", "geometry", "cavitation"},
            "thrust": {"speed_rpm", "pad_inner_radius_mm", "pad_outer_radius_mm", "axial_load_n", "n_theta", "n_radial"},
        }
        for key, required in expected_fields.items():
            page._select_type(key, announce=False)
            actual = set(page.input_panel.fields)
            if not required.issubset(actual):
                raise RuntimeError(f"Frozen inline {key} editor missing fields: {sorted(required - actual)}")

        # Fast General calculation: K/C values are available; THD-only dimensional
        # output and K/C curves stay unavailable.
        page._select_type("ball", announce=False)
        page.input_panel.fields["n_balls"].setValue(9)
        page.input_panel.fields["d_balls_mm"].setValue(28.0)
        window._calculate_bearing()
        if window.bearing_calculation is None or window.bearing_calculation.source_model != "BallBearingElement":
            raise RuntimeError("Frozen inline BallBearing calculation did not reach the qualified service.")
        if not page.output_kc_button.isEnabled() or page.output_dimensional_button.isEnabled():
            raise RuntimeError("Frozen General bearing output contract is not K/C-only.")
        if page.kc_native_view.figure is not None:
            raise RuntimeError("Frozen General bearing unexpectedly exposes a THD K/C curve.")

        # Model-flow bearing node must remain inspectable without navigating away.
        window._navigate("rotor")
        first = stations[0]
        WORKSPACE_SELECTION.select(RotorEntityRef("bearings", first.index, first.name, first.position_mm))
        app.processEvents()
        inspector = window.rotor_page.bearing_node_inspector
        if inspector.station_index != first.index:
            raise RuntimeError("Frozen Rotor workspace did not expose the selected bearing-node inspector.")
        if inspector.curves_button.isVisible():
            raise RuntimeError("Imported/General K/C bearing node must not expose THD K/C curves.")

        page._select_type("amb", announce=False)
        if not page.calculate_button.isEnabled():
            raise RuntimeError("Frozen AMB calculation is unexpectedly disabled.")
        page.input_panel.fields["g0_mm"].setValue(1.234)
        window._calculate_bearing()
        if window.bearing_calculation is None or window.bearing_calculation.source_model != "MagneticBearingElement":
            raise RuntimeError("Frozen AMB GUI did not execute the native magnetic bearing calculation.")
        received = window.bearing_calculation.metadata["engineering_input"]["g0_m"]
        if abs(received - 0.001234) > 1e-15:
            raise RuntimeError(f"AMB GUI gap conversion failed: received {received!r} m.")

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
