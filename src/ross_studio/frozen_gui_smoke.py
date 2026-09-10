from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from .frozen_gui_smoke_base import run_frozen_gui_smoke as _run_base_gui_smoke


@dataclass(slots=True, frozen=True)
class FrozenGuiSmokeResult:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def run_frozen_gui_smoke() -> FrozenGuiSmokeResult:
    """Qualify the production GUI plus 0.14 model-builder transactions in-place.

    The inherited 0.13 gate first checks navigation and Bearing Studio. A second
    production window then exercises the same transaction service used by the editor,
    proving PyInstaller includes every newly enabled entity path on both Linux and
    Windows. Coupling and Load are intentionally qualified as engineering/analysis
    inputs at exact stations, not falsely reported as structural ROSS elements.
    """

    base = _run_base_gui_smoke().to_dict()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from .app import RossStudioWindow
    from .domain import (
        CouplingSpec,
        DiskSpec,
        DistributedMassSpec,
        LoadSpec,
        PointMassSpec,
        ProbeSpec,
        SealSpec,
    )
    from .ross_backend import RossModelBuilder
    from .rotor_selection import WORKSPACE_SELECTION
    from .topology import NodeInsertionService

    app = QApplication.instance() or QApplication([])
    WORKSPACE_SELECTION.clear()
    window = RossStudioWindow()
    try:
        project = window.project.engineering
        if project is None:
            raise RuntimeError("Frozen Model Builder smoke did not load OP-W60 engineering domain.")
        service = window.rotor_page.model_builder

        records = (
            ("distributed_mass", DistributedMassSpec("FROZEN-MASSAS", 1000.125, 30.0, 9.0, 160.0, 20.0)),
            ("disk", DiskSpec("FROZEN-DISK", 1100.250, 8.0, 0.03, 0.06)),
            ("point_mass", PointMassSpec("FROZEN-CONCENT", 1200.375, 7.0, 0.011, 0.022, 0.033)),
            (
                "seal",
                SealSpec(
                    "FROZEN-SEAL", 1300.500,
                    kxx=1.0e6, kyy=1.1e6, cxx=100.0, cyy=110.0,
                    kxy=-2.0e5, kyx=2.1e5, cxy=-20.0, cyx=21.0,
                ),
            ),
            (
                "coupling",
                CouplingSpec(
                    "FROZEN-COUPLING", 1400.625,
                    left_mass_kg=2.0, right_mass_kg=3.0,
                    left_ip_kg_m2=0.04, right_ip_kg_m2=0.05,
                    kr_z_n_m_rad=2.0e6,
                ),
            ),
            ("load", LoadSpec("FROZEN-LOAD", "harmonic", 1500.750, 100.0, 15.0, {"order": 1})),
            ("probe", ProbeSpec("FROZEN-PROBE", 1600.875, 1, 45.0)),
        )

        transaction_nodes: dict[str, int] = {}
        for kind, record in records:
            preview = service.preview_add(project, kind, record)
            service.commit(project, preview)
            if kind == "distributed_mass":
                position = record.center_mm
            else:
                position = record.position_mm
            node = NodeInsertionService.plan(project).node_for(position)
            if node is None:
                raise RuntimeError(f"Frozen {kind} transaction did not retain exact node at {position:g} mm.")
            transaction_nodes[kind] = node

        final = RossModelBuilder().build(project, strict=True)
        if final.unresolved_positions_mm:
            raise RuntimeError(f"Frozen strict Rotor contains unresolved stations: {final.unresolved_positions_mm}")
        if not any(item.name == "FROZEN-MASSAS" for item in final.equivalent_disks):
            raise RuntimeError("Frozen strict Rotor lost the [Massas] equivalent DiskElement.")
        point = next((item for item in final.equivalent_point_masses if item.name == "FROZEN-CONCENT"), None)
        if point is None or (point.ix_kg_m2, point.iy_kg_m2, point.iz_kg_m2) != (0.011, 0.022, 0.033):
            raise RuntimeError("Frozen strict Rotor did not preserve [Concent] principal inertias.")
        seal_candidates = [*getattr(final.rotor, "seal_elements", []), *getattr(final.rotor, "bearing_elements", [])]
        if not any(type(element).__name__ == "SealElement" and getattr(element, "tag", None) == "FROZEN-SEAL" for element in seal_candidates):
            raise RuntimeError("Frozen strict Rotor did not realize the new seal as ROSS SealElement.")
        if any(type(element).__name__ == "CouplingElement" for element in final.rotor.shaft_elements):
            raise RuntimeError("Frozen single-station coupling was silently mapped to a two-node CouplingElement.")

        # Rebuild the visible tables from the committed domain and exercise the actual
        # offscreen sketch paint pass so [Concent] cannot disappear only in packaging.
        window.rotor_page._rebuild_editors("disks")
        table = window.rotor_page.editor_tables["disks"]
        concent_table_visible = any(
            table.item(row, 1) is not None and "[Concent]" in table.item(row, 1).text()
            for row in range(table.rowCount())
        )
        if not concent_table_visible:
            raise RuntimeError("Frozen mass editor does not expose [Concent] as a first-class body.")

        window.resize(1400, 850)
        window.show()
        app.processEvents()
        window.rotor_page.sketch.repaint()
        app.processEvents()
        concent_sketch_visible = any("[Concent]" in hit.tooltip for hit in window.rotor_page.sketch._hits)
        if not concent_sketch_visible:
            raise RuntimeError("Frozen Engineering 2D sketch did not render an interactive [Concent] body.")

        buttons = window.rotor_page.editor_action_buttons
        enabled_editor_groups = tuple(
            key
            for key in ("disks", "seals", "couplings", "loads", "probes")
            if all(buttons[key][action].isEnabled() for action in ("add", "edit", "delete"))
        )
        if enabled_editor_groups != ("disks", "seals", "couplings", "loads", "probes"):
            raise RuntimeError(f"Frozen 0.14 editor action gating mismatch: {enabled_editor_groups}")
        if buttons["shaft"]["add"].isEnabled() or buttons["shaft"]["delete"].isEnabled():
            raise RuntimeError("Frozen shaft add/delete bypassed the absolute-coordinate remapping gate.")
        if any(button.isEnabled() for button in buttons["ump"].values()):
            raise RuntimeError("Frozen UMP page exposed a detached duplicate editor.")

        base["model_builder_014"] = {
            "status": "PASS",
            "transaction_contract": "preview -> domain validation -> engineering validation -> strict ROSS -> stale-check -> commit",
            "transaction_nodes": transaction_nodes,
            "enabled_editor_groups": list(enabled_editor_groups),
            "concent_table_visible": concent_table_visible,
            "concent_sketch_visible": concent_sketch_visible,
            "concent_inertias_preserved": True,
            "seal_native_class": "SealElement",
            "coupling_native_mapping": "BLOCKED_PENDING_TWO_NODE_CONTRACT",
            "load_realization": "ANALYSIS_INPUT_EXACT_NODE",
            "unresolved_positions_mm": final.unresolved_positions_mm,
        }
        return FrozenGuiSmokeResult(base)
    finally:
        WORKSPACE_SELECTION.clear()
        window.close()
        app.processEvents()


__all__ = ["FrozenGuiSmokeResult", "run_frozen_gui_smoke"]
