from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__ as studio_version
from ..models import ProjectModel
from ..services import EngineeringValidationService
from ..widgets import Card, SectionCard


def _package_version(distribution: str, fallback: str = "Unavailable") -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return fallback


class _ValueGrid(QWidget):
    def __init__(self, rows: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(9)
        for row, (label, value) in enumerate(rows):
            key = QLabel(label)
            key.setObjectName("muted")
            val = QLabel(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(key, row, 0)
            grid.addWidget(val, row, 1)
        grid.setColumnStretch(1, 1)


class ProjectHomePage(QWidget):
    """Project-data dashboard.

    Home is deliberately not another alias for the rotor editor. It summarizes the
    project and the current engineering-domain state without mutating scientific data.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = Card()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel("Project Data")
        title.setObjectName("cardHeader")
        subtitle = QLabel(
            "Project identity, operating case, model inventory and validation. "
            "Scientific editing remains under ROTOR MODEL."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        project_card = SectionCard("Project")
        project_card.root.addWidget(_ValueGrid([
            ("Name", project.name),
            ("Description", project.description or "—"),
            ("Created", project.created or "—"),
            ("Last Modified", project.modified or "—"),
            ("ROSS Studio", studio_version),
            ("ROSS Rotordynamics", _package_version("ross-rotordynamics")),
            ("Units", "SI at ROSS boundary · desktop display uses mm / rpm / N"),
        ]))
        grid.addWidget(project_card, 0, 0)

        operation_card = SectionCard("Operating Case")
        operation_card.root.addWidget(_ValueGrid([
            ("Rated speed", f"{project.speed_rpm:,} rpm"),
            ("Minimum speed", f"{project.speed_min_rpm:,} rpm"),
            ("Maximum speed", f"{project.speed_max_rpm:,} rpm"),
            ("Electrical frequency", f"{project.frequency_hz:g} Hz"),
            ("Poles", str(project.poles)),
            ("Rotation direction", "Not specified in current project schema"),
        ]))
        grid.addWidget(operation_card, 0, 1)

        engineering = project.engineering
        if engineering is None:
            counts = {
                "Shaft sections": project.physical_sections,
                "ROSS ShaftElements": project.ross_shaft_elements,
                "Disks / masses": project.disks,
                "Bearings": project.bearings,
                "Supports": project.supports,
                "Foundations": 0,
                "Seals": 0,
                "Couplings": 0,
                "Loads": 0,
                "Probes": 0,
            }
        else:
            counts = {
                "Shaft sections": len(engineering.shaft_sections),
                "ROSS ShaftElements": engineering.ross_shaft_element_count,
                "Disks / masses": len(engineering.distributed_masses) + len(engineering.disks) + len(engineering.point_masses),
                "Bearings": len(engineering.bearings),
                "Supports": len(engineering.supports),
                # FoundationSpec intentionally arrives in its own scientific tranche.
                "Foundations": len(getattr(engineering, "foundations", ())),
                "Seals": len(engineering.seals),
                "Couplings": len(engineering.couplings),
                "Loads": len(engineering.loads),
                "Probes": len(engineering.probes),
            }

        summary_card = SectionCard("Model Summary")
        summary_card.root.addWidget(_ValueGrid([(key, str(value)) for key, value in counts.items()]))
        grid.addWidget(summary_card, 1, 0)

        validation_card = SectionCard("Validation")
        if engineering is None:
            validation_rows = [("Engineering domain", "Not loaded")]
        else:
            issues = EngineeringValidationService().validate(engineering)
            errors = [issue for issue in issues if issue.severity == "error"]
            warnings = [issue for issue in issues if issue.severity == "warning"]
            validation_rows = [
                ("Topology / domain", "PASS" if not errors else f"FAIL · {len(errors)} error(s)"),
                ("Readiness warnings", str(len(warnings))),
                ("Exact-node policy", "Mandatory; no silent nearest-node snapping"),
                ("ROSS assembly", "Qualified through strict builder transactions"),
            ]
        validation_card.root.addWidget(_ValueGrid(validation_rows))
        grid.addWidget(validation_card, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)


__all__ = ["ProjectHomePage"]
