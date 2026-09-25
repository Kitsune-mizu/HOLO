from datetime import datetime, timedelta, timezone

import pytest

from hologram.ai.base import Provider, ProviderError, Turn
from hologram.ai.ollama_provider import OllamaModel
from hologram.ai.router import AllFailed, OnlineTarget, Router
from hologram.core.device import DeviceInfo, GB

HISTORY = [Turn("user", "halo")]
BUILD = lambda online: "sys-online" if online else "sys-offline"  # noqa: E731


class Fake(Provider):
    def __init__(self, name, answer="{}", error=None):
        self.name, self.answer, self.error, self.calls = name, answer, error, []

    def generate(self, model, system, history, image=None):
        self.calls.append((model, system, image))
        if self.error:
            raise ProviderError(self.error)
        return self.answer


def models():
    when = datetime.now(timezone.utc) - timedelta(days=2)
    return [
        OllamaModel("llama3.1:8b", "46e0c10c039e" + "0" * 20, int(4.9 * GB), when),
        OllamaModel("qwen2.5:1.5b", "65ec06548149" + "0" * 20, 986 * 10 ** 6, when),
    ]


def router(mode="offline", ollama=None, gemini=None, key=True, ram_gb=16):
    ollama = ollama or Fake("Ollama", '{"action":"reply"}')
    gemini = gemini or Fake("Gemini", '{"action":"reply","reply":"online"}')
    r = Router(ollama, [OnlineTarget(gemini, "gem-1", key)], mode=mode)
    r.update_status(True, models(), DeviceInfo(32 * GB, ram_gb * GB))
    return r, ollama, gemini


def test_auto_picks_largest_safe_model_for_ram():
    r, *_ = router(ram_gb=16)
    assert r.info() == "Ollama/llama3.1:8b"
    r, *_ = router(ram_gb=4)
    assert r.info() == "Ollama/qwen2.5:1.5b"


def test_options_look_like_ollama_list_and_mark_heavy():
    r, *_ = router(ram_gb=4)
    rows = {o["id"]: o for o in r.options()}
    assert rows["qwen2.5:1.5b"]["cells"][:3] == ["qwen2.5:1.5b", "65ec06548149", "986 MB"]
    assert rows["qwen2.5:1.5b"]["cells"][3] == "2 days ago"
    assert rows["llama3.1:8b"]["tag"] == "heavy" and rows["qwen2.5:1.5b"]["tag"] == "ok"


def test_manual_selection_wins_and_warns_when_heavy():
    r, *_ = router(ram_gb=4)
    assert r.select("llama3.1:8b")
    assert r.info() == "Ollama/llama3.1:8b" and "berat" in r.model_warning()
    assert not r.select("tidak-ada")


def test_dropdown_hidden_without_internet():
    r, *_ = router()
    assert r.dropdown_available()
    r.update_status(False, models(), DeviceInfo(32 * GB, 16 * GB))
    assert not r.dropdown_available() and r.info().startswith("Ollama/")


def test_offline_ask_uses_ollama_only():
    r, ollama, gemini = router()
    reply = r.ask(BUILD, HISTORY)
    assert reply.mode == "offline" and ollama.calls and not gemini.calls
    assert ollama.calls[0][1] == "sys-offline"


def test_online_ask_sends_image_and_online_prompt():
    r, ollama, gemini = router(mode="online")
    reply = r.ask(BUILD, HISTORY, image=b"png")
    assert reply.mode == "online" and gemini.calls[0][1:] == ("sys-online", b"png")


def test_light_command_in_online_mode_goes_local_first():
    r, ollama, gemini = router(mode="online")
    reply = r.ask(BUILD, HISTORY, light=True)
    assert reply.mode == "offline" and r.mode == "online" and not gemini.calls


def test_online_failure_falls_back_to_offline_and_switches_mode():
    r, ollama, gemini = router(mode="online", gemini=Fake("Gemini", error="Kuota gratis Gemini habis (429)."))
    reply = r.ask(BUILD, HISTORY)
    assert reply.mode == "offline" and r.mode == "offline"
    assert reply.notes and reply.notes[0].startswith("Pindah ke mode offline: kuota")
    assert r.info().startswith("Ollama/")


