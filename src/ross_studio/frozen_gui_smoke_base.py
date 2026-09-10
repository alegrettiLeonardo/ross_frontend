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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_frozen_gui_smoke() -> FrozenGuiSmokeResult:
    """Construct the production Qt window and exercise non-modal navigation.

    The scientific self-test validates the backend. This companion gate proves the
    packaged desktop shell imports, constructs and exposes Bearing Studio 2.0 with
    explicit bearing-station selection instead of silently degrading to a fixed
    ``bearing_index=0`` path. No solver dialog or expensive THD calculation is run.
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
            "rotor",
            "shaft",
            "disks",
            "bearings",
            "seals",
            "supports",
            "couplings",
            "loads",
            "ump",
            "probes",
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

        # Bearing Studio 2.0 is the direct target of the sidebar. There is no
        # intermediate family landing page and every physical radial station is
        # selectable independently from its calculation model.
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

        # Bearing Studio selector -> shared rotor selection.
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

            # Shared rotor/sketch selection -> Bearing Studio selector/application.
            first = stations[0]
            WORKSPACE_SELECTION.select(RotorEntityRef("bearings", first.index, first.name, first.position_mm))
            app.processEvents()
            if window.bearing_index != first.index or window.bearing_page.bearing_selector.currentData() != first.index:
                raise RuntimeError("Frozen rotor bearing selection did not synchronize back to Bearing Studio.")

        # Exercise family visibility and capability gating inside the single workspace.
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            window._open_bearing_group(group.value)
            visible = [
                (key, window.bearing_page.type_metadata[key][1], button)
                for key, button in window.bearing_page.type_buttons.items()
                if not button.isHidden()
            ]
            expected_count = len(window.catalog.entries(group))
            if len(visible) != expected_count:
                raise RuntimeError(
                    f"Frozen {group.value} page shows {len(visible)} model buttons; expected {expected_count}."
                )
            for key, ross_class, _button in visible:
                window.bearing_page._select_type(key, announce=False)
                can_execute = next(
                    bool(row["can_execute"])
                    for row in window.catalog.entries(group)
                    if row["class"] == ross_class
                )
                if window.bearing_page.calculate_button.isEnabled() != can_execute:
                    raise RuntimeError(
                        f"Frozen Calculate button gating mismatch for {ross_class}: expected {can_execute}."
                    )

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
        )
    finally:
        WORKSPACE_SELECTION.clear()
        window.close()
        app.processEvents()


__all__ = ["FrozenGuiSmokeResult", "run_frozen_gui_smoke"]
