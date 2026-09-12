"""Qt guard for results tied to an exact project and numerical input snapshot."""
from PySide6.QtCore import QObject, QEvent, QTimer
from .project_io import project_fingerprint


class ResultValidityGuard(QObject):
    def __init__(self, owner, invalidate):
        super().__init__(owner)
        self.owner = owner
        self.invalidate = invalidate
        self.fingerprint = project_fingerprint(owner.project)
        owner.installEventFilter(self)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def check(self):
        current = project_fingerprint(self.owner.project)
        if current != self.fingerprint:
            self.fingerprint = current
            self.invalidate()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            self.check()
        return False
