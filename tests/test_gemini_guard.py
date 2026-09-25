import httpx
import pytest

from hologram.ai import gemini_provider as gp
from hologram.ai.base import ProviderError, Turn

OK = {"candidates": [{"content": {"parts": [{"text": '{"action":"reply","reply":"hai"}'}]}}]}


class Recorder:
    """Pengganti httpx.post: mengembalikan respons berurutan dan menghitung permintaan."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append(json)
        status, body, hdr = self.responses.pop(0) if self.responses else (200, OK, {})
        return httpx.Response(status, json=body, headers=hdr, request=httpx.Request("POST", url))


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(gp.time, "sleep", lambda s: None)
    return gp.GeminiProvider("k", use_search=True, min_interval_s=0)


def ask(p, model="m"):
    return p.generate(model, "sys", [Turn("user", "halo")])


def test_429_pauses_model_and_sends_no_more_requests(provider, monkeypatch):
    rec = Recorder((429, {"error": {"message": "quota"}}, {"retry-after": "30"}))
    monkeypatch.setattr(gp.httpx, "post", rec)
    with pytest.raises(ProviderError, match="429"):
        ask(provider)
    for _ in range(5):
        with pytest.raises(ProviderError, match="dijeda"):
            ask(provider)
    assert len(rec.calls) == 1                      # hanya satu permintaan ke Google


def test_404_blocks_model_but_other_model_still_works(provider, monkeypatch):
    rec = Recorder((404, {"error": {"message": "nf"}}, {}))
    monkeypatch.setattr(gp.httpx, "post", rec)
    with pytest.raises(ProviderError, match="tidak ditemukan"):
        ask(provider, "salah")
    with pytest.raises(ProviderError, match="nama model tidak ada"):
        ask(provider, "salah")
    assert "hai" in ask(provider, "benar")
    assert len(rec.calls) == 2


def test_400_on_search_retries_once_then_remembers(provider, monkeypatch):
    rec = Recorder((400, {"error": {"message": "tools"}}, {}))
    monkeypatch.setattr(gp.httpx, "post", rec)
    ask(provider)
    ask(provider)
    assert len(rec.calls) == 3                      # 2 untuk pesan pertama, 1 untuk kedua
    assert "tools" in rec.calls[0] and "tools" not in rec.calls[1] and "tools" not in rec.calls[2]


def test_requests_are_spaced_out(monkeypatch):
    slept = []
    monkeypatch.setattr(gp.time, "sleep", slept.append)
    monkeypatch.setattr(gp.httpx, "post", Recorder())
    p = gp.GeminiProvider("k", min_interval_s=4.0)
    ask(p)
    ask(p)
    assert slept and 0 < slept[0] <= 4.0


def test_missing_key_never_calls_google(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(gp.httpx, "post", rec)
    with pytest.raises(ProviderError, match="belum diisi"):
        ask(gp.GeminiProvider(""))
    assert rec.calls == []