def test_internet_loss_switches_mode_and_reports():
    r, *_ = router(mode="online")
    notes = r.update_status(False, models(), DeviceInfo(32 * GB, 16 * GB))
    assert r.mode == "offline" and notes and "internet" in notes[0].lower()


def test_set_mode_online_needs_internet_and_key():
    r, *_ = router(key=False)
    ok, why = r.set_mode("online")
    assert not ok and "Kunci" in why
    r, *_ = router()
    r.update_status(False, models(), DeviceInfo(1, 1))
    ok, why = r.set_mode("online")
    assert not ok and "internet" in why.lower()
    r.update_status(True, models(), DeviceInfo(1, 1))
    assert r.set_mode("online")[0] and r.mode == "online"


def test_second_online_provider_is_used_after_first_fails():
    a, b = Fake("Gemini", error="429"), Fake("Groq", '{"action":"reply"}')
    r = Router(Fake("Ollama"), [OnlineTarget(a, "g", True), OnlineTarget(b, "l", True, False)], mode="online")
    r.update_status(True, models(), DeviceInfo(32 * GB, 16 * GB))
    reply = r.ask(BUILD, HISTORY, image=b"png")
    assert reply.provider == "Groq" and b.calls[0][2] is None and r.mode == "online"
    assert reply.notes[0].startswith("Pindah ke Groq/l")


def test_everything_down_raises_readable_error():
    r = Router(Fake("Ollama"), [], mode="offline")
    r.update_status(True, "Ollama tidak aktif. Jalankan Ollama.", DeviceInfo(1, 1))
    with pytest.raises(AllFailed, match="Ollama tidak aktif"):
        r.ask(BUILD, HISTORY)


def _gemini_router(first_error, models_=("m-a", "m-b")):
    class Scripted(Fake):
        def generate(self, model, system, history, image=None):
            self.calls.append((model, system, image))
            if self.error and model == "m-a":
                raise ProviderError(self.error, self.status)
            return '{"action":"reply"}'
    g = Scripted("Gemini", error=first_error[0])
    g.status = first_error[1]
    r = Router(Fake("Ollama", '{"action":"reply"}'), [OnlineTarget(g, m, True) for m in models_], mode="online")
    r.update_status(True, models(), DeviceInfo(32 * GB, 16 * GB))
    return r, g


def test_one_attempt_per_provider_per_message():
    r, g = _gemini_router(("Kuota gratis Gemini habis (429).", 429))
    reply = r.ask(BUILD, HISTORY)
    assert len(g.calls) == 1 and reply.mode == "offline"       # model kedua tidak ikut dicoba


def test_quota_error_pauses_gemini_for_a_minute():
    r, g = _gemini_router(("Kuota gratis Gemini habis (429).", 429))
    r.ask(BUILD, HISTORY)
    ok, why = r.set_mode("online")
    assert not ok and "dibatasi" in why
    r.ask(BUILD, HISTORY)
    assert len(g.calls) == 1                                    # tidak menghantam lagi selama jeda


def test_missing_model_is_skipped_next_time_but_other_model_still_works():
    r, g = _gemini_router(("Model m-a tidak ditemukan.", 404))
    first = r.ask(BUILD, HISTORY)
    assert len(g.calls) == 1 and first.mode == "offline"
    assert r.set_mode("online")[0]
    second = r.ask(BUILD, HISTORY)
    assert [c[0] for c in g.calls] == ["m-a", "m-b"] and second.mode == "online"


def test_online_history_is_trimmed_and_starts_with_user():
    r, g = _gemini_router((None, None))
    long = [Turn("user" if i % 2 == 0 else "assistant", f"t{i}") for i in range(11)]
    r.ask(BUILD, long)
    sent = g.calls[0]
    assert sent[0] == "m-a"
