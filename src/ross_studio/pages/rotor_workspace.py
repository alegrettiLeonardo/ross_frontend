from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from ..bearing_node_inspector import BearingNodeInspector
from ..rotor_selection import RotorEntityRef
from ..shaft_geometry import display_shaft_geometry
from ..shaft_section_dialog import GuidedShaftSectionEditorDialog
from ..workspace_commands import WORKSPACE_COMMANDS
from . import rotor_model as _legacy_rotor_module
from .rotor_model import RotorModelPage as _LegacyRotorModelPage

# Keep the historical editor transaction owner and monkeypatch point intact. The
# legacy page resolves this module-global class when Edit is clicked, so existing
# tests/callers that monkeypatch ``pages.rotor_model.ShaftSectionEditorDialog`` keep
# working while production uses the guided ROSS tutorial editor.
_legacy_rotor_module.ShaftSectionEditorDialog = GuidedShaftSectionEditorDialog


class RotorModelPage(_LegacyRotorModelPage):
    """Unified Rotor/Shaft engineering workspace.

    The physical RotorDin-style sketch is the default model view. Strict ROSS
    construction and ``Rotor.plot_rotor`` live only behind Rotor Completo's explicit
    discretization toggle. Selecting a bearing keeps the engineer in this model flow
    and replaces the generic model summary with the applied node K/C context;
    Bearing Studio opens only through an explicit action.

    Shaft editing is additionally guided by the four explicit geometries documented
    in the ROSS Modeling tutorial: solid cylindrical, solid conical, hollow
    cylindrical and hollow conical. The existing strict preview/commit transaction
    remains the scientific gate; no shaft equation is duplicated in the GUI.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

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

        self.bearing_node_inspector = BearingNodeInspector(self.project, self)
        root = self.layout()
        right_panel = root.itemAt(1).widget() if root is not None and root.count() > 1 else None
        right_layout = right_panel.layout() if right_panel is not None else None
        self._model_summary_card = None
        if right_layout is not None:
            # Inherited order before insertion: ProjectInfo, ModelSummary, QuickActions.
            if right_layout.count() >= 2:
                self._model_summary_card = right_layout.itemAt(1).widget()
            insertion = max(0, right_layout.count() - 1)
            right_layout.insertWidget(insertion, self.bearing_node_inspector)
        self.bearing_node_inspector.hide()
        self.bearing_node_inspector.open_bearing_studio_requested.connect(self._open_bearing_studio)

        current = self.selection.current
        if current is not None and current.kind == "bearings":
            self._show_bearing_context(current)

    def _segments_page(self):
        """Decorate the qualified shaft table with the explicit ROSS geometry family.

        The legacy column order is intentionally preserved so existing FE-mesh
        automation and golden tests retain their column contracts. The geometry type
        is appended as a read-only engineering classification.
        """

        page = super()._segments_page()
        table = self.segment_table
        geometry_column = table.columnCount()
        table.insertColumn(geometry_column)
        table.setHorizontalHeaderItem(geometry_column, QTableWidgetItem("ROSS Shaft Type"))

        engineering = self.project.engineering
        if engineering is not None:
            for row, section in enumerate(engineering.shaft_sections):
                geometry_item = QTableWidgetItem(display_shaft_geometry(section))
                geometry_item.setFlags(geometry_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                geometry_item.setToolTip(
                    "Guided type follows the ROSS Modeling tutorial. Edit this section to choose "
                    "Solid cylindrical, Solid conical, Hollow cylindrical or Hollow conical."
                )
                table.setItem(row, geometry_column, geometry_item)
        table.resizeColumnsToContents()
        return page

    def set_view_mode(self, mode: str) -> None:
        # Compatibility shim for stale programmatic callers. There is no global
        # model-view state in 0.15; the editor is always the physical model.
        del mode
        self.view_stack.setCurrentWidget(self.sketch)

    def _sketch_entity_activated(self, kind: str, index: int) -> None:
        if kind == "bearings":
            # InteractiveRotorSketch writes the selection before emitting this
            # signal. Keep the Rotor Model page visible so the node K/C card is the
            # immediate consequence of clicking a bearing.
            return
        super()._sketch_entity_activated(kind, index)

    def _show_bearing_context(self, ref: RotorEntityRef) -> None:
        self.bearing_node_inspector.set_selection(ref)
        self.bearing_node_inspector.show()
        if self._model_summary_card is not None:
            self._model_summary_card.hide()

    def _hide_bearing_context(self) -> None:
        self.bearing_node_inspector.clear()
        self.bearing_node_inspector.hide()
        if self._model_summary_card is not None:
            self._model_summary_card.show()

    def _selection_changed(self, ref: RotorEntityRef | None) -> None:
        inspector = getattr(self, "bearing_node_inspector", None)
        if ref is not None and ref.kind == "bearings":
            if inspector is not None:
                self._show_bearing_context(ref)
            return
        if inspector is not None:
            self._hide_bearing_context()
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
        if hasattr(self, "bearing_node_inspector") and self.bearing_node_inspector.station_index is not None:
            self.bearing_node_inspector.refresh()


__all__ = ["RotorModelPage"]
