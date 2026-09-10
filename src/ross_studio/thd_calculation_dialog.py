"""Keep Qt responsive while the native ROSS solver runs in a worker thread."""
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout


class CalculationThread(QThread):
    def __init__(self, service, project, index, ross_class, inputs, parent):
        super().__init__(parent)
        self.arguments = service, project, index, ross_class, inputs
        self.result = None
        self.error = None

    def run(self):
        service, project, index, ross_class, inputs = self.arguments
        try:
            self.result = service.calculate(project, index, ross_class, inputs)
        except Exception as exc:
            self.error = exc


class THDCalculationDialog(QDialog):
    def __init__(self, service, project, index, ross_class, inputs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Solving {ross_class} · ROSS 2.3.0")
        root = QVBoxLayout(self)
        label = QLabel("Solving the requested speed stations. This window closes when the native calculation finishes.")
        label.setWordWrap(True)
        root.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        root.addWidget(progress)
        self.worker = CalculationThread(service, project, index, ross_class, inputs, self)
        self.worker.finished.connect(self.accept)
        QTimer.singleShot(0, self.worker.start)

    def reject(self):
        # ROSS has no safe cancellation point inside a THD solve.
        if not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)

    def calculate(self):
        self.exec()
        self.worker.wait()
        if self.worker.error is not None:
            raise self.worker.error
        return self.worker.result
