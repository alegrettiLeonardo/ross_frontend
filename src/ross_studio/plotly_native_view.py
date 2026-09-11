from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def _webengine_enabled() -> bool:
    """Use Qt WebEngine only when a real GUI platform is available.

    QtWebEngine is not teardown-safe with the offscreen platform used by pytest/CI;
    creating even an idle QWebEngineView there can leave a WebEnginePage alive when
    QApplication is destroyed and crash the process with SIGSEGV.  Scientific
    qualification does not require JavaScript rendering, so headless runs retain the
    exact Plotly figure object without constructing WebEngine at all.
    """

    explicit = os.environ.get("ROSS_STUDIO_DISABLE_WEBENGINE", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return False
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    return platform not in {"offscreen", "minimal", "headless"}


class NativeRossFigureView(QWidget):
    """Render an unmodified ROSS Plotly figure inside the desktop application.

    ROSS remains the owner of traces, semantics, axes and hover data. ROSS Studio
    only provides a local HTML transport and Qt WebEngine host. In headless test/CI
    environments the original Plotly figure is retained and exposed through
    ``figure`` while WebEngine creation is intentionally skipped.
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

    @property
    def webengine_active(self) -> bool:
        return self._web is not None

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

        # Keep the scientific object even when JavaScript rendering is intentionally
        # disabled. Tests and qualification can therefore prove native-output
        # ownership without ever initializing QtWebEngine in an offscreen process.
        self._figure = figure
        self.setToolTip(tooltip)
        if not _webengine_enabled():
            if self._web is not None:
                self._web.hide()
            self._message.setText(
                "Native ROSS Plotly figure retained. Interactive WebEngine rendering "
                "is disabled for the current headless/offscreen Qt platform."
            )
            self._message.show()
            return True

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # pragma: no cover - platform runtime dependency
            self._message.setText(f"Qt WebEngine is unavailable: {exc}")
            self._message.show()
            return True

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
            return True
        except Exception as exc:
            # Rendering transport failure must not discard a valid ROSS result.
            self._message.setText(f"ROSS native figure retained; interactive rendering failed: {exc}")
            self._message.show()
            if self._web is not None:
                self._web.hide()
            return True

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._html_path is not None:
            self._html_path.unlink(missing_ok=True)
            self._html_path = None
        if self._web is not None:
            # Desktop cleanup. Headless tests never create WebEngine, which is the
            # important crash-isolation boundary for CI.
            self._web.hide()
            self._web.close()
        super().closeEvent(event)


__all__ = ["NativeRossFigureView"]
