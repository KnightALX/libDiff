"""PyQt-Fluent-Widgets GUI for libDiff."""

__all__ = ["MainWindow", "run_gui"]


def __getattr__(name):
    if name in ("MainWindow", "run_gui"):
        from libdiff.gui.main_window import MainWindow, run_gui

        return {"MainWindow": MainWindow, "run_gui": run_gui}[name]
    raise AttributeError(name)
