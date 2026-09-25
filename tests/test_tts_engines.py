import sys
import time
import types

import numpy as np
import pytest
import soundfile as sf

from hologram.voice import tts as ttsmod
from hologram.voice.level import LevelMeter


def make_speaker(qapp, **cfg):
    return ttsmod.Speaker(cfg, LevelMeter())


def fake_edge(monkeypatch, fail=False):
    calls = []

    class Communicate:
        def __init__(self, text, voice, rate="+0%"):
            calls.append((text, voice, rate))

        async def save(self, path):
            if fail:
                raise ConnectionError("tidak ada internet")
            sf.write(path, np.sin(np.linspace(0, 200, 24000)).astype("float32") * 0.3, 24000, format="MP3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    return calls


def no_sleep(monkeypatch):
    monkeypatch.setattr(ttsmod.time, "sleep", lambda s: None)
    monkeypatch.setattr(ttsmod.random, "uniform", lambda a, b: 0.0)


def test_edge_voice_is_used_and_mp3_decodes(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="edge", tts_voice="id-ID-GadisNeural")
    out = sp._synthesize("Halo dunia", tmp_path / "x")
    assert out.suffix == ".mp3" and calls == [("Halo dunia", "id-ID-GadisNeural", "+0%")]
    data, rate = sf.read(str(out), dtype="float32", always_2d=True)
    assert rate == 24000 and len(data) > 20000


def test_edge_retries_three_times_with_backoff_before_giving_up(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch, fail=True)
    no_sleep(monkeypatch)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: True))
    used = []
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": used.append(path) or path)
    assert sp._synthesize("halo", tmp_path / "x").suffix == ".wav"
    assert len(calls) == 3 and len(used) == 1                     # dicoba tiga kali dulu, baru menyerah


def test_edge_succeeds_on_second_attempt(qapp, monkeypatch, tmp_path):
    attempts = []

    class Communicate:
        def __init__(self, text, voice, rate="+0%"):
            attempts.append(1)

        async def save(self, path):
            if len(attempts) == 1:
                raise ConnectionError("putus sesaat")
            sf.write(path, np.zeros(24000, dtype="float32") + 0.1, 24000, format="MP3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    no_sleep(monkeypatch)
    sp = make_speaker(qapp, tts_engine="edge")
    out = sp._synthesize("halo", tmp_path / "x")
    assert out.suffix == ".mp3" and len(attempts) == 2
    assert sp._edge_down_until == 0.0 and sp._edge_consecutive_failures == 0


def test_offline_after_edge_fails_gets_short_fixed_cooldown(qapp, monkeypatch, tmp_path):
    fake_edge(monkeypatch, fail=True)
    no_sleep(monkeypatch)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: False))
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": path)
    sp._synthesize("halo", tmp_path / "x")
    assert sp._edge_consecutive_failures == 0                     # bukan salah edge, tidak dihukum backoff
    assert 4.5 < sp._edge_down_until - time.monotonic() <= 5.0


def test_online_but_edge_down_gets_growing_cooldown(qapp, monkeypatch, tmp_path):
    fake_edge(monkeypatch, fail=True)
    no_sleep(monkeypatch)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: True))
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": path)

    sp._synthesize("satu", tmp_path / "a")
    first_cooldown = sp._edge_down_until - time.monotonic()
    assert sp._edge_consecutive_failures == 1 and 3.5 < first_cooldown <= 4.0

    sp._edge_down_until = 0.0                                     # lewati waktu tunggu, supaya bisa coba lagi
    sp._synthesize("dua", tmp_path / "b")
    second_cooldown = sp._edge_down_until - time.monotonic()
    assert sp._edge_consecutive_failures == 2 and second_cooldown > first_cooldown


def test_edge_gives_a_speech_warning_not_a_fatal_error(qapp, monkeypatch, tmp_path):
    fake_edge(monkeypatch, fail=True)
    no_sleep(monkeypatch)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: True))
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": path)
    warnings = []
    sp.speechWarning.connect(warnings.append)
    sp._synthesize("halo", tmp_path / "x")
    assert warnings and "suara sistem" in warnings[0]


def test_system_engine_never_touches_edge(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="system")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": path)
    sp._synthesize("halo", tmp_path / "x")
    assert calls == []


def test_missing_system_voice_falls_back_to_first_available_with_warning(qapp, monkeypatch, tmp_path):
    class Engine:
        def setProperty(self, k, v): pass
        def getProperty(self, k):
            V = type("V", (), {})
            v = V(); v.id, v.name, v.languages = "zira", "Microsoft Zira Desktop - English (United States)", ["en-US"]
            return [v]
        def save_to_file(self, text, path): open(path, "wb").write(b"x" * 200)
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system", tts_language="id")
    warnings = []
    sp.speechWarning.connect(warnings.append)
    out = sp._synth_system("Halo", tmp_path / "a.wav", "id")
    assert out.suffix == ".wav"                                    # tetap bicara, tidak diam
    assert warnings and "Zira" in warnings[0]


