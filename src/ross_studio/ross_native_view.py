from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import tempfile
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .domain import RotorProject
from .ross_backend import RossModelBuilder


@dataclass(slots=True, frozen=True)
class RossRotorFigureResult:
    figure: Any
    node_increment: int
    shaft_elements: int
    nodes: int


class RossRotorPlotService:
    """Create the model visualization through the pinned ROSS plotting API.

    The Studio keeps its own selectable engineering sketch for editing, while this
    service exposes ROSS' native ``Rotor.plot_rotor`` Plotly figure as an independent
    audit view. This prevents the GUI from claiming a topology different from the
    strict ROSS object actually used by the analyses.
    """

    def __init__(self, ross_module: Any | None = None) -> None:
        self.rs = ross_module

    def build_figure(self, project: RotorProject) -> RossRotorFigureResult:
        rs = self.rs or import_module("ross")
        if getattr(rs, "__version__", None) != "2.3.0":
            raise RuntimeError(
                f"ROSS native model view is qualified for ROSS 2.3.0; received {getattr(rs, '__version__', 'unknown')}."
            )
        built = RossModelBuilder(rs).build(project, strict=True)
        node_count = len(built.node_positions_mm)
        node_increment = max(1, (node_count + 24) // 25)
        figure = built.rotor.plot_rotor(
            nodes=node_increment,
            check_sld=True,
            length_units="mm",
        )
        figure.update_layout(
            margin=dict(l=35, r=25, t=30, b=45),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
        )
        return RossRotorFigureResult(
            figure=figure,
            node_increment=node_increment,
            shaft_elements=len(built.shaft_plan),
            nodes=node_count,
        )

    def to_html(self, project: RotorProject) -> tuple[str, RossRotorFigureResult]:
        result = self.build_figure(project)
        html = result.figure.to_html(
            full_html=True,
            include_plotlyjs=True,
            config={
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": True,
            },
        )
        return html, result


class RossNativeRotorView(QWidget):
    """Lazy Qt host for the offline Plotly figure returned by ROSS."""

    def __init__(self, project: RotorProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = RossRotorPlotService()
        self._web = None
        self._html_path: Path | None = None
        self._loaded = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._message = QLabel("ROSS native view is loaded on demand from the strict rotor object.")
        self._message.setWordWrap(True)
        self._message.setStyleSheet("padding:24px;color:#61778d;")
        self._layout.addWidget(self._message)

    @property
    def loaded(self) -> bool:
        return self._loaded

    def refresh(self) -> None:
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # pragma: no cover - depends on optional Qt runtime component
            self._message.setText(
                "ROSS native Plotly view is unavailable because Qt WebEngine could not be loaded. "
                f"The scientific rotor remains available. Runtime detail: {exc}"
            )
            return

        try:
            html, result = self.service.to_html(self.project)
            if self._html_path is not None:
                self._html_path.unlink(missing_ok=True)
            handle = tempfile.NamedTemporaryFile(prefix="ross-studio-rotor-", suffix=".html", delete=False)
            handle.write(html.encode("utf-8"))
            handle.close()
            self._html_path = Path(handle.name)
            if self._web is None:
                self._layout.removeWidget(self._message)
                self._message.hide()
                self._web = QWebEngineView(self)
                self._layout.addWidget(self._web, 1)
            self._web.setUrl(QUrl.fromLocalFile(str(self._html_path)))
            self._web.setToolTip(
                f"ROSS 2.3.0 native plot_rotor · {result.shaft_elements} shaft elements · {result.nodes} nodes"
            )
            self._loaded = True
        except Exception as exc:
            self._message.show()
            self._message.setText(f"ROSS native rotor view failed strict construction: {exc}")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._html_path is not None:
            self._html_path.unlink(missing_ok=True)
        super().closeEvent(event)


__all__ = ["RossNativeRotorView", "RossRotorFigureResult", "RossRotorPlotService"]
