from types import SimpleNamespace

from hologram.core import intent
from hologram.core.actions import ActionRunner, Command, parse_command


def test_parse_clean_json():
    c = parse_command('{"action": "zoom_in", "args": {}, "reply": "Oke."}')
    assert c.action == "zoom_in" and c.reply == "Oke."


def test_parse_json_inside_text_and_fence():
    c = parse_command('Tentu!\n```json\n{"action":"load_model","args":{"name":"drone"},"reply":"Siap"}\n```')
    assert c.action == "load_model" and c.args["name"] == "drone"


def test_parse_strips_think_and_flat_args():
    c = parse_command('<think>{"x":1}</think>{"action":"rotate","direction":"kanan"}')
    assert c.action == "rotate" and c.args["direction"] == "right"


def test_parse_unknown_action_with_reply_becomes_reply():
    c = parse_command('{"action":"dance","reply":"Halo"}')
    assert c.action == "reply" and c.reply == "Halo"


def test_parse_garbage_returns_none():
    assert parse_command("bukan json") is None
    assert parse_command('{"action": ') is None


def test_intent_zoom_rotate_load_list():
    assert intent.guess("zoom in").action == "zoom_in"
    assert intent.guess("tolong perkecil sedikit").action == "zoom_out"
    c = intent.guess("putar ke kiri")
    assert c.action == "rotate" and c.args["direction"] == "left"
    c = intent.guess("ganti ke drone")
    assert c.action == "load_model" and c.args["name"] == "drone"
    assert intent.guess("model apa saja yang tersedia?").action == "list_models"


def test_intent_mode_switch():
    c = intent.guess("pindah ke mode online")
    assert c.action == "switch_mode" and c.args == {"mode": "online", "answer": False}
    c = intent.guess("pakai online dan jelaskan pesawat ini")
    assert c.args["mode"] == "online" and c.args["answer"] is True
    assert intent.guess("ganti ke offline").args["mode"] == "offline"


def test_intent_ignores_questions_and_chatter():
    assert intent.guess("apa itu zoom in?") is None
    assert intent.guess("halo apa kabar") is None
    assert intent.guess("") is None
    assert intent.is_light("zoom out") and not intent.is_light("ceritakan sejarah pesawat")


class FakeView:
    def __init__(self):
        self.calls = []

    def zoom_in(self): self.calls.append("in")
    def zoom_out(self): self.calls.append("out")
    def rotate(self, d): self.calls.append(("rot", d))
    def show_model(self, e): self.calls.append(("show", e.id))


class FakeRegistry:
    def find(self, q):
        return SimpleNamespace(id="drone", name="Drone") if "drone" in q else None

    def names(self):
        return ["Pyramid", "Drone"]


def test_runner_actions():
    view = FakeView()
    runner = ActionRunner(FakeRegistry(), view)
    assert runner.run(Command("zoom_in")).text == "Zoom in."
    assert runner.run(Command("load_model", {"name": "drone"})).text == "Menampilkan Drone."
    missing = runner.run(Command("load_model", {"name": "tank"}))
    assert "tidak ada" in missing.text and "Pyramid, Drone" in missing.text
    assert "Pyramid, Drone" in runner.run(Command("list_models")).text
    sw = runner.run(Command("switch_mode", {"mode": "online", "answer": True}))
    assert sw.switch_mode == "online" and sw.resend
    assert view.calls == ["in", ("show", "drone")]
