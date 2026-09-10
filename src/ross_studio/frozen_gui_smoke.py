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
    general_executable: tuple[str, ...]
    thd_executable: tuple[str, ...]
    amb_blocked: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_frozen_gui_smoke() -> FrozenGuiSmokeResult:
    """Construct the production Qt window and exercise non-modal navigation.

    The frozen scientific self-test validates the backend. This companion gate proves
    that the packaged desktop shell imports, constructs and exposes the same Bearing
    Studio capabilities instead of silently degrading to ``0 executable adapters``.
    No solver dialog or expensive THD calculation is started here.
    """

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication, QTabWidget

    from .app import RossStudioWindow

    app = QApplication.instance() or QApplication([])
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

        # 0.12 intentionally removed the second horizontal model navigation bar.
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
            raise RuntimeError(
                "Frozen AMB gate mismatch: "
                f"{blocked_by_group[BearingGroup.AMB]}"
            )

        # Exercise actual application routing and button gating for every family.
        for route in ("shaft", "disks", "supports", "loads", "ump", "probes"):
            window._navigate(route)
            if window.stack.currentWidget() is not window.rotor_page:
                raise RuntimeError(f"Frozen route {route!r} did not open the Rotor engineering workspace.")

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
            general_executable=tuple(executable_by_group[BearingGroup.GENERAL]),
            thd_executable=tuple(executable_by_group[BearingGroup.THD]),
            amb_blocked=tuple(blocked_by_group[BearingGroup.AMB]),
        )
    finally:
        window.close()
        app.processEvents()


__all__ = ["FrozenGuiSmokeResult", "run_frozen_gui_smoke"]
