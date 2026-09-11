from __future__ import annotations

from ..bearing_node_inspector import BearingNodeInspector
from ..rotor_selection import RotorEntityRef
from ..workspace_commands import WORKSPACE_COMMANDS
from .rotor_model import RotorModelPage as _LegacyRotorModelPage


class RotorModelPage(_LegacyRotorModelPage):
    """Unified Rotor/Shaft engineering workspace.

    The physical RotorDin-style sketch is the default model view. Strict ROSS
    construction and ``Rotor.plot_rotor`` live only behind Rotor Completo's explicit
    discretization toggle. Selecting a bearing keeps the engineer in this model flow
    and exposes the applied K/C at the exact node; Bearing Studio is opened only by
    an explicit action in the bearing-node inspector.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # The inherited 0.14 page connected the obsolete global view selector.
        try:
            WORKSPACE_COMMANDS.view_mode_requested.disconnect(self.set_view_mode)
        except (RuntimeError, TypeError):
            pass

        native = getattr(self, "native_view", None)
        if native is not None:
            self.view_stack.removeWidget(native)
            native.close()
            native.deleteLater()
        self.native_view = None
        self.view_stack.setCurrentWidget(self.sketch)
        self.sketch.set_mesh_visible(False)

        # Right-side contextual node information. The inherited layout is
        # [engineering center, right panel]; the right panel itself owns
        # ProjectInfo, ModelSummary and QuickActions. Insert the inspector before
        # QuickActions without duplicating primary model navigation.
        self.bearing_node_inspector = BearingNodeInspector(self.project, self)
        root = self.layout()
        right_panel = root.itemAt(1).widget() if root is not None and root.count() > 1 else None
        right_layout = right_panel.layout() if right_panel is not None else None
        if right_layout is not None:
            insertion = max(0, right_layout.count() - 1)
            right_layout.insertWidget(insertion, self.bearing_node_inspector)
        self.bearing_node_inspector.open_bearing_studio_requested.connect(self._open_bearing_studio)

        current = self.selection.current
        if current is not None and current.kind == "bearings":
            self.bearing_node_inspector.set_selection(current)

    def set_view_mode(self, mode: str) -> None:
        # Compatibility shim for stale programmatic callers. There is no longer a
        # model-view state: normal editing is always the physical model.
        del mode
        self.view_stack.setCurrentWidget(self.sketch)

    def _sketch_entity_activated(self, kind: str, index: int) -> None:
        if kind == "bearings":
            # The base sketch has already written this bearing into the shared
            # selection model. Keep the Rotor workspace visible so its node card can
            # show K/C; navigation becomes an explicit user choice.
            return
        super()._sketch_entity_activated(kind, index)

    def _selection_changed(self, ref: RotorEntityRef | None) -> None:
        inspector = getattr(self, "bearing_node_inspector", None)
        if ref is not None and ref.kind == "bearings":
            if inspector is not None:
                inspector.set_selection(ref)
            return
        if inspector is not None:
            inspector.clear()
        super()._selection_changed(ref)

    def _open_bearing_studio(self, station_index: int) -> None:
        engineering = self.project.engineering
        if engineering is None or not (0 <= station_index < len(engineering.bearings)):
            return
        bearing = engineering.bearings[station_index]
        self.selection.select(RotorEntityRef("bearings", station_index, bearing.name, bearing.position_mm))
        WORKSPACE_COMMANDS.navigate_requested.emit("bearings")

    def _after_model_commit(self, key, audit, *, selected_row: int = -1) -> None:
        super()._after_model_commit(key, audit, selected_row=selected_row)
        if hasattr(self, "bearing_node_inspector"):
            self.bearing_node_inspector.refresh()


__all__ = ["RotorModelPage"]
