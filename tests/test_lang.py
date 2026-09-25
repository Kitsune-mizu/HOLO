from hologram.core.lang import detect
from hologram.core.actions import ActionRunner, Command


def test_indonesian_and_english_sentences():
    assert detect("tolong jelaskan model ini", "en") == "id"
    assert detect("apa ini sebenarnya") == "id"
    assert detect("what is this model", "id") == "en"
    assert detect("please show me the drone", "id") == "en"
    assert detect("hello", "id") == "en"
    assert detect("thanks", "id") == "en"


def test_ambiguous_text_keeps_previous_language():
    assert detect("zoom in", "id") == "id" and detect("zoom in", "en") == "en"
    assert detect("drone", "en") == "en" and detect("", "id") == "id"
    assert detect("Ini model 3D drone quadcopter dengan empat baling-baling.") == "id"
    assert detect("This is a 3D quadcopter drone with four rotors.", "id") == "en"


class V:
    def zoom_in(self): pass
    def zoom_out(self): pass
    def rotate(self, d): pass
    def show_model(self, e): pass


class R:
    def find(self, q): return None
    def names(self): return ["Pyramid", "Drone"]


def test_action_texts_are_localized():
    runner = ActionRunner(R(), V())
    assert runner.run(Command("zoom_in"), "en").text == "Zooming in."
    assert runner.run(Command("zoom_in"), "id").text == "Zoom in."
    en = runner.run(Command("load_model", {"name": "tank"}), "en").text
    assert en == 'There is no model called "tank". Available models: Pyramid, Drone.'
    assert runner.run(Command("list_models"), "id").text == "Model yang tersedia: Pyramid, Drone."
