"""Thread kecil yang memanggil sebuah fungsi berkala dan mengirim hasilnya ke thread utama."""
from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal

from ..threads import stop_thread


class Poller(QThread):
    result = Signal(object)

    def __init__(self, fn: Callable[[], object], interval_s: float, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._interval = max(1.0, interval_s)
        self._stop = threading.Event()
        self._now = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.result.emit(self._fn())
            except Exception as exc:  # satu putaran gagal tidak boleh mematikan poller
                self.result.emit(exc)
            self._now.wait(self._interval)
            self._now.clear()

    def refresh(self) -> None:
        self._now.set()

    def stop(self) -> None:
        self._stop.set()
        self._now.set()
        stop_thread(self, 6000)
