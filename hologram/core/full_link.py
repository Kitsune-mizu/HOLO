"""Penghubung UI <-> AI untuk Mode AI (AI Full). TERPISAH TOTAL dari `controller.py`: tidak ada
Router/Ollama/ActionRunner/CameraLink/model 3D di sini sama sekali - hanya percakapan AI online biasa.
Diberi nama beda (`FullLink`, bukan `Controller`) dan didaftarkan sebagai context property sendiri
("fullAI") supaya benar-benar tidak saling berhubungan dengan sisi HologramOS.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, QThread, QTimer, Signal, Slot

from ..ai.base import ProviderError
from ..ai.full_session import FullSession
from ..threads import stop_thread
from ..voice.level import LevelMeter
from ..voice.tts_full import FullSpeaker
from . import lang
from .messages import MessageModel


class _AskWorker(QThread):
    """Satu pertanyaan = satu thread singkat, seperti AskWorker punya HologramOS, tapi memanggil
    FullSession (bukan Router) - dibuat di sini karena kecil dan supaya full_link.py berdiri sendiri."""

    done = Signal(object)   # str (balasan) ATAU Exception

    def __init__(self, session: FullSession, text: str, lng: str, parent=None) -> None:
        super().__init__(parent)
        self._session, self._text, self._lang = session, text, lng

    def run(self) -> None:
        try:
            result: object = self._session.ask(self._text, self._lang)
        except Exception as exc:            # noqa: BLE001 - dikirim balik ke thread GUI untuk ditangani di sana
            result = exc
        self.done.emit(result)


class FullLink(QObject):
    busyChanged = Signal()
    speakingChanged = Signal()
    levelChanged = Signal()
    voiceEnabledChanged = Signal()
    engineChanged = Signal()

    def __init__(self, cfg, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self.messages = MessageModel()
        self.session = FullSession(cfg)
        self._busy = False
        self._speaking = False
        self._voice_enabled = True
        self._lang = "id"
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(50)
        self._level_timer.timeout.connect(lambda: self.levelChanged.emit())
        self._workers: list[_AskWorker] = []

        self.meter = LevelMeter()
        self.speaker = FullSpeaker(dict(cfg.section("ai_full")), self.meter, self)
        self.speaker.textReady.connect(self._on_text_ready)
        self.speaker.speechStarted.connect(self._on_speech_started)
        self.speaker.speechFinished.connect(self._on_speech_finished)
        self.speaker.speechWarning.connect(lambda msg: self.messages.append("system", msg))
        self._pending_reply = ""

        if self.session.history:   # riwayat tersimpan dari sesi sebelumnya - tampilkan lagi di UI
            for turn in self.session.history:
                self.messages.append("user" if turn.role == "user" else "ai", turn.text)
            self.messages.append("system", "Percakapan sebelumnya dimuat kembali.")

    # ------------------------------------------------------------------ dipanggil dari Python (bukan QML)
    def shutdown(self) -> None:
        self.speaker.shutdown()
        for w in self._workers:
            stop_thread(w, 1500)

    # ------------------------------------------------------------------ properti untuk QML
    def _get_busy(self) -> bool:
        return self._busy

    def _get_speaking(self) -> bool:
        return self._speaking

    def _get_level(self) -> float:
        return self.meter.value

    def _get_voice_enabled(self) -> bool:
        return self._voice_enabled

    def _get_tokens_used(self) -> int:
        p = self.session._active_provider
        return p.total_prompt_tokens + p.total_output_tokens

    def _get_requests_used(self) -> int:
        return self.session._active_provider.request_count

    def _get_engine(self) -> str:
        return self.session.engine

    @Property(list, constant=True)
    def engines(self) -> list:
        return [{"id": e_id, "label": label} for e_id, label in self.session.engines]

    def _set_voice_enabled(self, on: bool) -> None:
        if on != self._voice_enabled:
            self._voice_enabled = on
            self.voiceEnabledChanged.emit()

    busy = Property(bool, _get_busy, notify=busyChanged)
    speaking = Property(bool, _get_speaking, notify=speakingChanged)
    level = Property(float, _get_level, notify=levelChanged)
    voiceEnabled = Property(bool, _get_voice_enabled, _set_voice_enabled, notify=voiceEnabledChanged)
    # Bukan "sisa kuota" (Gemini API key tidak expose itu) - ini akumulasi token/permintaan yang
    # BENAR-BENAR terpakai sejauh ini di sesi ini, dari usageMetadata respons Gemini sendiri.
    tokensUsed = Property(int, _get_tokens_used, notify=busyChanged)
    requestsUsed = Property(int, _get_requests_used, notify=busyChanged)
    engine = Property(str, _get_engine, notify=engineChanged)

    # ------------------------------------------------------------------ slot untuk QML
    @Slot(str)
    def selectEngine(self, engine_id: str) -> None:
        if self.session.select_engine(engine_id):
            self.engineChanged.emit()
            self.busyChanged.emit()   # dipakai juga sebagai sinyal "baca ulang" tokensUsed/requestsUsed
            self.messages.append("system", f"Engine AI: {dict(self.session.engines).get(engine_id, engine_id)}.")

    @Slot()
    def clearHistory(self) -> None:
        self.session.reset()
        self.messages.clear()
        self.messages.append("system", "Riwayat Mode AI dihapus.")

    @Slot()
    def resetConversation(self) -> None:        # alias lama, dipertahankan untuk kompatibilitas
        self.clearHistory()

    @Slot()
    def toggleVoice(self) -> None:
        self._set_voice_enabled(not self._voice_enabled)

    @Slot()
    def stopSpeaking(self) -> None:
        self.speaker.stop_speaking()

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        text = text.strip()
        if not text or self._busy:
            return
        self._lang = lang.detect(text, self._lang)
        self.messages.append("user", text)
        self._set_busy(True)
        worker = _AskWorker(self.session, text, self._lang, self)
        self._workers.append(worker)
        worker.done.connect(lambda result, w=worker: self._on_reply(w, result))
        worker.start()

    # ------------------------------------------------------------------ internal
    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    def _on_reply(self, worker: _AskWorker, result: object) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()
        if isinstance(result, Exception):
            reason = str(result) if isinstance(result, ProviderError) else f"Kesalahan tak terduga: {result}"
            self.messages.append("system", f"Mode AI gagal menjawab: {reason}")
            self._set_busy(False)
            return
        text = str(result).strip() or "(AI tidak memberi jawaban yang bisa ditampilkan.)"
        self._pending_reply = text
        if self._voice_enabled:
            self.speaker.say(text, self._lang)     # textReady -> _on_text_ready akan menampilkannya
        else:
            self._show_pending()

    def _show_pending(self) -> None:
        if self._pending_reply:
            self.messages.append("ai", self._pending_reply)
            self._pending_reply = ""
        self._set_busy(False)

    def _on_text_ready(self) -> None:
        self._show_pending()

    def _on_speech_started(self) -> None:
        self._speaking = True
        self.speakingChanged.emit()
        self._level_timer.start()

    def _on_speech_finished(self, error: str) -> None:
        self._speaking = False
        self.speakingChanged.emit()
        self._level_timer.stop()
        self.levelChanged.emit()
        if error:
            self.messages.append("system", error)