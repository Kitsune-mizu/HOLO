"""AI online: Gemini lewat REST (httpx). Nama model dibaca dari config.toml."""
from __future__ import annotations

import base64
import time

import httpx

from .base import Provider, ProviderError, Turn

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(Provider):
    name = "Gemini"

    def __init__(self, api_key: str, use_search: bool = True, timeout: float = 45.0,
                 min_interval_s: float = 4.0, cooldown_s: float = 90.0) -> None:
        self.api_key = api_key
        self.use_search = use_search
        self.timeout = timeout
        self.min_interval_s = min_interval_s     # jarak minimum antar permintaan ke Google
        self.cooldown_s = cooldown_s             # jeda setelah 429 kalau Google tidak menyebut waktunya
        self._blocked: dict[str, tuple[float, str]] = {}   # model -> (sampai kapan, alasan)
        self._last_call = 0.0
        self._search_ok = True

    def generate(self, model: str, system: str, history: list[Turn], image: bytes | None = None) -> str:
        if not self.api_key:
            raise ProviderError("Kunci Gemini belum diisi. Salin .env.example ke .env lalu isi GEMINI_API_KEY.")
        self._check_blocked(model)                          # sedang dijeda: tidak ada permintaan ke Google
        self._space_out()
        search = self.use_search and self._search_ok
        try:
            data = self._post(model, self._body(system, history, image, search))
        except ProviderError as exc:
            if exc.status == 400 and search:                # model menolak alat pencarian: ulang sekali, lalu ingat
                self._search_ok = False
                self._check_blocked(model)
                data = self._post(model, self._body(system, history, image, False))
            else:
                raise
        return self._text(data)

    def _check_blocked(self, model: str) -> None:
        until, reason = self._blocked.get(model, (0.0, ""))
        left = until - time.monotonic()
        if left > 0:
            raise ProviderError(f"{model} dijeda {int(left) + 1} detik ({reason}). Permintaan tidak dikirim ke Google.")

    def _space_out(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(min(wait, 5.0))
        self._last_call = time.monotonic()

    def _block_after(self, model: str, resp: httpx.Response) -> None:
        """Ingat kegagalan supaya pesan berikutnya tidak menghantam Google lagi."""
        code = resp.status_code
        if code == 429:
            try:
                wait = float(resp.headers.get("retry-after", ""))
            except ValueError:
                wait = self.cooldown_s
            self._blocked[model] = (time.monotonic() + max(wait, 5.0), "kuota habis")
        elif code == 404:
            self._blocked[model] = (time.monotonic() + 3600, "nama model tidak ada, ubah gemini_models di config.toml")
        elif code in (401, 403):
            self._blocked[model] = (time.monotonic() + 600, "kunci ditolak")

    @staticmethod
    def _body(system: str, history: list[Turn], image: bytes | None, search: bool) -> dict:
        contents = [
            {"role": "user" if t.role == "user" else "model", "parts": [{"text": t.text}]}
            for t in history
        ]
        if image and contents and contents[-1]["role"] == "user":
            contents[-1]["parts"].insert(0, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image).decode()}})
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 800},
        }
        if search:
            body["tools"] = [{"google_search": {}}]
        else:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return body

    def _post(self, model: str, body: dict) -> dict:
        try:
            resp = httpx.post(
                f"{BASE}/{model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=body, timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("Gemini terlalu lama menjawab.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Tidak bisa menghubungi Gemini. Cek koneksi internet.") from exc
        if resp.status_code == 200:
            return resp.json()
        self._block_after(model, resp)
        raise self._http_error(resp, model)

    @staticmethod
    def _http_error(resp: httpx.Response, model: str) -> ProviderError:
        code = resp.status_code
        try:
            detail = str(resp.json().get("error", {}).get("message", ""))[:160]
        except ValueError:
            detail = ""
        if code == 429:
            return ProviderError("Kuota gratis Gemini habis (429). Coba lagi nanti.", 429)
        if code in (401, 403):
            return ProviderError("Kunci Gemini ditolak. Cek GEMINI_API_KEY di .env.", code)
        if code == 404:
            return ProviderError(f"Model {model} tidak ditemukan. Ubah gemini_models di config.toml.", 404)
        return ProviderError(f"Gemini error {code}. {detail}".strip(), code)

    @staticmethod
    def _text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini tidak memberi jawaban (mungkin diblokir filter).")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise ProviderError("Jawaban Gemini kosong.")
        return text.strip()