"""Mikrofon ke teks: sounddevice merekam, faster-whisper mengubah ke teks (offline)."""
from __future__ import annotations

import queue
import threading
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QThread, Signal

from ..config import WHISPER_DIR
from ..threads import stop_thread
from .level import rms

RATE = 16000


class Listener(QThread):
    stateChanged = Signal(str)     # "loading", "listening", "transcribing", "idle"
    heard = Signal(str)
    failed = Signal(str)

    _model = None
    _model_lock = threading.Lock()

    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._finish = threading.Event()

    def start_listening(self) -> None:
        if not self.isRunning():
            self._finish.clear()
            self.start()

    def stop_listening(self) -> None:
        """Hentikan rekaman sekarang dan lanjut ke transkripsi."""
        self._finish.set()

    def shutdown(self) -> None:
        self._finish.set()
        stop_thread(self, 5000)

    # ------------------------------------------------------------------ thread
    def run(self) -> None:
        try:
            model = self._load_model()
            self.stateChanged.emit("listening")
            audio = self._record()
            if audio is None:
                self.failed.emit("Tidak ada suara terdengar. Coba lagi.")
                return
            self.stateChanged.emit("transcribing")
            text = self._transcribe(model, audio)
            if text:
                self.heard.emit(text)
            else:
                self.failed.emit("Ucapan tidak terbaca. Coba lagi.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.stateChanged.emit("idle")

    def _load_model(self):
        name = str(self._cfg.get("stt_model", "base"))
        path = WHISPER_DIR / name
        if not path.is_dir() or not any(path.iterdir()):
            raise RuntimeError(f"Model Whisper '{name}' belum diunduh. Jalankan: python tools/download_assets.py")
        with Listener._model_lock:
            if Listener._model is None:
                self.stateChanged.emit("loading")
                from faster_whisper import WhisperModel

                Listener._model = WhisperModel(str(path), device="cpu", compute_type="int8")
            return Listener._model

    def _record(self) -> np.ndarray | None:
        try:
            import sounddevice as sd
            sd.query_devices(kind="input")
        except Exception as exc:
            raise RuntimeError("Mikrofon tidak ditemukan atau tidak bisa dibuka.") from exc

        blocks: queue.Queue[np.ndarray] = queue.Queue()
        silence_s = float(self._cfg.get("silence_s", 1.2))
        max_s = float(self._cfg.get("max_record_s", 20))
        noise: list[float] = []
        preroll: deque[np.ndarray] = deque(maxlen=4)
        chunks: list[np.ndarray] = []
        speaking, last_voice, start = False, 0.0, time.monotonic()

        def callback(indata, _frames, _time, _status):
            blocks.put(indata[:, 0].copy())

        with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=1600, callback=callback):
            while not self._finish.is_set():
                try:
                    block = blocks.get(timeout=0.2)
                except queue.Empty:
                    continue
                now, level = time.monotonic(), rms(block)
                if now - start < 0.4:
                    noise.append(level)
                    preroll.append(block)
                    continue
                threshold = max(0.015, 3.0 * (sum(noise) / max(1, len(noise))))
                if level > threshold:
                    if not speaking:
                        speaking = True
                        chunks.extend(preroll)
                    last_voice = now
                if speaking:
                    chunks.append(block)
                    if now - last_voice > silence_s or now - start > max_s:
                        break
                else:
                    preroll.append(block)
                    if now - start > 8.0:
                        break
        return np.concatenate(chunks) if chunks else None

    def _transcribe(self, model, audio: np.ndarray) -> str:
        lang = str(self._cfg.get("stt_language", "")) or None
        segments, _info = model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
