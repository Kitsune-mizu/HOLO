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


def test_edge_voice_is_used_and_mp3_decodes(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="edge", tts_voice="id-ID-GadisNeural")
    out = sp._synthesize("Halo dunia", tmp_path / "x")
    assert out.suffix == ".mp3" and calls == [("Halo dunia", "id-ID-GadisNeural", "+0%")]
    data, rate = sf.read(str(out), dtype="float32", always_2d=True)
    assert rate == 24000 and len(data) > 20000


def test_edge_failure_falls_back_to_system_and_skips_edge_for_a_while(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch, fail=True)
    sp = make_speaker(qapp, tts_engine="edge")
    used = []
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": used.append(path) or path)
    monkeypatch.setattr(ttsmod.time, "sleep", lambda s: None)
    assert sp._synthesize("satu", tmp_path / "x").suffix == ".wav"
    assert sp._synthesize("dua", tmp_path / "x").suffix == ".wav"
    assert len(calls) == 2 and len(used) == 2          # dicoba dua kali untuk pesan pertama, lalu dilewati


def test_system_engine_never_touches_edge(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="system")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": path)
    sp._synthesize("halo", tmp_path / "x")
    assert calls == []


def test_edge_voice_follows_language(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    sp = make_speaker(qapp, tts_engine="edge", tts_voice="id-ID-GadisNeural", tts_voice_en="en-US-JennyNeural")
    sp._synthesize("Halo", tmp_path / "a", "id")
    sp._synthesize("Hello there", tmp_path / "b", "en")
    assert [c[1] for c in calls] == ["id-ID-GadisNeural", "en-US-JennyNeural"]


def test_offline_skips_edge_entirely_and_uses_short_cooldown(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: False))
    used = []
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": used.append(path) or path)
    assert sp._synthesize("halo", tmp_path / "x").suffix == ".wav"
    assert calls == [] and len(used) == 1                         # edge tidak disentuh sama sekali
    assert 0 < sp._edge_down_until - time.monotonic() <= 4         # istirahat pendek, bukan 12 detik


def test_online_but_edge_fails_uses_normal_longer_cooldown(qapp, monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch, fail=True)
    monkeypatch.setattr(ttsmod.Speaker, "_network_ok", staticmethod(lambda: True))
    monkeypatch.setattr(ttsmod.time, "sleep", lambda s: None)
    used = []
    sp = make_speaker(qapp, tts_engine="edge")
    monkeypatch.setattr(sp, "_synth_system", lambda text, path, lang="id": used.append(path) or path)
    assert sp._synthesize("halo", tmp_path / "x").suffix == ".wav"
    assert len(calls) == 2 and len(used) == 1                      # dicoba dua kali dulu (koneksi ada, edge yang gagal)
    assert 8 < sp._edge_down_until - time.monotonic() <= 12


def test_system_voice_follows_language(qapp, monkeypatch, tmp_path):
    chosen = []

    class Engine:
        def setProperty(self, k, v):
            if k == "voice": chosen.append(v)
        def getProperty(self, k):
            V = type("V", (), {})
            a, b = V(), V()
            a.id, a.name, a.languages = "david", "Microsoft David - English (United States)", ["en-US"]
            b.id, b.name, b.languages = "andika", "Microsoft Andika - Indonesian", ["id-ID"]
            return [a, b]
        def save_to_file(self, text, path):
            open(path, "wb").write(b"x" * 200)
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system", tts_language="id")
    sp._synth_system("Halo", tmp_path / "a.wav", "id")
    sp._synth_system("Hello", tmp_path / "b.wav", "en")
    assert chosen == ["andika", "david"]


def test_edge_gets_a_second_try_before_falling_back(qapp, monkeypatch, tmp_path):
    attempts = []

    class Communicate:
        def __init__(self, text, voice, rate="+0%"):
            attempts.append(1)

        async def save(self, path):
            if len(attempts) == 1:
                raise ConnectionError("putus sesaat")
            sf.write(path, np.zeros(24000, dtype="float32") + 0.1, 24000, format="MP3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    monkeypatch.setattr(ttsmod.time, "sleep", lambda s: None)
    sp = make_speaker(qapp, tts_engine="edge")
    assert sp._synthesize("halo", tmp_path / "x").suffix == ".mp3" and len(attempts) == 2


def test_never_reads_indonesian_with_an_english_only_voice(qapp, monkeypatch, tmp_path):
    class Engine:
        def setProperty(self, k, v): pass
        def getProperty(self, k):
            V = type("V", (), {})
            v = V(); v.id, v.name, v.languages = "zira", "Microsoft Zira - English (United States)", ["en-US"]
            return [v]
        def save_to_file(self, text, path): raise AssertionError("tidak boleh bicara")
        def runAndWait(self): pass
        def stop(self): pass

    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=lambda: Engine()))
    sp = make_speaker(qapp, tts_engine="system", tts_language="id")
    with pytest.raises(RuntimeError, match="tidak punya suara"):
        sp._synth_system("Halo", tmp_path / "a.wav", "id")
    sp._cfg["tts_allow_foreign_voice"] = True
    with pytest.raises(AssertionError):                          # kalau diizinkan, ia lanjut bicara
        sp._synth_system("Halo", tmp_path / "a.wav", "id")


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
