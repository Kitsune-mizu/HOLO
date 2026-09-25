"""Penghubung UI <-> AI <-> 3D <-> kamera <-> suara. Satu-satunya bagian yang tahu semuanya."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal, Slot

from ..ai import prompts
from ..ai.base import Turn
from ..ai.gemini_provider import GeminiProvider
from ..ai.network import has_internet
from ..ai.ollama_provider import OllamaProvider
from ..ai.openai_compat import OpenAICompatProvider
from ..ai.router import AllFailed, OnlineTarget, Router
from ..config import MODELS_DIR, MODELS_JSON, Config
from ..models3d.registry import ModelRegistry
from ..threads import stop_thread
from ..vision.frame_provider import FrameProvider
from . import device, intent, lang
from .actions import ActionRunner, Command, parse_command
from .camera_link import CameraLink
from .messages import MessageModel
from .poller import Poller
from .state import AppState
from .voice_link import VoiceLink
from .workers import AskWorker


class Controller(AppState):
    viewCommand = Signal(str, str)         # (perintah, argumen) untuk Viewer3D
    snapshotRequested = Signal(str)        # QML menyimpan tangkapan 3D ke path ini
    transcriptReady = Signal(str)          # hasil mikrofon, dikirim ke kolom input

    def __init__(self, cfg: Config, provider: FrameProvider, no_camera: bool = False, no_voice: bool = False) -> None:
        super().__init__()
        self.cfg, self.provider = cfg, provider
        self.messages = MessageModel()
        self.registry = ModelRegistry(MODELS_JSON, MODELS_DIR)
        self.router = self._build_router()
        self.runner = ActionRunner(self.registry, self)
        self._no_camera, self._no_voice = no_camera, no_voice
        self._history: list[Turn] = []
        self._workers: list[AskWorker] = []
        self._current = None
        self._snap: tuple[int, str, str] | None = None
        self._snap_token = 0
        self._ollama_err = None
        self._lang = "id"                       # bahasa percakapan terakhir: "id" atau "en"
        self._pending: list[str] = []          # jawaban yang menunggu tampil (harus segera lewat textReady)
        self._warmed: set[str] = set()
        self.poller = None
        self.camera_link = CameraLink(self)
        self.voice_link = VoiceLink(self)   # textReady->_flush_pending sudah disambungkan di dalam VoiceLink
        self._set("mode", self.router.mode)
        self._set("voiceEnabled", True)   # suara AI aktif secara default kalau subsistemnya tersedia
        self._sync_router()

    # ------------------------------------------------------------------ mulai dan berhenti
    def start(self) -> None:
        default = self.registry.get(str(self.cfg.get("app.default_model"))) or (self.registry.all() or [None])[0]
        if default:
            self._load_entry(default)
            self._note(f'Halo. Model tampil: {default.name}. Coba "zoom in", "ganti ke drone", atau "model apa saja".')
        else:
            self._note("Belum ada model 3D. Jalankan: python tools/make_placeholder_models.py")
        self.camera_link.start(self._no_camera)
        self.voice_link.start()
        self.poller = Poller(self._probe, float(self.cfg.get("network.check_interval_s", 8)), self)
        self.poller.result.connect(self._on_status)
        self.poller.start()

    def shutdown(self) -> None:
        if self.poller:
            self.poller.stop()
        self.camera_link.stop()
        self.voice_link.shutdown()
        for worker in self._workers:
            stop_thread(worker, 1500)

    def _build_router(self) -> Router:
        off, on = self.cfg.section("offline"), self.cfg.section("online")
        timeout = float(on.get("timeout_s", 45))
        key = self.cfg.secret("GEMINI_API_KEY")
        gemini = GeminiProvider(key, bool(on.get("use_search", True)), timeout,
                                float(on.get("min_interval_s", 4.0)), float(on.get("cooldown_s", 90.0)))
        targets = [OnlineTarget(gemini, m, bool(key), True) for m in on.get("gemini_models", [])]
        for fb in on.get("fallback", []):
            fb_key = self.cfg.secret(fb.get("key_env", ""))
            if fb.get("enabled"):
                prov = OpenAICompatProvider(fb["name"], fb["base_url"], fb_key, bool(fb.get("vision")), timeout)
                targets.append(OnlineTarget(prov, fb["model"], bool(fb_key), bool(fb.get("vision"))))
        return Router(
            OllamaProvider(str(off.get("host", "")), float(off.get("timeout_s", 120))), targets,
            mode=str(self.cfg.get("app.mode")), offline_choice=str(off.get("model", "auto")),
            reserve_gb=float(off.get("reserve_ram_gb", 2.0)),
        )

    # ------------------------------------------------------------------ ViewPort (dipakai ActionRunner)
    def zoom_in(self) -> None:
        self.viewCommand.emit("zoom", str(self.cfg.get("viewer.zoom_step", 1.35)))

    def zoom_out(self) -> None:
        self.viewCommand.emit("zoom", str(1.0 / float(self.cfg.get("viewer.zoom_step", 1.35))))

    def rotate(self, direction: str) -> None:
        self.viewCommand.emit("rotate", direction)

    def spin(self, yaw: float, pitch: float = 0.0) -> None:
        self.viewCommand.emit("spin", f"{yaw},{pitch}")

    def show_model(self, entry) -> None:
        self._load_entry(entry)

    def _load_entry(self, entry) -> None:
        self._current = entry
        self._set("shapeName", entry.name)
        self._set("modelSource", QUrl.fromLocalFile(str(self.registry.path(entry))).toString())
        self.viewCommand.emit("resetZoom", "")

    @Slot(bool, str)
    def modelStatus(self, ok: bool, error: str) -> None:
        if not ok:
            self._note(f"Model gagal dimuat: {error}")

    # ------------------------------------------------------------------ chat
    def _note(self, text: str) -> None:
        self.messages.append("system", text)

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        text = text.strip()
        if not text or self.get("busy"):
            return
        self.stopSpeaking()
        self.messages.append("user", text)
        self._ask(text)

    def _ask(self, text: str) -> None:
        self._lang = lang.detect(text, self._lang)         # balasan dan suara mengikuti bahasa yang ditulis
        self._set("busy", True)
        self._history = (self._history + [Turn("user", text)])[-12:]
        online = self.router.mode == "online"
        guessed = intent.guess(text)
        if not online and self.cfg.get("offline.fast_commands", True) and guessed and intent.is_light(text):
            self._set("busy", False)                       # zoom, putar, ganti model: langsung, tanpa menunggu model
            self._apply(guessed, text)
            return
        light = online and intent.is_light(text)
        if light and guessed and not self.router.ollama_ready():
            self._set("busy", False)                       # perintah ringan tanpa model lokal: kata kunci saja
            self._apply(guessed, text)
        elif online and not light and self.cfg.get("online.attach_snapshot"):
            self._snap_token += 1
            path = str(Path(tempfile.gettempdir()) / f"hologram_snap_{os.getpid()}.png")
            self._snap = (self._snap_token, text, path)
            self.snapshotRequested.emit(path)
            token = self._snap_token
            QTimer.singleShot(2500, lambda: self._snapshot_done(token, False))
        else:
            self._dispatch(text, None, light)

    @Slot(bool)
    def snapshotSaved(self, ok: bool) -> None:
        if self._snap:
            self._snapshot_done(self._snap[0], ok)

    def _snapshot_done(self, token: int, ok: bool) -> None:
        if not self._snap or self._snap[0] != token:
            return
        _, text, path = self._snap
        self._snap = None
        image = None
        if ok:
            try:
                image = Path(path).read_bytes()
                Path(path).unlink(missing_ok=True)
            except OSError:
                image = None
        self._dispatch(text, image, False)

    def _dispatch(self, text: str, image: bytes | None, light: bool) -> None:
        self._workers = [w for w in self._workers if w.isRunning()]
        worker = AskWorker(self.router, self._system, list(self._history), image, light, text, self)
        worker.done.connect(self._on_reply)
        self._workers.append(worker)
        worker.start()

    def _system(self, online: bool) -> str:
        if not online:                                     # offline: ringkas saja, model kecil di CPU peka panjang prompt
            names = ", ".join(e.name for e in self.registry.all())
            return prompts.build_system(names, self._current.name if self._current else "", False, self._lang)
        models = "\n".join(f"- {e.summary()}" for e in self.registry.all())
        return prompts.build_system(models, self._current.summary() if self._current else "", online, self._lang)

    @Slot(object)
    def _on_reply(self, payload) -> None:
        user_text, result = payload
        self._set("busy", False)
        if isinstance(result, Exception):
            reason = str(result) if isinstance(result, AllFailed) else f"Terjadi kesalahan: {result}"
            self._note(reason)
            guessed = intent.guess(user_text)
            if guessed:                                     # AI tidak terjangkau, tapi perintah sederhana tetap jalan
                self._apply(guessed, user_text)
            self._sync_router()
            return
        for note in result.notes:
            self._note(note)
        self._sync_router()
        cmd = parse_command(result.text)
        guessed = intent.guess(user_text)
        if cmd is None:
            cmd = guessed or Command("reply", reply=result.text.strip())
        elif cmd.action == "reply" and guessed and guessed.action in intent.LIGHT:
            cmd = guessed                                   # model kecil lupa menyertakan aksi
        self._apply(cmd, user_text)

    def _apply(self, cmd: Command, user_text: str) -> None:
        res = self.runner.run(cmd, self._lang)
        text = res.text
        if res.switch_mode:
            before = self.router.mode
            ok, msg = self.router.set_mode(res.switch_mode)
            self._sync_router()
            if not ok:
                self._say(Command("reply"), msg)
                return
            switched = f"Switched to {res.switch_mode} mode." if self._lang == "en" else f"Pindah ke mode {res.switch_mode}."
            self._say(cmd, text or switched)
            if res.resend and before != self.router.mode:
                self._ask(user_text)
            return
        self._say(cmd, text)

    def _say(self, cmd: Command, text: str) -> None:
        if not text:
            return
        record = json.dumps({"action": cmd.action, "args": cmd.args, "reply": text}, ensure_ascii=False)
        self._history = (self._history + [Turn("assistant", record)])[-12:]
        if self.voice_link.enabled:
            self._pending.append(text)                     # ditampilkan begitu textReady dipancarkan Speaker
            self._set("busy", True)
            self.voice_link.say(text, lang.detect(text, self._lang))   # suara mengikuti bahasa balasan
            QTimer.singleShot(1200, self._flush_pending)    # jaring pengaman saja: harusnya textReady sudah lebih cepat
        else:
            self.messages.append("ai", text)

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        for text in self._pending:
            self.messages.append("ai", text)
        self._pending.clear()
        self._set("busy", False)

    # ------------------------------------------------------------------ suara
    @Slot()
    def toggleVoice(self) -> None:
        """Tombol speaker: hanya mematikan/menghidupkan suara AI. Mikrofon tetap bisa dipakai."""
        self.voice_link.set_tts_enabled(not self.get("voiceEnabled"))

    @Slot()
    def toggleMic(self) -> None:
        self.voice_link.toggle_mic()

    @Slot()
    def toggleCamera(self) -> None:
        self.camera_link.set_enabled(not self.get("cameraOn"))

    @Slot()
    def stopSpeaking(self) -> None:
        self._flush_pending()
        self.voice_link.stop_speaking()

    # ------------------------------------------------------------------ mode dan model AI
    @Slot(str)
    def setMode(self, mode: str) -> None:
        ok, msg = self.router.set_mode(mode)
        self._sync_router()
        self._note(f"Mode {mode}. AI: {self.router.info()}" if ok else msg)
        if ok and self.router.model_warning():
            self._note(self.router.model_warning())

    def _warm_up(self) -> None:
        """Muat model Ollama yang akan dipakai di latar belakang, sekali per model."""
        info = self.router.info()
        model = info[len("Ollama/"):] if info.startswith("Ollama/") else ""
        if model and model not in self._warmed:
            self._warmed.add(model)
            threading.Thread(target=self.router.ollama.warm_up, args=(model,), daemon=True).start()

    @Slot(str)
    def selectOption(self, option_id: str) -> None:
        if self.router.select(option_id):
            self._sync_router()
            self._warm_up()
            self._note(f"AI: {self.router.info()}")
            if self.router.model_warning():
                self._note(self.router.model_warning())

    @Slot()
    def refreshOptions(self) -> None:
        if self.poller:
            self.poller.refresh()

    def _sync_router(self) -> None:
        r = self.router
        self._set("mode", r.mode)
        self._set("netOnline", r.net)
        self._set("aiInfo", r.info())
        self._set("options", r.options())
        self._set("optionHeader", r.header())
        self._set("selectedOption", r.selected())
        self._set("dropdownAvailable", r.dropdown_available())

    def _probe(self) -> dict:
        net = has_internet()
        try:
            ollama = self.router.ollama.list_models()
        except Exception as exc:
            ollama = str(exc)
        return {"net": net, "ollama": ollama, "device": device.snapshot()}

    @Slot(object)
    def _on_status(self, result) -> None:
        if isinstance(result, Exception):
            return
        for note in self.router.update_status(result["net"], result["ollama"], result["device"]):
            self._note(note)
        self._set("ramText", device.ram_text(result["device"]))
        error = self.router.ollama_error
        if error != self._ollama_err:
            if error:
                self._note(error)
            elif self._ollama_err is not None:
                self._note(f"Ollama tersambung. {len(self.router.ollama_models)} model tersedia.")
            self._ollama_err = error
        self._sync_router()
        self._warm_up()