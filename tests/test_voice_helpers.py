import numpy as np

from hologram.voice.level import LevelMeter, rms
from hologram.voice.tts import clean_for_speech, pick_voice


class V:
    def __init__(self, id, name, languages=()):
        self.id, self.name, self.languages = id, name, languages


def test_clean_for_speech_strips_markdown_urls_emoji():
    out = clean_for_speech("**Halo** 😀 lihat https://contoh.id/x `kode`")
    assert out == "Halo lihat tautan kode"


def test_clean_for_speech_truncates_at_sentence():
    text = ("Kalimat pendek nomor satu ini cukup panjang. " * 30).strip()
    out = clean_for_speech(text, limit=300)
    assert len(out) <= 300 and out.endswith(".")


def test_pick_voice_prefers_indonesian():
    voices = [V("en1", "English", [b"en_US"]), V("id1", "Damayanti", [b"id_ID"]), V("x", "Microsoft Andika - Indonesian")]
    assert pick_voice(voices, "id") == "id1"
    assert pick_voice([V("en1", "English", [b"en_US"])], "id") is None
    assert pick_voice([V("w", "Microsoft Andika Desktop - Indonesian")], "id") == "w"


def test_level_meter_rises_fast_and_falls_slow():
    m = LevelMeter()
    loud = np.full(1600, 0.3, dtype="float32")
    for _ in range(3):
        m.push(loud)
    peak = m.value
    assert 0.5 < peak <= 1.0
    m.push(np.zeros(1600, dtype="float32"))
    assert 0.5 * peak < m.value < peak
    assert rms(np.zeros(0)) == 0.0
