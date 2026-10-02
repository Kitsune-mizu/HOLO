"""Thread kamera. Membaca frame, memotong ke 16:9, mencerminkan, lalu meneruskannya."""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

import numpy as np
from PySide6.QtCore import QThread, Signal

from ..threads import stop_thread
from .cv import load_cv2

FrameHook = Callable[[np.ndarray], None]


class CameraWorker(QThread):
    statusChanged = Signal(str)   # teks kosong = kamera jalan normal
    frameUpdated = Signal()

    def __init__(self, cfg: dict, on_frame: FrameHook | None = None) -> None:
        super().__init__()
        self._cfg = cfg
        self._on_frame = on_frame
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._seq = 0

    def latest(self) -> tuple[np.ndarray | None, int]:
        with self._lock:
            return self._latest, self._seq

    def stop(self) -> None:
        self._stop.set()
        stop_thread(self, 3000)

    # ------------------------------------------------------------------ thread
    def run(self) -> None:
        try:
            cv2 = load_cv2()
        except ImportError:
            self.statusChanged.emit("OpenCV belum terpasang. Jalankan: pip install -r requirements.txt")
            return
        period = 1.0 / max(1, int(self._cfg.get("fps", 30)))
        while not self._stop.is_set():
            cap = self._open(cv2)
            if cap is None:
                idx = self._cfg.get("index", 0)
                self.statusChanged.emit(f"Kamera tidak ditemukan (indeks {idx}). Sambungkan kamera, atau jalankan dengan --no-camera.")
                if self._stop.wait(3.0):
                    break
                continue
            self.statusChanged.emit("")
            self._read_loop(cv2, cap, period)
            cap.release()
            if not self._stop.is_set():
                self.statusChanged.emit("Kamera terputus. Mencoba menyambung lagi.")
                self._stop.wait(2.0)

    def _open(self, cv2):
        index = int(self._cfg.get("index", 0))
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        try:
            cap = cv2.VideoCapture(index, backend)
        except Exception:
            return None
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self._cfg.get("width", 640)))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self._cfg.get("height", 480)))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _read_loop(self, cv2, cap, period: float) -> None:
        failures = 0
        while not self._stop.is_set():
            started = time.monotonic()
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > 30:
                    return
                time.sleep(0.02)
                continue
            failures = 0
            frame = self._prepare(cv2, frame)
            with self._lock:
                self._latest = frame
                self._seq += 1
            if self._on_frame:
                self._on_frame(frame)
            self.frameUpdated.emit()
            rest = period - (time.monotonic() - started)
            if rest > 0:
                time.sleep(rest)

    @staticmethod
    def _prepare(cv2, frame: np.ndarray) -> np.ndarray:
        """Potong tengah ke 16:9 supaya yang terlihat di kartu sama dengan yang dideteksi, lalu cermin."""
        h, w = frame.shape[:2]
        target = int(w * 9 / 16)
        if target < h:
            y0 = (h - target) // 2
            frame = frame[y0:y0 + target]
        return cv2.flip(frame, 1)
