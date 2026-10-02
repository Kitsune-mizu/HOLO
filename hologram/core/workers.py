"""Pekerja latar untuk permintaan AI, supaya jendela tidak macet selagi menunggu jawaban."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class AskWorker(QThread):
    """Menjalankan router.ask di thread sendiri. Hasil: (teks_pengguna, Reply atau Exception)."""

    done = Signal(object)

    def __init__(self, router, build_system, history, image, light: bool, user_text: str, parent=None) -> None:
        super().__init__(parent)
        self._args = (router, build_system, history, image, light)
        self._user_text = user_text

    def run(self) -> None:
        router, build_system, history, image, light = self._args
        try:
            result: object = router.ask(build_system, history, image, light)
        except Exception as exc:
            result = exc
        self.done.emit((self._user_text, result))
