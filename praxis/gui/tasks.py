"""Running slow requests off the GUI thread.

A model call can take a minute; run on the GUI thread, it would freeze the
window. ``ThreadTaskRunner`` runs the work on a worker thread and hands the
result back on the GUI thread through a Qt signal.

Python/Qt notes: a ``Signal`` is like a Go channel that the GUI's event loop
reads. ``signal.connect(f)`` registers ``f``; ``signal.emit(x)`` calls it with
``x``. When a signal is emitted on one thread and its receiver lives on
another, Qt queues the call, so the receiver runs on its own thread. That is
how a result computed on the worker reaches the views safely.

Only one request runs at a time: the database connection is shared with the
worker (``Database(shared_with_worker=True)``), and an SQLite connection must
not be used from two threads at once. While a request runs, ``busy`` is True
and the views keep their actions disabled (``busy_changed``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

Work = Callable[[], Any]
Done = Callable[[Any], None]
Failed = Callable[[Exception], None]

BUSY_MESSAGE = "Wait for the current request to finish."


def describe_error(exc: Exception) -> str:
    """The message a view shows for a failed request."""
    return str(exc) or type(exc).__name__


class TaskRunner(QObject):
    """Runs one request at a time and reports when it starts and ends."""

    busy_changed = Signal(bool)
    status = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def run(self, description: str, work: Work, on_done: Done, on_error: Failed | None = None) -> bool:
        """Start ``work``; ``on_done`` gets its result, or ``on_error`` its
        exception, on the GUI thread. Returns False, and does nothing, if
        another request is still running."""
        if self._busy:
            self.status.emit(BUSY_MESSAGE)
            return False
        self._set_busy(True)
        self.status.emit(f"{description}…")

        def done(result: Any) -> None:
            self._set_busy(False)
            self.status.emit(f"{description}: done.")
            on_done(result)

        def failed(exc: Exception) -> None:
            self._set_busy(False)
            self.status.emit(f"{description}: failed.")
            if on_error is not None:
                on_error(exc)

        self._start(work, done, failed)
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    def _start(self, work: Work, done: Done, failed: Failed) -> None:
        raise NotImplementedError


class InlineTaskRunner(TaskRunner):
    """Runs the work at once, on the calling thread. For tests, where the
    result should be there as soon as ``run`` returns."""

    def _start(self, work: Work, done: Done, failed: Failed) -> None:
        try:
            result = work()
        except Exception as exc:  # reported to the view, as the threaded runner does
            failed(exc)
            return
        done(result)


class _Relay(QObject):
    """Created on the GUI thread, so its signals are delivered there."""

    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, work: Work, relay: _Relay) -> None:
        super().__init__()
        self._work = work
        self._relay = relay

    def run(self) -> None:  # on the worker thread
        try:
            result = self._work()
        except Exception as exc:
            self._relay.failed.emit(exc)
            return
        self._relay.done.emit(result)


class ThreadTaskRunner(TaskRunner):
    """Runs the work on one worker thread."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._relay: _Relay | None = None  # kept so it is not garbage-collected mid-request

    def _start(self, work: Work, done: Done, failed: Failed) -> None:
        relay = _Relay()
        relay.done.connect(done)
        relay.failed.connect(failed)
        self._relay = relay
        self._pool.start(_Job(work, relay))

    def wait(self, milliseconds: int = -1) -> bool:
        """Block until the running request ends (for shutdown and tests)."""
        return self._pool.waitForDone(milliseconds)
