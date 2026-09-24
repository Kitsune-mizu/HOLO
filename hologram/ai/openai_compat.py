"""Penyedia online berformat OpenAI (Groq, OpenRouter, Mistral, Cerebras): satu kelas, alamat dan kunci beda."""
from __future__ import annotations

import base64

import httpx

from .base import Provider, ProviderError, Turn


class OpenAICompatProvider(Provider):
    def __init__(self, name: str, base_url: str, api_key: str, vision: bool = False, timeout: float = 45.0) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.vision = vision
        self.timeout = timeout

    def generate(self, model: str, system: str, history: list[Turn], image: bytes | None = None) -> str:
        messages: list[dict] = [{"role": "system", "content": system}]
        for i, turn in enumerate(history):
            content: object = turn.text
            if image and self.vision and i == len(history) - 1 and turn.role == "user":
                url = "data:image/png;base64," + base64.b64encode(image).decode()
                content = [{"type": "text", "text": turn.text}, {"type": "image_url", "image_url": {"url": url}}]
            messages.append({"role": turn.role, "content": content})
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": model, "messages": messages, "max_tokens": 600, "temperature": 0.2},
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} terlalu lama menjawab.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Tidak bisa menghubungi {self.name}.") from exc
        if resp.status_code == 429:
            raise ProviderError(f"Kuota {self.name} habis (429).", 429)
        if resp.status_code != 200:
            raise ProviderError(f"{self.name} error {resp.status_code}.", resp.status_code)
        try:
            return str(resp.json()["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"Jawaban {self.name} tidak terbaca.") from exc
