"""Menghubungkan mikrofon (STT) dan suara AI/TTS ke Controller.

Mikrofon dan suara AI adalah dua hal terpisah: tombol speaker di UI hanya mematikan/menghidupkan suara AI
(TTS). Mikrofon tetap bisa dipakai untuk mendikte teks walau suara AI sedang dimatikan. Keduanya dibuat
sekali di awal (kalau tersedia dari config/`--no-voice`) dan tetap hidup selama aplikasi berjalan; tombol
speaker tidak membongkar/membuat ulang thread, hanya mengatur satu flag `tts_enabled`.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Slot

from ..voice.level import LevelMeter
from ..voice.stt import Listener
from ..voice.tts import Speaker


class VoiceLink(QObject):
    def __init__(self, ctl) -> None:
        super().__init__(ctl)
        self.ctl = ctl
        self.meter = LevelMeter()
        self.speaker: Speaker | None = None
        self.listener: Listener | None = None
        self.tts_enabled = True     # ini yang diatur tombol speaker di UI
        self._tts_warned = False
        self._level_timer = QTimer(self, interval=33)
        self._level_timer.timeout.connect(lambda: ctl._set("level", self.meter.value))

    @property
    def available(self) -> bool:
        """Subsistem suara ada sama sekali (config voice.enabled dan bukan --no-voice)."""
        return bool(self.ctl.cfg.get("voice.enabled")) and not self.ctl._no_voice

    @property
    def enabled(self) -> bool:
        """Dipakai Controller: suara AI benar-benar akan berbunyi untuk balasan berikutnya."""
        return self.speaker is not None and self.tts_enabled

    def start(self) -> None:
        """Buat mikrofon dan suara AI kalau tersedia. Dipanggil sekali saat aplikasi mulai."""
        if self.speaker is not None or not self.available:
            return
        cfg = self.ctl.cfg.section("voice")
        self.speaker = Speaker(cfg, self.meter, self)
        self.speaker.speechStarted.connect(self._on_started)
        self.speaker.speechFinished.connect(self._on_finished)
        self.speaker.audioReady.connect(self._on_audio_ready)
        self.speaker.speechWarning.connect(self._on_warning)
        self.listener = Listener(cfg, self)
        self.listener.stateChanged.connect(self._on_listen_state)
        self.listener.heard.connect(self.ctl.transcriptReady)
        self.listener.failed.connect(self._on_listen_failed)

    def shutdown(self) -> None:
        """Matikan suara sepenuhnya (aplikasi ditutup): hentikan bicara/dengar dan lepas kedua thread."""
        self.stop_speaking()
        for part in (self.speaker, self.listener):
            if part:
                part.shutdown()
        self.speaker = self.listener = None

    def set_tts_enabled(self, on: bool) -> None:
        """Tombol speaker: nyalakan/matikan HANYA suara AI. Mikrofon tidak tersentuh sama sekali."""
        if on == self.tts_enabled:
            return
        self.tts_enabled = on
        self.ctl._set("voiceEnabled", on)
        if not on:
            self.stop_speaking()               # ucapan yang sedang jalan langsung berhenti

    # ------------------------------------------------------------------ dipanggil Controller
    def say(self, text: str, lang: str = "id") -> None:
        if self.speaker and self.tts_enabled:
            self.ctl._set("speaking", True)
            self.speaker.say(text, lang)

    def stop_speaking(self) -> None:
        if self.speaker:
            self.speaker.stop_speaking()
        self._speech_over()

    def toggle_mic(self) -> None:
        """Mikrofon berdiri sendiri, tidak dipengaruhi tombol speaker/tts_enabled."""
        if not self.listener:
            self.ctl._note("Mikrofon tidak tersedia (--no-voice atau voice.enabled = false).")
        elif self.ctl.get("speaking"):
            return                                   # mikrofon tidak aktif selagi AI berbicara
        elif self.ctl.get("listening"):
            self.listener.stop_listening()
        else:
            self.listener.start_listening()

    # ------------------------------------------------------------------ sinyal dari thread suara
    def _speech_over(self) -> None:
        self.ctl._set("speaking", False)
        self._level_timer.stop()
        self.ctl._set("level", 0.0)

    @Slot()
    def _on_started(self) -> None:
        if self.listener and self.ctl.get("listening"):
            self.listener.stop_listening()
        self.ctl._set("speaking", True)
        self._level_timer.start()

    @Slot()
    def _on_audio_ready(self) -> None:
        self.ctl._flush_pending()

    @Slot(str)
    def _on_warning(self, message: str) -> None:
        """Peringatan tidak fatal (mis. lagi pakai suara cadangan). Ditampilkan tiap kejadian,
        karena sudah dijarangkan sendiri oleh cooldown/backoff di Speaker, bukan spam per pesan."""
        self.ctl._note(message)

    @Slot(str)
    def _on_finished(self, error: str) -> None:
        self.ctl._flush_pending()                    # suara gagal atau selesai: teks tidak boleh tertahan
        self._speech_over()
        if error and not self._tts_warned:
            self._tts_warned = True
            self.ctl._note(error)

    @Slot(str)
    def _on_listen_state(self, state: str) -> None:
        self.ctl._set("listening", state in ("loading", "listening"))

    @Slot(str)
    def _on_listen_failed(self, message: str) -> None:
        self.ctl._note(message)
