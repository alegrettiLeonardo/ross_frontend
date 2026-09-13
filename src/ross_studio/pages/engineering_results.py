from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engineering_figures import EngineeringFigureCatalog
from ..engineering_outputs import EngineeringOutputsService, EngineeringOutputsSnapshot
from ..models import ProjectModel
from ..result_validity import ResultValidityGuard
from ..plotly_native_view import NativeRossFigureView
from .results import AnalysisResultsPage


class EngineeringOutputsDialog(QDialog):
    """Engineering deliverables browser embedded in the analysis workflow.

    There is intentionally no global Results/Outputs navigation route. The dialog is
    opened from the qualified analysis result page and only becomes available after a
    real ``AnalysisPipelineResult`` exists.
    """

    def __init__(
        self,
        project: ProjectModel,
        snapshot: EngineeringOutputsSnapshot,
        figure_catalog: EngineeringFigureCatalog,
        service: EngineeringOutputsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.snapshot = snapshot
        self.figure_catalog = figure_catalog
        self.service = service
        self.setWindowTitle(f"Engineering Outputs | {project.name}")
        self.resize(1450, 860)
        self.setMinimumSize(1100, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Engineering Outputs")
        title.setObjectName("cardHeader")
        title_row.addWidget(title)
        title_row.addWidget(QLabel(project.name))
        title_row.addStretch(1)
        provenance = QLabel(
            f"ROSS {snapshot.provenance['ross_version']} · Studio {snapshot.provenance['ross_studio_version']} · "
            f"strict model · fingerprint {str(snapshot.provenance['project_fingerprint_sha256'])[:12]}…"
        )
        provenance.setObjectName("muted")
        title_row.addWidget(provenance)
        root.addLayout(title_row)

        policy = QLabel(
            "Native-figure policy: graphs are returned by retained ROSS result plot methods; "
            "Engineering Outputs does not call run_* again."
        )
        policy.setObjectName("muted")
        policy.setWordWrap(True)
        root.addWidget(policy)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tables_tab(), "Tables")
        self.tabs.addTab(self._figures_tab(), "Native ROSS Figures")
        self.tabs.addTab(self._qualification_tab(), "Qualification Manifest")
        root.addWidget(self.tabs, 1)

        export_row = QHBoxLayout()
        self.export_status = QLabel("Ready")
        self.export_status.setObjectName("muted")
        export_row.addWidget(self.export_status, 1)

        self.export_xlsx_button = QPushButton("Export XLSX")
        self.export_xlsx_button.setObjectName("softButton")
        self.export_xlsx_button.clicked.connect(self._export_xlsx)
        export_row.addWidget(self.export_xlsx_button)

        self.export_pdf_button = QPushButton("Export PDF")
        self.export_pdf_button.setObjectName("softButton")
        self.export_pdf_button.clicked.connect(self._export_pdf)
        export_row.addWidget(self.export_pdf_button)

        self.export_images_button = QPushButton("Export Images")
        self.export_images_button.setObjectName("softButton")
        self.export_images_button.clicked.connect(self._export_images)
        export_row.addWidget(self.export_images_button)

        self.export_manifest_button = QPushButton("Qualification Manifest")
        self.export_manifest_button.setObjectName("softButton")
        self.export_manifest_button.clicked.connect(self._export_manifest)
        export_row.addWidget(self.export_manifest_button)

        self.export_package_button = QPushButton("Export Full Package")
        self.export_package_button.setObjectName("primaryButton")
        self.export_package_button.clicked.connect(self._export_package)
        export_row.addWidget(self.export_package_button)
        root.addLayout(export_row)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        close.setMaximumWidth(110)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

        self._populate_table(self.table_selector.currentData())
        default_key = "campbell" if "campbell" in self.figure_catalog.keys else self.figure_catalog.keys[0]
        index = self.figure_selector.findData(default_key)
        if index >= 0:
            self.figure_selector.setCurrentIndex(index)
        self._show_figure(default_key)

    def _tables_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Engineering table"))
        self.table_selector = QComboBox()
        for table in self.snapshot.tables:
            self.table_selector.addItem(table.title, table.key)
        self.table_selector.currentIndexChanged.connect(
            lambda _index: self._populate_table(self.table_selector.currentData())
        )
        selector_row.addWidget(self.table_selector, 1)
        layout.addLayout(selector_row)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        return page

    def _figures_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("ROSS output"))
        self.figure_selector = QComboBox()
        for spec in self.figure_catalog.specs:
            self.figure_selector.addItem(f"{spec.category} · {spec.title}", spec.key)
        self.figure_selector.currentIndexChanged.connect(
            lambda _index: self._show_figure(self.figure_selector.currentData())
        )
        selector_row.addWidget(self.figure_selector, 1)
        layout.addLayout(selector_row)

        self.figure_source = QLabel()
        self.figure_source.setObjectName("muted")
        self.figure_source.setWordWrap(True)
        layout.addWidget(self.figure_source)

        self.figure_view = NativeRossFigureView()
        layout.addWidget(self.figure_view, 1)
        return page

    def _qualification_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        explanation = QLabel(
            "The manifest records provenance, qualified/not-qualified capabilities, native ROSS plot ownership, "
            "asset hashes and the no-recompute policy."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)
        self.manifest_preview = QPlainTextEdit()
        self.manifest_preview.setReadOnly(True)
        payload = self.service.build_qualification_manifest(
            self.snapshot,
            figure_catalog=self.figure_catalog,
        )
        self.manifest_preview.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
        layout.addWidget(self.manifest_preview, 1)
        return page

    def _populate_table(self, key: str | None) -> None:
        if not key:
            return
        table = self.snapshot.table(str(key))
        self.table.clear()
        self.table.setColumnCount(len(table.columns))
        self.table.setHorizontalHeaderLabels(list(table.columns))
        self.table.setRowCount(len(table.rows))
        for row_index, row in enumerate(table.rows):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)

    def _show_figure(self, key: str | None) -> None:
        if not key:
            return
        try:
            spec = self.figure_catalog.spec(str(key))
            figure = self.figure_catalog.figure(str(key))
            self.figure_source.setText(
                f"Native source: {spec.source_method} · {spec.tutorial_basis} · {spec.description}"
            )
            self.figure_view.set_figure(figure, tooltip=f"{spec.source_method} · native ROSS Plotly output")
        except Exception as exc:
            self.figure_source.setText(str(exc))
            self.figure_view.set_unavailable(str(exc))

    def _export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Engineering Outputs XLSX", "engineering_outputs.xlsx", "Excel Workbook (*.xlsx)")
        if not path:
            return
        self._run_export(lambda: self.service.export_xlsx(self.snapshot, path), "XLSX")

    def _export_images(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Export Native ROSS Images")
        if not directory:
            return
        self._run_export(lambda: self.service.export_figures(self.figure_catalog, directory), "native ROSS PNG images")

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Engineering Outputs PDF", "engineering_outputs_report.pdf", "PDF (*.pdf)")
        if not path:
            return

        def export() -> Path:
            with tempfile.TemporaryDirectory(prefix="ross-studio-engineering-figures-") as temp:
                images = self.service.export_figures(self.figure_catalog, Path(temp))
                return self.service.export_pdf(
                    self.snapshot,
                    path,
                    figure_paths=images,
                    figure_catalog=self.figure_catalog,
                )

        self._run_export(export, "PDF report")

    def _export_manifest(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Qualification Manifest",
            "qualification_manifest.json",
            "JSON (*.json)",
        )
        if not path:
            return
        self._run_export(
            lambda: self.service.export_qualification_manifest(
                self.snapshot,
                path,
                figure_catalog=self.figure_catalog,
            ),
            "Qualification Manifest",
        )

    def _export_package(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Export Full Engineering Outputs Package")
        if not directory:
            return
        root = Path(directory) / "engineering_outputs_018"
        self._run_export(
            lambda: self.service.export_package(
                self.snapshot,
                root,
                figure_catalog=self.figure_catalog,
                include_xlsx=True,
                include_pdf=True,
                include_images=True,
                include_qualification_manifest=True,
            ),
            "full Engineering Outputs package",
        )

    def _run_export(self, operation: Any, label: str) -> None:
        self.export_status.setText(f"Exporting {label}…")
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            value = operation()
        except Exception as exc:
            self.export_status.setText(f"Export failed: {exc}")
        else:
            path = getattr(value, "root", value)
            self.export_status.setText(f"Exported {label}: {path}")
        finally:
            self.unsetCursor()


class EngineeringAnalysisResultsPage(AnalysisResultsPage):
    """Qualified analysis page plus a local Engineering Outputs entry point.

    It intentionally subclasses the existing results page so all 0.17 analysis widgets
    and automation contracts remain intact. The Engineering Outputs button is local to
    this page; no global ``Results``/``Outputs`` sidebar route is introduced.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(project, parent)
        self.engineering_outputs_service = EngineeringOutputsService()
        self.engineering_snapshot: EngineeringOutputsSnapshot | None = None
        self.engineering_figure_catalog: EngineeringFigureCatalog | None = None
        self.engineering_outputs_dialog: EngineeringOutputsDialog | None = None

        # The historical mockup carried placeholder export buttons. Hide them in the
        # qualified composition so the only visible export actions are functional.
        for button in self.findChildren(QPushButton):
            if button.text() in {"Export PNG", "Export CSV", "Generate Report"}:
                button.hide()

        self.engineering_outputs_button = QPushButton("Engineering Outputs", self)
        self.engineering_outputs_button.setObjectName("primaryButton")
        self.engineering_outputs_button.setFixedSize(190, 36)
        self.engineering_outputs_button.setEnabled(False)
        self.engineering_outputs_button.setToolTip("Run the qualified ROSS analysis before opening Engineering Outputs.")
        self.engineering_outputs_button.clicked.connect(self.open_engineering_outputs)
        self.engineering_outputs_button.raise_()
        self.validity_guard = ResultValidityGuard(self, self._invalidate_results)

    def _invalidate_results(self):
        if self.engineering_outputs_dialog is not None:
            self.engineering_outputs_dialog.close()
            self.engineering_outputs_dialog = None
        self.result = None
        self.engineering_snapshot = None
        self.engineering_figure_catalog = None
        self.engineering_outputs_button.setEnabled(False)
        self.result_state.setText("Result invalidated: model changed; run again.")
        self.campbell_chart.clear()
        for card in (self.kpi_first, self.kpi_second, self.kpi_response, self.kpi_damping):
            card.set_value("—")
        self._populate_empty()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        margin = 350
        x = max(12, self.width() - margin - self.engineering_outputs_button.width() - 10)
        self.engineering_outputs_button.move(x, 18)
        self.engineering_outputs_button.raise_()

    def set_results(self, result) -> None:
        super().set_results(result)
        try:
            snapshot = self.engineering_outputs_service.build(self.project, result)
            catalog = EngineeringFigureCatalog(self.project, result)
        except Exception as exc:
            self.engineering_snapshot = None
            self.engineering_figure_catalog = None
            self.engineering_outputs_button.setEnabled(False)
            self.engineering_outputs_button.setToolTip(f"Engineering Outputs unavailable: {exc}")
            return
        self.engineering_snapshot = snapshot
        self.engineering_figure_catalog = catalog
        self.engineering_outputs_button.setEnabled(True)
        self.engineering_outputs_button.setToolTip(
            f"Open {len(snapshot.tables)} engineering tables and {len(catalog.specs)} native ROSS figures."
        )

    def open_engineering_outputs(self) -> None:
        self.validity_guard.check()
        if self.engineering_snapshot is None or self.engineering_figure_catalog is None:
            return
        dialog = EngineeringOutputsDialog(
            self.project,
            self.engineering_snapshot,
            self.engineering_figure_catalog,
            self.engineering_outputs_service,
            self,
        )
        self.engineering_outputs_dialog = dialog
        dialog.exec()


__all__ = ["EngineeringAnalysisResultsPage", "EngineeringOutputsDialog"]
