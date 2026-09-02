
"""Background workers for libDiff GUI."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from libdiff.model.library import Library


class LoadLibraryWorker(QThread):
    """Load a Liberty file off the UI thread."""

    finished_ok = pyqtSignal(object)  # Library
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            lib = Library(self.path)
            # warm cell list
            lib.cell_names()
            self.finished_ok.emit(lib)
        except Exception as exc:  # noqa: BLE001 — surface any load error to GUI
            self.failed.emit(str(exc))
