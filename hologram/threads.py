"""Penghentian thread yang tidak bisa menggantung."""
from __future__ import annotations

from PySide6.QtCore import QThread


def stop_thread(thread: QThread | None, timeout_ms: int = 3000) -> None:
    """Tunggu thread selesai sendiri. Kalau macet (mis. menunggu jaringan), hentikan paksa saat aplikasi keluar."""
    if thread is None or not thread.isRunning():
        return
    if not thread.wait(timeout_ms):
        thread.terminate()
        thread.wait(1000)
