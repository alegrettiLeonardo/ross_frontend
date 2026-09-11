from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .models import ProjectModel
from .rotor_scene import InteractiveRotorSketch


class FullRotorDialog(QDialog):
    """Large RotorDin-style model view with opt-in ROSS structural rendering.

    The physical engineering model is always the default.  No ``ross.Rotor`` is
    built in this dialog until the user explicitly enables ``Rotor discretizado``.
    This keeps normal editing independent from the comparatively expensive strict
    ROSS assembly and makes the distinction between source model and FE realization
    explicit instead of storing it in a global view-mode combobox.
    """

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self._ross_view = None
        self._ross_loaded_once = False
        self.setWindowTitle("Rotor Completo")
        self.resize(1280, 760)
        self.setMinimumSize(900, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Rotor Completo")
        title.setObjectName("cardHeader")
        header.addWidget(title)
        header.addStretch(1)
        self.discretized_toggle = QCheckBox("Rotor discretizado (ROSS)")
        self.discretized_toggle.setObjectName("rossDiscretizationToggle")
        self.discretized_toggle.setChecked(False)
        self.discretized_toggle.setEnabled(project.engineering is not None)
        self.discretized_toggle.setToolTip(
            "Off: physical RotorDin engineering model. On: build the strict ROSS 2.3.0 FE rotor and render plot_rotor."
        )
        header.addWidget(self.discretized_toggle)
        root.addLayout(header)

        self.mode_label = QLabel(
            "Modelo físico · edição/inspeção baseada no domínio de engenharia; discretização ROSS não instanciada."
        )
        self.mode_label.setObjectName("muted")
        self.mode_label.setWordWrap(True)
        root.addWidget(self.mode_label)

        self.stack = QStackedWidget()
        self.physical_view = InteractiveRotorSketch(project)
        # RotorDin-like physical view is deliberately clean.  FE nodes/elements are
        # not painted in the default model view; they belong to the explicit ROSS
        # discretized audit view.
        self.physical_view.set_mesh_visible(False)
        self.stack.addWidget(self.physical_view)
        root.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.fit_button = QPushButton("Fit")
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_out_button = QPushButton("Zoom −")
        self.close_button = QPushButton("Close")
        footer.addWidget(self.fit_button)
        footer.addWidget(self.zoom_in_button)
        footer.addWidget(self.zoom_out_button)
        footer.addStretch(1)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.discretized_toggle.toggled.connect(self._set_discretized)
        self.fit_button.clicked.connect(self._fit)
        self.zoom_in_button.clicked.connect(self._zoom_in)
        self.zoom_out_button.clicked.connect(self._zoom_out)
        self.close_button.clicked.connect(self.accept)

    @property
    def ross_structural_view_created(self) -> bool:
        return self._ross_view is not None

    @property
    def ross_structural_view_loaded(self) -> bool:
        return bool(self._ross_view is not None and self._ross_view.loaded)

    def _set_discretized(self, enabled: bool) -> None:
        if not enabled:
            self.stack.setCurrentWidget(self.physical_view)
            self.mode_label.setText(
                "Modelo físico · RotorDin engineering domain é a referência de edição; ROSS não é a vista principal."
            )
            return

        engineering = self.project.engineering
        if engineering is None:
            self.discretized_toggle.blockSignals(True)
            self.discretized_toggle.setChecked(False)
            self.discretized_toggle.blockSignals(False)
            self.mode_label.setText("Não existe modelo de engenharia para discretizar.")
            return

        if self._ross_view is None:
            # Import and widget construction are intentionally lazy.  RossNativeRotorView
            # itself only creates the strict ROSS rotor when refresh() is requested.
            from .ross_native_view import RossNativeRotorView

            self._ross_view = RossNativeRotorView(engineering)
            self.stack.addWidget(self._ross_view)

        if not self._ross_view.loaded:
            self.mode_label.setText("Construindo Rotor estrito e plot_rotor nativo do ROSS 2.3.0…")
            self._ross_view.refresh()
            self._ross_loaded_once = bool(self._ross_view.loaded)

        self.stack.setCurrentWidget(self._ross_view)
        self.mode_label.setText(
            "Rotor discretizado · strict RossModelBuilder → ross.Rotor → Rotor.plot_rotor()."
            if self._ross_view.loaded
            else "A vista discretizada ROSS não pôde ser carregada; consulte a mensagem do painel."
        )

    def _fit(self) -> None:
        if self.stack.currentWidget() is self.physical_view:
            self.physical_view.fit()

    def _zoom_in(self) -> None:
        if self.stack.currentWidget() is self.physical_view:
            self.physical_view.zoom_in()

    def _zoom_out(self) -> None:
        if self.stack.currentWidget() is self.physical_view:
            self.physical_view.zoom_out()


__all__ = ["FullRotorDialog"]
