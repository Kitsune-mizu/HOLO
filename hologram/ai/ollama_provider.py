"""AI offline lewat pustaka `ollama` (layanan Ollama di komputer yang sama)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .base import Provider, ProviderError, Turn

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
NO_SERVICE = "Ollama tidak aktif. Jalankan aplikasi Ollama (atau `ollama serve`) lalu coba lagi."


@dataclass(frozen=True)
class OllamaModel:
    name: str
    digest: str
    size: int
    modified: datetime | None


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class OllamaProvider(Provider):
    name = "Ollama"

    def __init__(self, host: str = "", timeout: float = 120.0) -> None:
        self.host = host or None
        self.timeout = timeout

    def _client(self, timeout: float):
        try:
            import ollama
        except ImportError as exc:
            raise ProviderError("Pustaka ollama belum terpasang. Jalankan: pip install -r requirements.txt") from exc
        return ollama.Client(host=self.host, timeout=timeout)

    def list_models(self) -> list[OllamaModel]:
        try:
            resp = self._client(4.0).list()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(NO_SERVICE) from exc
        items = _field(resp, "models", []) or []
        models = [
            OllamaModel(
                name=str(_field(m, "model") or _field(m, "name") or ""),
                digest=str(_field(m, "digest", "")),
                size=int(_field(m, "size", 0) or 0),
                modified=_field(m, "modified_at"),
            )
            for m in items
        ]
        return sorted((m for m in models if m.name), key=lambda m: m.name)

    def warm_up(self, model: str) -> None:
        """Muat model ke memori sebelum pesan pertama, supaya jawaban pertama tidak lambat. Gagal = diabaikan."""
        try:
            self._client(self.timeout).generate(model=model, prompt="", keep_alive="30m")
        except Exception:
            pass

    def generate(self, model: str, system: str, history: list[Turn], image: bytes | None = None) -> str:
        client = self._client(self.timeout)
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t.role, "content": t.text} for t in history]
        kwargs = dict(
            model=model, messages=messages, format="json", keep_alive="30m",
            options={"temperature": 0.2, "num_predict": 160, "num_ctx": 2048},
        )
        try:
            try:
                resp = client.chat(think=False, **kwargs)
            except TypeError:                      # pustaka lama tanpa parameter think
                resp = client.chat(**kwargs)
        except Exception as exc:
            raise self._translate(exc, model) from exc
        content = str(_field(_field(resp, "message", {}), "content", "") or "")
        return _THINK.sub("", content).strip()

    @staticmethod
    def _translate(exc: Exception, model: str) -> ProviderError:
        status = getattr(exc, "status_code", None)
        text = str(exc)
        if status == 404 or "not found" in text.lower():
            return ProviderError(f"Model {model} belum ada. Jalankan: ollama pull {model}", 404)
        if isinstance(exc, ConnectionError) or "connect" in text.lower():
            return ProviderError(NO_SERVICE)
        if "timed out" in text.lower() or "timeout" in text.lower():
            return ProviderError(f"Model {model} terlalu lama menjawab. Coba model yang lebih kecil.")
        return ProviderError(f"Ollama gagal: {text[:160]}", status)