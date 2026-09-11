from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from .ui_shell import AppToolbar as _BaseAppToolbar
from .ui_shell import QuickActionsCard as _BaseQuickActionsCard


def _dispatch(command: str) -> None:
    from .project_file_controller import dispatch_project_command

    dispatch_project_command(command)


class AppToolbar(_BaseAppToolbar):
    """Desktop project toolbar with one physical-model view contract.

    The former ``Engineering 2D / ROSS Native`` combobox represented two views as
    if they were competing model states.  It is removed here.  The source of truth
    is always the RotorDin-style physical engineering model; a strict ROSS FE view
    is available only inside ``Rotor Completo`` and only after the user explicitly
    enables the discretization toggle.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = self.layout()

        # Remove the obsolete global model-view state created by the legacy shell.
        # Deleting the widget also disconnects its signal from view_mode_requested;
        # no view mode is persisted by the production toolbar.
        legacy_view = getattr(self, "view_combo", None)
        if legacy_view is not None:
            if layout is not None:
                layout.removeWidget(legacy_view)
            legacy_view.hide()
            legacy_view.deleteLater()
            del self.view_combo

        self.file_menu_button = QToolButton(self)
        self.file_menu_button.setObjectName("fileMenuButton")
        self.file_menu_button.setText("Arquivo")
        self.file_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.file_menu = QMenu("Arquivo", self.file_menu_button)
        self.file_menu_button.setMenu(self.file_menu)
        self.file_actions: dict[str, QAction] = {}

        self._action("new", "Novo", QKeySequence.StandardKey.New)
        self._action("open", "Abrir…", QKeySequence.StandardKey.Open)
        self._action("import", "Importar cálculo legado…", QKeySequence("Ctrl+I"))
        self.file_menu.addSeparator()
        self._action("save", "Salvar", QKeySequence.StandardKey.Save)
        self._action("save_as", "Salvar como…", QKeySequence.StandardKey.SaveAs)
        self.file_menu.addSeparator()
        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self._exit_application)
        self.file_menu.addAction(exit_action)
        self.file_actions["exit"] = exit_action

        if layout is not None:
            layout.insertWidget(0, self.file_menu_button)

        self.buttons["new"].clicked.connect(lambda: _dispatch("new"))
        self.buttons["open"].clicked.connect(lambda: _dispatch("open"))
        self.buttons["save"].clicked.connect(lambda: _dispatch("save"))

        # This is the only UI path to the ROSS structural visualization.  The
        # dialog is created from the current project and the ROSS object remains
        # lazy until its own explicit discretization toggle is switched on.
        self.full_rotor_button = self._button(self.layout(), "full_rotor", "Rotor Completo", "rotor")
        self.full_rotor_button.setToolTip("Open full physical rotor view; enable ROSS discretization only on demand")
        self.full_rotor_button.clicked.connect(self._open_full_rotor)

    def _action(self, key: str, text: str, shortcut) -> QAction:
        action = QAction(text, self)
        action.setShortcut(shortcut)
        action.triggered.connect(lambda checked=False, command=key: _dispatch(command))
        self.file_menu.addAction(action)
        self.addAction(action)
        self.file_actions[key] = action
        return action

    def _open_full_rotor(self) -> None:
        window = self.window()
        project = getattr(window, "project", None)
        if project is None:
            return
        from .full_rotor_dialog import FullRotorDialog

        dialog = FullRotorDialog(project, window)
        dialog.exec()

    @staticmethod
    def _exit_application() -> None:
        app = QApplication.instance()
        window = app.activeWindow() if app is not None else None
        if window is not None:
            window.close()


class QuickActionsCard(_BaseQuickActionsCard):
    """Quick Actions uses the same qualified persistence controller as Arquivo/Save."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.save.clicked.connect(lambda: _dispatch("save"))


__all__ = ["AppToolbar", "QuickActionsCard"]
