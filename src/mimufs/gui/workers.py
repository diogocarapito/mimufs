"""Run :mod:`mimufs.core` functions off the GUI thread (TECH_SPECS §14.3).

``Worker(fn, *args)`` runs ``fn(*args)`` in the global :class:`QThreadPool` and reports back
through queued signals, so slots always run on the GUI thread. With ``with_progress=True`` the
function also receives ``progress=callback(percent, message)``.

:class:`MainThreadGC`: Python's cyclic garbage collector runs in whichever thread happens to
allocate, so it could destroy Qt widgets from a worker thread, which crashes (seen on Linux CI).
While the GUI runs, automatic collection is off and a timer collects in the GUI thread instead.
"""

from __future__ import annotations

import gc
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, QTimer, Signal

log = logging.getLogger(__name__)


class MainThreadGC(QObject):
    """Collect garbage only in the GUI thread (the approach pyqtgraph uses)."""

    INTERVAL_MS = 1000

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(self.INTERVAL_MS)

    def check(self) -> None:
        count0, count1, count2 = gc.get_count()
        if count0 > self.threshold[0]:
            gc.collect(0)
            if count1 > self.threshold[1]:
                gc.collect(1)
                if count2 > self.threshold[2]:
                    gc.collect(2)


def install_gc_guard() -> MainThreadGC | None:
    """Once per application; called when the main window is created."""
    app = QCoreApplication.instance()
    if app is None:
        return None
    existing = app.findChild(MainThreadGC)
    return existing if existing is not None else MainThreadGC(app)


class WorkerSignals(QObject):
    progress = Signal(int, str)
    finished = Signal(object)  # the function's return value
    failed = Signal(object)  # the exception


class Worker(QRunnable):
    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        if with_progress:
            self.kwargs["progress"] = self._report
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def _report(self, percent: int, message: str = "") -> None:
        self.signals.progress.emit(int(percent), message)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            # Only the type: exception messages can quote file contents (TECH_SPECS §12.1).
            log.warning(
                "worker %s failed (%s)", getattr(self.fn, "__name__", "?"), type(exc).__name__
            )
            self.signals.failed.emit(exc)
            return
        self.signals.finished.emit(result)


class WorkerPool:
    """Starts workers and keeps them referenced until they report back."""

    def __init__(self, pool: QThreadPool | None = None) -> None:
        self.pool = pool or QThreadPool.globalInstance()
        self._running: set[Worker] = set()

    def start(
        self,
        worker: Worker,
        on_finished: Callable[[Any], None] | None = None,
        on_failed: Callable[[BaseException], None] | None = None,
    ) -> Worker:
        self._running.add(worker)
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)
        if on_failed is not None:
            worker.signals.failed.connect(on_failed)
        worker.signals.finished.connect(lambda _r: self._running.discard(worker))
        worker.signals.failed.connect(lambda _e: self._running.discard(worker))
        self.pool.start(worker)
        return worker

    def wait(self, msecs: int = -1) -> bool:
        return self.pool.waitForDone(msecs)

    @property
    def active(self) -> int:
        return len(self._running)
