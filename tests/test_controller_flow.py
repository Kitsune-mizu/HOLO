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
    ctl.sendMessage("tampilannya kurang jelas nih")
    settle(ctl)
    assert ("zoom", "1.35") in ctl.events
    assert texts(ctl, "user") == ["tampilannya kurang jelas nih"] and texts(ctl, "ai") == ["Oke, diperbesar."]
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
    ctl.sendMessage("zoom in")                     # jalur cepat: tidak butuh Ollama
    settle(ctl)
    assert ("zoom", "1.35") in ctl.events
    ctl.sendMessage("ceritakan tentang pesawat")   # butuh model: pesan yang jelas
    settle(ctl)
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
    ctl.sendMessage("tampilannya kurang jelas nih"); settle(ctl)
    ctl.sendMessage("terima kasih"); settle(ctl)
    hist = ollama.calls[1]["history"]
    assert [t.role for t in hist] == ["user", "assistant", "user"]
    assert json.loads(hist[1].text)["action"] == "zoom_in"


def test_busy_blocks_double_send(qapp):
    ctl = make(qapp, Fake("Ollama"))
    ctl._set("busy", True)
    ctl.sendMessage("halo")
    assert texts(ctl, "user") == []


def test_offline_simple_commands_skip_the_model(qapp):
    ollama = Fake("Ollama")
    ctl = make(qapp, ollama)
    for phrase in ("zoom in", "putar ke kanan", "ganti ke drone", "model apa saja"):
        ctl.sendMessage(phrase)
        settle(ctl)
    assert ollama.calls == []                                   # tidak ada satu pun panggilan ke model
    assert ("zoom", "1.35") in ctl.events and ("rotate", "right") in ctl.events
    assert ctl.get("shapeName") == "Drone" and "Model yang tersedia" in texts(ctl, "ai")[-1]


def test_fast_commands_can_be_turned_off(qapp):
    ollama = Fake("Ollama", ['{"action":"zoom_in","reply":"Oke."}'])
    ctl = make(qapp, ollama)
    ctl.cfg.data["offline"]["fast_commands"] = False
    ctl.sendMessage("zoom in")
    settle(ctl)
    assert len(ollama.calls) == 1


def test_offline_prompt_is_compact_and_online_prompt_is_full(qapp):
    ctl = make(qapp, Fake("Ollama"))
    short, full = ctl._system(False), ctl._system(True)
    assert len(short) < len(full) * 0.6 and "Pyramid" in short and "zoom_in" in short


def test_reply_text_waits_for_the_voice_then_appears_together(qapp):
    ctl = make(qapp, Fake("Ollama", ['{"action":"reply","reply":"Halo juga."}']))
    said = []
    ctl.voice_link.speaker = type("S", (), {"stop_speaking": lambda self: None})()   # anggap suara aktif
    ctl.voice_link.say = lambda text, lang="id": said.append(text)
    ctl.sendMessage("kamu siapa sebenarnya")
    end = time.time() + 5
    while not said and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    assert said == ["Halo juga."] and texts(ctl, "ai") == [] and ctl.get("busy")   # teks ditahan
    ctl._flush_pending()                                         # audio mulai diputar
    assert texts(ctl, "ai") == ["Halo juga."] and not ctl.get("busy")
    ctl._flush_pending()                                         # panggilan kedua tidak menggandakan
    assert texts(ctl, "ai") == ["Halo juga."]


def test_stop_speaking_never_loses_held_text(qapp):
    ctl = make(qapp, Fake("Ollama"))
    ctl.voice_link.speaker = type("S", (), {"stop_speaking": lambda self: None})()
    ctl._pending.append("Jawaban tertahan")
    ctl.stopSpeaking()
    assert texts(ctl, "ai") == ["Jawaban tertahan"]


def test_ollama_model_is_warmed_once(qapp):
    ollama = Fake("Ollama")
    warmed = []
    ollama.warm_up = warmed.append
    ctl = make(qapp, ollama)
    ctl._warm_up(); ctl._warm_up()
    time.sleep(0.2)
    assert warmed == ["qwen2.5:1.5b"]


def test_language_is_detected_and_drives_prompt_text_and_voice(qapp):
    ollama = Fake("Ollama", ['{"action":"reply","reply":"This is a pyramid."}'])
    ctl = make(qapp, ollama)
    spoken = []
    ctl.voice_link.speaker = type("S", (), {"stop_speaking": lambda self: None})()
    ctl.voice_link.say = lambda text, lang="id": spoken.append((text, lang))
    ctl.sendMessage("what is this model and can you explain it please")
    end = time.time() + 5
    while not spoken and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    assert "MUST be written in English" in ollama.calls[0]["system"]
    assert spoken == [("This is a pyramid.", "en")]
    ctl._flush_pending()
    ctl.sendMessage("apa ini sebenarnya")
    end = time.time() + 5
    while len(ollama.calls) < 2 and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    assert "WAJIB bahasa Indonesia" in ollama.calls[1]["system"]


def test_builtin_replies_follow_language(qapp):
    ctl = make(qapp, Fake("Ollama"))
    ctl.sendMessage("please show the drone model for me")
    settle(ctl)
    assert texts(ctl, "ai")[-1] == "Showing Drone."
    ctl.sendMessage("tolong ganti ke pyramid dong")
    settle(ctl)
    assert texts(ctl, "ai")[-1] == "Menampilkan Pyramid."


def test_toggle_voice_off_stops_only_speaker_mic_stays_available(qapp):
    ctl = make(qapp, Fake("Ollama", ['{"action":"reply","reply":"Halo."}']))
    stopped = []
    fake_speaker = type("S", (), {"stop_speaking": lambda self: stopped.append("speaker")})()
    fake_listener = type("L", (), {"start_listening": lambda self: stopped.append("mic_started")})()
    ctl.voice_link.speaker = fake_speaker
    ctl.voice_link.listener = fake_listener
    assert ctl.get("voiceEnabled") is True

    ctl.toggleVoice()
    assert ctl.get("voiceEnabled") is False and ctl.voice_link.tts_enabled is False
    assert "speaker" in stopped                                  # ucapan yang sedang jalan dihentikan
    assert ctl.voice_link.speaker is fake_speaker and ctl.voice_link.listener is fake_listener  # objeknya tetap ada

    # mikrofon tetap bisa dipakai walau suara AI mati
    ctl.toggleMic()
    assert "mic_started" in stopped

    # dengan suara mati, jawaban tampil langsung, tidak ditahan menunggu audio
    ctl.sendMessage("halo lagi")
    settle(ctl)
    assert texts(ctl, "ai")[-1] == "Halo."


def test_toggle_voice_on_off_does_not_touch_thread_lifecycle(qapp):
    ctl = make(qapp, Fake("Ollama"))
    ctl.voice_link.speaker = type("S", (), {"stop_speaking": lambda self: None})()
    ctl.voice_link.listener = object()
    ctl.toggleVoice()
    assert ctl.get("voiceEnabled") is False
    assert ctl.voice_link.speaker is not None and ctl.voice_link.listener is not None   # tidak dibongkar
    ctl.toggleVoice()
    assert ctl.get("voiceEnabled") is True


def test_no_voice_flag_means_no_speaker_or_listener_ever_created(qapp):
    ctl = Controller(Config(), FrameProvider(), no_camera=True, no_voice=True)
    assert ctl.voice_link.available is False
    ctl.voice_link.start()
    assert ctl.voice_link.speaker is None and ctl.voice_link.listener is None
    ctl.toggleVoice()                                             # tombol tetap bisa ditekan, tapi tidak berefek nyata
    assert ctl.voice_link.speaker is None
