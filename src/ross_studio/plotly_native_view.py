from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class NativeRossFigureView(QWidget):
    """Render an unmodified ROSS Plotly figure inside the desktop application.

    ROSS remains the owner of traces, semantics, axes and hover data.  ROSS Studio
    only provides a local HTML transport and Qt WebEngine host.  This deliberately
    replaces application-side re-plotting of scientific result arrays.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._web = None
        self._html_path: Path | None = None
        self._figure: Any | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._message = QLabel("No native ROSS plot selected.")
        self._message.setObjectName("muted")
        self._message.setWordWrap(True)
        self._message.setStyleSheet("padding:24px;")
        root.addWidget(self._message)
        self._layout = root

    @property
    def figure(self) -> Any | None:
        return self._figure

    def set_unavailable(self, message: str) -> None:
        self._figure = None
        if self._web is not None:
            self._web.hide()
        self._message.setText(message)
        self._message.show()

    def set_figure(self, figure: Any, *, tooltip: str = "ROSS native Plotly result") -> bool:
        if figure is None or not hasattr(figure, "to_html"):
            self.set_unavailable("ROSS did not return a Plotly Figure for this result.")
            return False
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # pragma: no cover - platform runtime dependency
            self.set_unavailable(f"Qt WebEngine is unavailable: {exc}")
            return False

        try:
            html = figure.to_html(
                full_html=True,
                include_plotlyjs=True,
                config={"displaylogo": False, "responsive": True, "scrollZoom": True},
            )
            handle = tempfile.NamedTemporaryFile(prefix="ross-studio-result-", suffix=".html", delete=False)
            handle.write(html.encode("utf-8"))
            handle.close()
            new_path = Path(handle.name)
            old_path = self._html_path
            self._html_path = new_path
            if old_path is not None:
                old_path.unlink(missing_ok=True)
            if self._web is None:
                self._web = QWebEngineView(self)
                self._layout.addWidget(self._web, 1)
            self._message.hide()
            self._web.show()
            self._web.setToolTip(tooltip)
            self._web.setUrl(QUrl.fromLocalFile(str(new_path)))
            self._figure = figure
            return True
        except Exception as exc:
            self.set_unavailable(f"ROSS native Plotly rendering failed: {exc}")
            return False

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._html_path is not None:
            self._html_path.unlink(missing_ok=True)
            self._html_path = None
        super().closeEvent(event)


__all__ = ["NativeRossFigureView"]
