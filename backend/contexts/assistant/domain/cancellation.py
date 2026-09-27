from __future__ import annotations

import threading
from collections.abc import Callable


class CancellationToken:
    """Thread-safe cancellation signal with callbacks for closing active I/O."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def register(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            cancelled = self._event.is_set()
            if not cancelled:
                self._callbacks.append(callback)
        if cancelled:
            self._invoke(callback)

        def unregister() -> None:
            with self._lock:
                try:
                    self._callbacks.remove(callback)
                except ValueError:
                    pass

        return unregister

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            self._invoke(callback)

    @staticmethod
    def _invoke(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            pass