def test_no_system_voice_at_all_is_a_real_fatal_error(qapp, monkeypatch, tmp_path):
    class Engine:
        def setProperty(self, k, v): pass
        def getProperty(self, k): return []
        def save_to_file(self, text, path): pass
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system")
    with pytest.raises(RuntimeError, match="tidak ada suara TTS"):
        sp._synth_system("Halo", tmp_path / "a.wav", "id")


def test_system_prefers_configured_name_over_language_search(qapp, monkeypatch, tmp_path):
    class Engine:
        def __init__(self): self.chosen = None
        def setProperty(self, k, v):
            if k == "voice": self.chosen = v
        def getProperty(self, k):
            V = type("V", (), {})
            a, b = V(), V()
            a.id, a.name, a.languages = "id1", "Microsoft Andika - Indonesian", ["id-ID"]
            b.id, b.name, b.languages = "id2", "Damayanti", ["id-ID"]
            return [a, b]
        def save_to_file(self, text, path): open(path, "wb").write(b"x" * 200)
        def runAndWait(self): pass
        def stop(self): pass

    engine = Engine()
    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: engine))
    sp = make_speaker(qapp, tts_system_voice_id="Damayanti")
    sp._synth_system("Halo", tmp_path / "a.wav", "id")
    assert engine.chosen == "id2"


def test_edge_voice_follows_language(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="edge", tts_voice="id-ID-GadisNeural", tts_voice_en="en-US-JennyNeural")
    sp._synthesize("Halo", tmp_path / "a", "id")
    sp._synthesize("Hello there", tmp_path / "b", "en")
    assert [c[1] for c in calls] == ["id-ID-GadisNeural", "en-US-JennyNeural"]


def test_system_voice_follows_language(qapp, monkeypatch, tmp_path):
    chosen = []

    class Engine:
        def setProperty(self, k, v):
            if k == "voice": chosen.append(v)
        def getProperty(self, k):
            V = type("V", (), {})
            a, b = V(), V()
            a.id, a.name, a.languages = "en1", "English", ["en_US"]
            b.id, b.name, b.languages = "id1", "Damayanti", ["id_ID"]
            return [a, b]
        def save_to_file(self, text, path): open(path, "wb").write(b"x" * 200)
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system", tts_language="id")
    sp._synth_system("Halo", tmp_path / "a.wav", "id")
    sp._synth_system("Hello", tmp_path / "b.wav", "en")
    assert chosen == ["id1", "en1"]


def test_system_english_prefers_zira_over_david(qapp, monkeypatch, tmp_path):
    chosen = []

    class Engine:
        def setProperty(self, k, v):
            if k == "voice": chosen.append(v)
        def getProperty(self, k):
            V = type("V", (), {})
            d, z = V(), V()
            d.id, d.name, d.languages = "david", "Microsoft David Desktop - English (United States)", ["en-US"]
            z.id, z.name, z.languages = "zira", "Microsoft Zira Desktop - English (United States)", ["en-US"]
            return [d, z]
        def save_to_file(self, text, path): open(path, "wb").write(b"x" * 200)
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system")
    sp._synth_system("Hello", tmp_path / "a.wav", "en")
    sp._cfg["tts_system_voice_en"] = "David"
    sp._synth_system("Hello", tmp_path / "b.wav", "en")
    assert chosen == ["zira", "david"]


def test_clean_for_speech_strips_markdown_urls_emoji():
    out = ttsmod.clean_for_speech("**Halo** 😀 lihat https://contoh.id/x `kode`")
    assert out == "Halo lihat tautan kode"


def test_clean_for_speech_truncates_at_sentence():
    text = ("Kalimat pendek nomor satu ini cukup panjang. " * 30).strip()
    out = ttsmod.clean_for_speech(text, limit=300)
    assert len(out) <= 300 and out.endswith(".")


def test_pick_voice_prefers_indonesian():
    V = type("V", (), {})

    def voice(id_, name, languages=()):
        v = V(); v.id, v.name, v.languages = id_, name, languages
        return v

    voices = [voice("en1", "English", [b"en_US"]), voice("id1", "Damayanti", [b"id_ID"]),
              voice("x", "Microsoft Andika - Indonesian")]
    assert ttsmod.pick_voice(voices, "id") == "id1"
    assert ttsmod.pick_voice([voice("en1", "English", [b"en_US"])], "id") is None
    assert ttsmod.pick_voice([voice("w", "Microsoft Andika Desktop - Indonesian")], "id") == "w"


def test_level_meter_rises_fast_and_falls_slow():
    m = LevelMeter()
    loud = np.full(1600, 0.3, dtype="float32")
    for _ in range(3):
        m.push(loud)
    peak = m.value
    assert 0.5 < peak <= 1.0
    m.push(np.zeros(1600, dtype="float32"))
    assert 0.5 * peak < m.value < peak
