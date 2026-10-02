"""Penghentian thread yang tidak bisa menggantung, tanpa memaksa terminate()."""
from __future__ import annotations

from PySide6.QtCore import QThread


def stop_thread(thread: QThread | None, timeout_ms: int = 3000) -> None:
    """Tunggu thread selesai sendiri, sampai timeout_ms. Kalau belum selesai (mis. macet menunggu
    baca kamera di kode native OpenCV), JANGAN di-terminate() paksa: memaksa hentikan thread yang
    sedang di tengah pemanggilan native seperti itu bisa mengorupsi state dan meng-crash seluruh
    proses. Cukup lepaskan saja - flag stop yang sudah di-set pemanggil tetap akan membuatnya
    keluar sendiri begitu pemanggilan native itu selesai/unblock."""
    if thread is None or not thread.isRunning():
        return
    thread.wait(timeout_ms)