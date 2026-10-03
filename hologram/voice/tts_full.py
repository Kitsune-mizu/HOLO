"""Suara untuk Mode AI (AI Full) - file TERPISAH dari `tts.py` (punya HologramOS), dioptimalkan
khusus untuk mode ini agar terasa responsif seperti chat AI biasa:

- Teks jawaban ditampilkan SEGERA (tidak menunggu audio sama sekali) - beda dari mode HologramOS
  yang menunggu teks & suara bersamaan; di sini kecepatan chat lebih penting daripada sinkronisasi itu.
- AI Full diasumsikan selalu online (butuh internet untuk model AI-nya juga), jadi tidak ada logika
  `prefer_system`/deteksi-jaringan-dulu seperti di tts.py - edge-tts dicoba SEKALI saja dengan timeout
  pendek, gagal langsung ke suara sistem, dengan cooldown singkat supaya tidak berulang kali membuang
  waktu kalau edge memang sedang bermasalah.

Fungsi bantu murni (pembersihan teks, pilih suara sistem) diimpor dari tts.py supaya tidak ada logika
yang didobelkan - hanya alur/kelasnya yang benar-benar baru dan berdiri sendiri.
"""
from __future__ import annotations

import asyncio
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..threads import stop_thread
from .level import LevelMeter
from .tts import clean_for_speech, find_voice, pick_voice


class FullSpeaker(QThread):
    speechStarted = Signal()
    speechFinished = Signal(str)     # teks kosong = selesai normal
    textReady = Signal()             # SEGERA - lihat catatan di atas kenapa ini beda dari tts.py
    speechWarning = Signal(str)

    def __init__(self, cfg: dict, meter: LevelMeter, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self.meter = meter
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._interrupt = threading.Event()
        self._quit = threading.Event()
        self._edge_down_until = 0.0
        self._edge_fail_streak = 0

    def say(self, text: str, lang: str = "id") -> None:
        text = clean_for_speech(text)
        if not text:
            return
        self.stop_speaking()
        self._queue.put((text, lang))
        if not self.isRunning():
            self.start()

    def stop_speaking(self) -> None:
        self._interrupt.set()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self._quit.set()
        self.stop_speaking()
        stop_thread(self, 3000)

    def run(self) -> None:
        while not self._quit.is_set():
            try:
                text, lang = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            self._interrupt.clear()
            self.speechStarted.emit()
            self.textReady.emit()               # segera, tidak menunggu audio sama sekali
            error = ""
            stem = Path(tempfile.gettempdir()) / f"hologram_full_tts_{os.getpid()}"
            try:
                made = self._synthesize(text, stem, lang)
                if not self._interrupt.is_set():
                    self._play(made)
            except Exception as exc:
                error = f"Suara AI Full tidak tersedia: {exc}"
            finally:
                for suffix in (".mp3", ".wav"):
                    stem.with_suffix(suffix).unlink(missing_ok=True)
                self.meter.reset()
                if self._queue.empty():
                    self.speechFinished.emit(error)

    def _synthesize(self, text: str, stem: Path, lang: str = "id") -> Path:
        engine = self._cfg.get("tts_engine", "edge")
        # Konfigurasi bisa melewati edge-tts sama sekali - berguna kalau jaringan memang tidak
        # pernah bisa menjangkau server suara online-nya, supaya tidak ada jeda tunggu sama sekali.
        if engine != "edge":
            return self._synth_system(text, stem.with_suffix(".wav"), lang)
        if time.monotonic() < self._edge_down_until:
            return self._synth_system(text, stem.with_suffix(".wav"), lang)
        try:
            path = self._synth_edge(text, stem.with_suffix(".mp3"), lang)
            self._edge_fail_streak = 0
            return path
        except Exception as exc:
            # Gagal berturut-turut (mis. jaringan memang tidak bisa menjangkau server suara online
            # ini) -> jeda sebelum coba lagi membesar (8s, 20s, 45s, maks 120s), supaya tidak setiap
            # pesan menunggu edge timeout dulu baru pindah ke suara sistem - itu jeda yang dirasakan.
            self._edge_fail_streak += 1
            cooldown = min(120.0, 8.0 * (2.2 ** min(self._edge_fail_streak - 1, 4)))
            self._edge_down_until = time.monotonic() + cooldown
            reason = str(exc) or type(exc).__name__            # beberapa exception (mis. asyncio.TimeoutError) str()-nya kosong
            self.speechWarning.emit(f"Suara online Mode AI gagal ({reason}), pakai suara sistem selama {cooldown:.0f}s ke depan.")
            return self._synth_system(text, stem.with_suffix(".wav"), lang)

    def _synth_edge(self, text: str, path: Path, lang: str = "id") -> Path:
        import edge_tts

        default = "en-US-JennyNeural" if lang == "en" else "id-ID-GadisNeural"
        voice = str(self._cfg.get("tts_voice_en" if lang == "en" else "tts_voice", default))
        # Timeout menyesuaikan panjang teks - balasan Mode AI boleh panjang (sampai ribuan token),
        # jadi batas waktu tetap pendek akan sering habis duluan sebelum edge-tts selesai
        # mensintesis teks panjang. Batas bawah dinaikkan ke 6 detik (round-trip ke server suara
        # online kadang memang butuh itu meski teksnya pendek), batas atas 25 detik.
        timeout = min(25.0, max(6.0, len(text) / 45.0))

        async def fetch() -> None:
            await asyncio.wait_for(edge_tts.Communicate(text, voice).save(str(path)), timeout=timeout)

        asyncio.run(fetch())
        if not path.exists() or path.stat().st_size < 500:
            raise RuntimeError("suara online tidak menghasilkan audio")
        return path

    def _synth_system(self, text: str, path: Path, lang: str = "id") -> Path:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", int(self._cfg.get("tts_rate", 175)))
            voices = list(engine.getProperty("voices") or [])  # type: ignore[arg-type]
            voice = find_voice(voices, str(self._cfg.get("tts_system_voice_id", ""))) or pick_voice(voices, lang)
            if voice is None and voices:
                voice = voices[0].id
            if voice is None:
                raise RuntimeError("tidak ada suara TTS terpasang di sistem")
            engine.setProperty("voice", voice)
            engine.save_to_file(text, str(path))
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass
        if not path.exists() or path.stat().st_size < 100:
            raise RuntimeError("mesin suara tidak menghasilkan audio")
        return path

    def _play(self, path: Path) -> None:
        import sounddevice as sd
        import soundfile as sf

        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        done = threading.Event()
        pos = 0

        def callback(outdata, frames, _time, _status):
            nonlocal pos
            if self._interrupt.is_set():
                raise sd.CallbackStop
            chunk = data[pos:pos + frames]
            outdata[:len(chunk)] = chunk
            if len(chunk) < frames:
                outdata[len(chunk):] = 0
                raise sd.CallbackStop
            self.meter.push(chunk[:, 0])
            pos += frames

        with sd.OutputStream(samplerate=rate, channels=data.shape[1], callback=callback, finished_callback=done.set):
            done.wait(timeout=len(data) / rate + 5)