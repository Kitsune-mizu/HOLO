import json
import time
from datetime import datetime, timezone

from PySide6.QtCore import QCoreApplication

from hologram.ai.base import Provider, ProviderError
from hologram.ai.ollama_provider import OllamaModel
from hologram.ai.router import OnlineTarget, Router
from hologram.config import Config
from hologram.core.controller import Controller
from hologram.core.device import GB, DeviceInfo
from hologram.vision.frame_provider import FrameProvider


class Fake(Provider):
    def __init__(self, name, answers=None, error=None):
        self.name, self.answers, self.error, self.calls = name, list(answers or []), error, []

    def generate(self, model, system, history, image=None):
        self.calls.append({"system": system, "history": list(history), "image": image})
        if self.error:
            raise ProviderError(self.error)
        return self.answers.pop(0) if self.answers else json.dumps({"action": "reply", "reply": "ok"})


def make(qapp, ollama, gemini=None, mode="offline", net=True):
    ctl = Controller(Config(), FrameProvider(), no_camera=True, no_voice=True)
    targets = [OnlineTarget(gemini, "g-1", True)] if gemini else []
    ctl.router = Router(ollama, targets, mode=mode)
    model = OllamaModel("qwen2.5:1.5b", "a" * 32, 986 * 10 ** 6, datetime.now(timezone.utc))
    ctl.router.update_status(net, [model], DeviceInfo(16 * GB, 8 * GB))
    ctl._sync_router()
    ctl._load_entry(ctl.registry.get("pyramid"))
    ctl.events = []
    ctl.viewCommand.connect(lambda name, arg: ctl.events.append((name, arg)))
    return ctl


def settle(ctl, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if not ctl.get("busy") and all(not w.isRunning() for w in ctl._workers):
            QCoreApplication.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("permintaan tidak selesai")


def texts(ctl, kind):
    m = ctl.messages
    return [m.data(m.index(i), m.roleNames() and list(m.roleNames())[1]) for i in range(m.rowCount()) if m.data(m.index(i), list(m.roleNames())[0]) == kind]


def test_ai_json_action_drives_the_view(qapp):
    ollama = Fake("Ollama", ['{"action":"zoom_in","args":{},"reply":"Oke, diperbesar."}'])
    ctl = make(qapp, ollama)
    ctl.sendMessage("tolong dekatkan")
    settle(ctl)
    assert ("zoom", "1.35") in ctl.events
    assert texts(ctl, "user") == ["tolong dekatkan"] and texts(ctl, "ai") == ["Oke, diperbesar."]
    assert "Ollama/qwen2.5:1.5b" == ctl.get("aiInfo")


def test_load_model_changes_shape_and_missing_model_lists_options(qapp):
    ollama = Fake("Ollama", ['{"action":"load_model","args":{"name":"drone"},"reply":"Siap."}',
                             '{"action":"load_model","args":{"name":"tank"},"reply":"Siap."}'])
    ctl = make(qapp, ollama)
    ctl.sendMessage("ganti ke drone")
    settle(ctl)
    assert ctl.get("shapeName") == "Drone" and ctl.get("modelSource").endswith("drone.glb")
    ctl.sendMessage("ganti ke tank")
    settle(ctl)
    last = texts(ctl, "ai")[-1]
    assert "tidak ada" in last and "Pyramid" in last and ctl.get("shapeName") == "Drone"


def test_garbled_model_output_falls_back_to_keywords(qapp):
    ollama = Fake("Ollama", ["maaf saya tidak mengerti ~~"])
    ctl = make(qapp, ollama)
    ctl.sendMessage("putar ke kiri")
    settle(ctl)
    assert ("rotate", "left") in ctl.events


def test_model_that_forgets_the_action_is_corrected(qapp):
    ollama = Fake("Ollama", ['{"action":"reply","reply":"Baik, saya perkecil."}'])
    ctl = make(qapp, ollama)
    ctl.sendMessage("perkecil")
    settle(ctl)
    assert any(name == "zoom" and float(arg) < 1 for name, arg in ctl.events)


def test_ollama_down_still_runs_simple_commands_and_explains(qapp):
    ctl = make(qapp, Fake("Ollama", error="x"))
    ctl.router.update_status(True, "Ollama tidak aktif. Jalankan Ollama.", DeviceInfo(16 * GB, 8 * GB))
    ctl.sendMessage("zoom in")
    settle(ctl)
    assert ("zoom", "1.35") in ctl.events
    assert any("Ollama tidak aktif" in t for t in texts(ctl, "system"))


def test_switch_to_online_and_answer_uses_snapshot(qapp):
    ollama = Fake("Ollama", ['{"action":"switch_mode","args":{"mode":"online","answer":true},"reply":"Pindah ke online."}'])
    gemini = Fake("Gemini", ['{"action":"reply","reply":"Ini model 3D drone quadcopter."}'])
    ctl = make(qapp, ollama, gemini)
    shots = []
    ctl.snapshotRequested.connect(shots.append)
    ctl.sendMessage("pakai online dan jelaskan model ini")
    end = time.time() + 5
    while not shots and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    assert ctl.get("mode") == "online" and shots
    ctl.snapshotSaved(False)                       # tangkapan gagal: lanjut tanpa gambar
    settle(ctl)
    assert texts(ctl, "ai") == ["Pindah ke online.", "Ini model 3D drone quadcopter."]
    assert "tangkapan layar" in gemini.calls[0]["system"]
    assert "Sedang tampil: Pyramid" in gemini.calls[0]["system"]


def test_cannot_switch_online_without_internet_and_ai_says_why(qapp):
    ollama = Fake("Ollama", ['{"action":"switch_mode","args":{"mode":"online"},"reply":"Baik."}'])
    ctl = make(qapp, ollama, Fake("Gemini"), net=False)
    ctl.sendMessage("pindah ke mode online")
    settle(ctl)
    assert ctl.get("mode") == "offline" and "internet" in texts(ctl, "ai")[-1].lower()


def test_online_failure_falls_back_and_reports(qapp):
    ollama = Fake("Ollama", ['{"action":"reply","reply":"Jawaban lokal."}'])
    gemini = Fake("Gemini", error="Kuota gratis Gemini habis (429).")
    ctl = make(qapp, ollama, gemini, mode="online")
    ctl.setMode("online")
    ctl.sendMessage("ceritakan tentang pesawat")
    end = time.time() + 5
    while not ctl._snap and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    ctl.snapshotSaved(False)
    settle(ctl)
    assert ctl.get("mode") == "offline" and texts(ctl, "ai") == ["Jawaban lokal."]
    assert any("Pindah ke mode offline" in t for t in texts(ctl, "system"))


def test_history_keeps_assistant_turns_as_json(qapp):
    ollama = Fake("Ollama", ['{"action":"zoom_in","reply":"Oke."}', '{"action":"reply","reply":"Sama-sama."}'])
    ctl = make(qapp, ollama)
    ctl.sendMessage("zoom in"); settle(ctl)
    ctl.sendMessage("terima kasih"); settle(ctl)
    hist = ollama.calls[1]["history"]
    assert [t.role for t in hist] == ["user", "assistant", "user"]
    assert json.loads(hist[1].text)["action"] == "zoom_in"


def test_busy_blocks_double_send(qapp):
    ctl = make(qapp, Fake("Ollama"))
    ctl._set("busy", True)
    ctl.sendMessage("halo")
    assert texts(ctl, "user") == []
