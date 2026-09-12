from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ..domain import FoundationModel
from ..models import ProjectModel
from ..page_registry import PageRouteSpec
from ..widgets import Card, SectionCard


class _ArchitectureHeader(Card):
    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        status: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("cardHeader")
        layout.addWidget(heading)
        description = QLabel(subtitle)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        state = QLabel(status)
        state.setObjectName("architectureStatus")
        state.setWordWrap(True)
        layout.addWidget(state)


class FoundationWorkspacePage(QWidget):
    """Foundation Studio 0.24 tranche-B audit page.

    Foundation is now a first-class engineering entity and the strict ROSS builder
    can assemble qualified 2-DOF K/C/M contracts. The editor remains intentionally
    disabled until the full numerical and frozen gates are closed; this page reports
    the actual project state instead of pretending the earlier architecture placeholder
    is still current.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(_ArchitectureHeader(
            "Foundation Studio · tranche B",
            "Foundation is a structural subsystem below the local bearing/support connection. "
            "SupportSpec and FoundationSpec remain separate physical owners.",
            status=(
                "0.24 implementation active · first-class domain, schema-2 persistence and strict "
                "bearing→support→foundation→ground assembly are present; editing stays locked until qualification closes."
            ),
        ))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        topology = SectionCard("Physical Ownership")
        text = QLabel(
            "Shaft node\n"
            "   │\n"
            "BearingElement / n_link\n"
            "   ▼\n"
            "Support node ─ PointMass(Msupport)\n"
            "   │\n"
            "Support K/C\n"
            "   ▼\n"
            "Foundation node ─ PointMass(Mfoundation)\n"
            "   │\n"
            "Foundation K/C\n"
            "   ▼\n"
            "Ground"
        )
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        topology.root.addWidget(text)
        grid.addWidget(topology, 0, 0)

        contract = SectionCard("0.24 Scientific Contract")
        message = QLabel(
            "Implemented domain models: RIGID, LUMPED_KC, LUMPED_KCM and FREQUENCY_DEPENDENT_KC. "
            "Full 2×2 K/C cross-coupling is retained. Frequency rows are engineering Hz at the project boundary "
            "and are converted to ROSS rad/s during assembly. REDUCED_MATRIX and any 6-DOF foundation request "
            "remain BLOCKED rather than truncated."
        )
        message.setWordWrap(True)
        contract.root.addWidget(message)
        grid.addWidget(contract, 0, 1)

        existing = SectionCard("Current Project")
        engineering = project.engineering
        support_count = len(engineering.supports) if engineering is not None else project.supports
        foundations = list(engineering.foundations) if engineering is not None else []
        dynamic_count = sum(f.model_type != FoundationModel.RIGID for f in foundations)
        frequency_count = sum(f.model_type == FoundationModel.FREQUENCY_DEPENDENT_KC for f in foundations)
        summary = QLabel(
            f"Flexible supports: {support_count}\n"
            f"Foundation definitions: {len(foundations)}\n"
            f"Dynamic foundations: {dynamic_count}\n"
            f"Frequency-dependent foundations: {frequency_count}\n"
            "Attachment: explicit support_index only\n"
            "Nearest-node mapping: prohibited"
        )
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        existing.root.addWidget(summary)
        grid.addWidget(existing, 1, 0)

        gate = SectionCard("Qualification Gate")
        gate_label = QLabel(
            "Pending before this route becomes operational: rigid/high-stiffness limit, diagonal and cross-coupled K/C, "
            "foundation-mass M audit, frequency interpolation, modal sensitivity, schema-1→2 migration, project round-trip, "
            "full pytest/OP-W60 regression, and Linux/Windows frozen execution."
        )
        gate_label.setWordWrap(True)
        gate.root.addWidget(gate_label)
        grid.addWidget(gate, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        root.addStretch(1)


class AnalysisRoutePage(QWidget):
    """Dedicated owner page for one analysis route.

    The page is deliberately non-executable until its ROSS run_* service is split
    from the legacy all-in-one qualification pipeline. A visible route must never
    pretend to be scientifically implemented merely because navigation exists.
    """

    def __init__(
        self,
        project: ProjectModel,
        spec: PageRouteSpec,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.spec = spec
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(_ArchitectureHeader(
            spec.title,
            "Dedicated analysis workspace owner. ROTOR MODEL supplies the physical model; "
            "this page will only consume a strict ROSS Rotor and its native analysis result.",
            status=f"Scientific execution gate: {spec.implementation_phase} · {spec.note}",
        ))

        ownership = SectionCard("Analysis Contract")
        details = {
            "analysis.static_modal.lateral": (
                "Planned native calls: Rotor.run_static(), Rotor.run_modal(), Rotor.run_campbell().\n"
                "Static and modal must run independently of unbalance inputs."
            ),
            "analysis.static_modal.torsional": (
                "Planned source: Rotor.run_modal(); torsional modes are selected by the ROSS mode classification.\n"
                "No parallel synthetic torsional solver will be introduced."
            ),
            "analysis.time_frequency": (
                "Planned native capabilities: frequency response, unbalance response, time response, "
                "harmonic balance, critical-speed map and fault workflows."
            ),
            "analysis.stochastic": (
                "Planned native ROSS stochastic ST_* model adapters and stochastic analysis results."
            ),
            "analysis.multirotor": (
                "Planned GearElement + MultiRotor project assembly using two independently qualified Rotor models."
            ),
        }[spec.route_id]
        label = QLabel(details)
        label.setWordWrap(True)
        ownership.root.addWidget(label)
        root.addWidget(ownership)

        state = SectionCard("Current State")
        state_label = QLabel(
            "This route has a unique page owner and no longer aliases the global Results page. "
            "Execution stays disabled until its scientific service is qualified, so no fake plot or "
            "fabricated result can be shown."
        )
        state_label.setWordWrap(True)
        state.root.addWidget(state_label)
        root.addWidget(state)
        root.addStretch(1)


__all__ = ["AnalysisRoutePage", "FoundationWorkspacePage"]
