"""Suara AI: pyttsx3 menghasilkan file audio, lalu diputar lewat sounddevice sambil menghitung level."""
from __future__ import annotations

import asyncio
import os
import queue
import re
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..threads import stop_thread
from .level import LevelMeter

_MARKDOWN = re.compile(r"[*_#`>~|]+")
_URL = re.compile(r"https?://\S+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F]")


def clean_for_speech(text: str, limit: int = 600) -> str:
    text = _URL.sub("tautan", text)
    text = _EMOJI.sub("", _MARKDOWN.sub("", text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > 200 else cut


def pick_voice(voices: list, language: str) -> str | None:
    """Cari suara berbahasa `language` (mis. "id"). None kalau tidak ada, dan suara bawaan dipakai."""
    lang = language.lower()
    for voice in voices:
        langs = " ".join(l.decode("utf-8", "ignore") if isinstance(l, bytes) else str(l) for l in (getattr(voice, "languages", None) or []))
        haystack = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')} {langs}".lower()
        if re.search(rf"(^|[^a-z]){lang}([^a-z]|$)", haystack) or "indones" in haystack and lang == "id":
            return voice.id
    return None


def find_voice(voices: list, name_part: str) -> str | None:
    """Suara pertama yang namanya memuat `name_part` (mis. "Zira"), tanpa peduli huruf besar-kecil."""
    part = name_part.strip().lower()
    if not part:
        return None
    for voice in voices:
        if part in str(getattr(voice, "name", "")).lower():
            return voice.id
    return None


class Speaker(QThread):
    speechStarted = Signal()
    speechFinished = Signal(str)     # teks kosong = selesai normal, selain itu pesan kegagalan
    voiceChosen = Signal(str)
    audioReady = Signal()            # audio sudah jadi dan mulai diputar: saat inilah teks jawaban boleh tampil

    def __init__(self, cfg: dict, meter: LevelMeter, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self.meter = meter
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._interrupt = threading.Event()
        self._quit = threading.Event()
        self._edge_down_until = 0.0      # edge gagal (mis. tanpa internet): pakai suara sistem sampai waktu ini

    def say(self, text: str, lang: str = "id") -> None:
        """Bicara dalam bahasa `lang` ("id" atau "en"). Ucapan yang sedang jalan dipotong."""
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

    # ------------------------------------------------------------------ thread
    def run(self) -> None:
        while not self._quit.is_set():
            try:
                text, lang = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            self._interrupt.clear()
            self.speechStarted.emit()
            error = ""
            stem = Path(tempfile.gettempdir()) / f"hologram_tts_{os.getpid()}"
            try:
                made = self._synthesize(text, stem, lang)
                if not self._interrupt.is_set():
                    self.audioReady.emit()
                    self._play(made)
            except Exception as exc:
                error = f"Suara AI tidak tersedia: {exc}"
            finally:
                for suffix in (".mp3", ".wav"):
                    stem.with_suffix(suffix).unlink(missing_ok=True)
                self.meter.reset()
                if self._queue.empty():          # ada ucapan baru menunggu: jangan kirim "selesai" dulu
                    self.speechFinished.emit(error)

    def _synthesize(self, text: str, stem: Path, lang: str = "id") -> Path:
        """Suara online (edge) dulu kalau dipilih. Gagal atau tanpa internet: suara bawaan sistem.

        Sebelum mencoba edge, cek koneksi cepat (di bawah 1 detik). Kalau jelas tidak ada internet,
        langsung pakai suara sistem tanpa membuang waktu menunggu timeout edge dua kali berturut-turut,
        dan tidak menghukum edge dengan masa istirahat panjang padahal penyebabnya cuma jaringan putus.
        """
        if self._cfg.get("tts_engine", "edge") == "edge" and time.monotonic() >= self._edge_down_until:
            if self._network_ok():
                for attempt in range(2):                    # gangguan jaringan sesaat: coba sekali lagi, tapi cepat
                    try:
                        return self._synth_edge(text, stem.with_suffix(".mp3"), lang)
                    except Exception:
                        time.sleep(0.2)
                self._edge_down_until = time.monotonic() + 12   # koneksi ada tapi tetap gagal: istirahat singkat
            else:
                self._edge_down_until = time.monotonic() + 4    # jelas tidak ada internet: cek lagi sebentar saja
        return self._synth_system(text, stem.with_suffix(".wav"), lang)

    @staticmethod
    def _network_ok() -> bool:
        from ..ai.network import has_internet

        return has_internet(timeout=0.8)

    def _synth_edge(self, text: str, path: Path, lang: str = "id") -> Path:
        import edge_tts

        default = "en-US-JennyNeural" if lang == "en" else "id-ID-GadisNeural"
        voice = str(self._cfg.get("tts_voice_en" if lang == "en" else "tts_voice", default))
        rate = str(self._cfg.get("tts_edge_rate", "+0%"))

        async def fetch() -> None:
            await asyncio.wait_for(edge_tts.Communicate(text, voice, rate=rate).save(str(path)), timeout=6)

        asyncio.run(fetch())
        if not path.exists() or path.stat().st_size < 500:
            raise RuntimeError("suara online tidak menghasilkan audio")
        self.voiceChosen.emit(voice)
        return path

    def _synth_system(self, text: str, path: Path, lang: str = "id") -> Path:
        import pyttsx3

        engine = pyttsx3.init()                       # engine baru tiap ucapan, supaya tidak macet
        try:
            engine.setProperty("rate", int(self._cfg.get("tts_rate", 175)))
            wanted = "en" if lang == "en" else str(self._cfg.get("tts_language", "id"))
            voices = list(engine.getProperty("voices") or [])  # type: ignore[arg-type] (pyttsx3 tanpa berkas tipe)
            preferred = str(self._cfg.get("tts_system_voice_en" if lang == "en" else "tts_system_voice_id", "Zira" if lang == "en" else ""))
            voice = find_voice(voices, preferred) or pick_voice(voices, wanted)   # Inggris: Zira (perempuan) dulu, bukan David
            if voice is None and not self._cfg.get("tts_allow_foreign_voice", False):
                # Jangan membaca teks Indonesia dengan suara Inggris (dan sebaliknya): lebih baik diam dengan pesan jelas.
                raise RuntimeError(f"suara online gagal dan Windows tidak punya suara untuk bahasa '{wanted}'")
            if voice:
                engine.setProperty("voice", voice)
            self.voiceChosen.emit(voice or "suara bawaan sistem")
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