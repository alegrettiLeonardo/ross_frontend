from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMenuBar

from .ui_shell import AppToolbar as _BaseAppToolbar
from .ui_shell import QuickActionsCard as _BaseQuickActionsCard


def _dispatch(command: str) -> None:
    from .project_file_controller import dispatch_project_command

    dispatch_project_command(command)


class AppToolbar(_BaseAppToolbar):
    """ROSS Studio toolbar with a native desktop File command surface."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.file_menu_bar = QMenuBar(self)
        self.file_menu_bar.setObjectName("fileMenuBar")
        self.file_menu_bar.setNativeMenuBar(False)
        self.file_menu = self.file_menu_bar.addMenu("Arquivo")
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

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, self.file_menu_bar)

        self.buttons["new"].clicked.connect(lambda: _dispatch("new"))
        self.buttons["open"].clicked.connect(lambda: _dispatch("open"))
        self.buttons["save"].clicked.connect(lambda: _dispatch("save"))

    def _action(self, key: str, text: str, shortcut) -> QAction:
        action = QAction(text, self)
        action.setShortcut(shortcut)
        action.setShortcutContext(action.shortcutContext())
        action.triggered.connect(lambda checked=False, command=key: _dispatch(command))
        self.file_menu.addAction(action)
        self.file_actions[key] = action
        return action

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
