"""Provider OpenRouter (format OpenAI-compatible) untuk Mode AI - alternatif Gemini, model gratis
pilihan sendiri (mis. "google/gemma-3-27b-it:free"). Dipakai lewat REST langsung dengan `httpx`,
bukan package `openai`, supaya konsisten dengan gemini_provider.py dan tidak nambah dependency baru
(endpoint OpenRouter sendiri memang cuma JSON REST biasa, format yang sama dipakai banyak SDK).
"""
from __future__ import annotations

import time

import httpx

from .base import ProviderError, Provider, Turn

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(Provider):
    name = "OpenRouter"

    def __init__(self, api_key: str, timeout: float = 45.0, min_interval_s: float = 2.0,
                 max_output_tokens: int = 2048) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.min_interval_s = min_interval_s
        self.max_output_tokens = max_output_tokens
        self._last_call = 0.0
        self.total_prompt_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0

    def _space_out(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def generate(self, model: str, system: str, history: list[Turn], image: bytes | None = None) -> str:
        if not self.api_key:
            raise ProviderError("Kunci OpenRouter belum diisi. Isi OPENROUTER_API_KEY di file .env.")
        self._space_out()
        messages = [{"role": "system", "content": system}]
        messages += [{"role": "user" if t.role == "user" else "assistant", "content": t.text} for t in history]
        body = {"model": model, "messages": messages, "max_tokens": self.max_output_tokens}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = httpx.post(API_URL, headers=headers, json=body, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError("OpenRouter tidak merespons (timeout).") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gagal menghubungi OpenRouter: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(self._explain_error(resp), status=resp.status_code)
        data = resp.json()
        usage = data.get("usage") or {}
        self.total_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.total_output_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.request_count += 1
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenRouter tidak mengembalikan jawaban (format respons tidak dikenal).") from exc

    @staticmethod
    def _explain_error(resp: httpx.Response) -> str:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except Exception:        # noqa: BLE001 - respons bukan JSON valid
            msg = resp.text[:200]
        if resp.status_code == 429:
            return "kuota/rate-limit OpenRouter habis (429), coba lagi nanti"
        if resp.status_code in (401, 403):
            return f"API key OpenRouter ditolak ({resp.status_code}): {msg or 'periksa OPENROUTER_API_KEY'}"
        if resp.status_code == 404:
            return f"model tidak ditemukan di OpenRouter ({msg or 'periksa openrouter_model di config.toml'})"
        return f"HTTP {resp.status_code}: {msg or 'kesalahan tak dikenal'}"