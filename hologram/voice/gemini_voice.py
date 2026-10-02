"""Voice Design Gemini (suara kustom dari deskripsi teks, mis. "suara anime ceria") untuk Mode AI.

Dipisah dari `tts_full.py` supaya berdiri sendiri: modul ini murni urusan HTTP ke Gemini Voices API
(`POST /v1beta/voices`) dan sintesis suara (`POST /v1beta/models/{model}:generateContent`,
`responseModalities=["AUDIO"]`). `tts_full.py` yang memanggil `ensure_voice()`/`synthesize()` sebagai
salah satu engine suara, sebagaimana ia juga bisa memakai edge-tts atau suara sistem.

Rujukan resmi: https://ai.google.dev/gemini-api/docs/generate-content/voice-design
                https://ai.google.dev/gemini-api/docs/generate-content/speech-generation
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from ..config import ROOT

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
CACHE_PATH = ROOT / ".cache" / "gemini_voices.json"
DEFAULT_MODEL = "gemini-3.8-flash-tts"


class VoiceDesignError(Exception):
    pass


def _cache_key(prompt: str, gender: str, language_code: str, model: str) -> str:
    raw = f"{model}|{gender}|{language_code}|{prompt.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:            # noqa: BLE001 - belum ada cache, atau rusak: mulai dari kosong saja
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:            # noqa: BLE001 - gagal simpan cache bukan alasan untuk gagal total
        pass


class GeminiVoiceDesigner:
    """Satu instance per API key. `ensure_voice()` cukup dipanggil sekali per persona - hasilnya
    (voice_id) di-cache ke disk, dipanggil ulang setiap start tanpa membuat persona baru terus."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 45.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def ensure_voice(self, prompt: str, display_name: str = "Custom Voice",
                      gender: str = "female", language_code: str = "id-ID") -> str:
        """Kembalikan voice_id untuk deskripsi `prompt` ini - dari cache kalau sudah pernah dibuat,
        atau membuat baru lewat Voice Design (`POST /v1beta/voices`, type="prompted") kalau belum."""
        if not self.api_key:
            raise VoiceDesignError("Kunci Gemini belum diisi (GEMINI_API_KEY).")
        prompt = (prompt or "").strip()
        if not prompt:
            raise VoiceDesignError("Deskripsi suara (gemini_voice_prompt) masih kosong.")

        key = _cache_key(prompt, gender, language_code, self.model)
        cache = _load_cache()
        cached = cache.get(key)
        if cached and cached.get("voice_id"):
            return cached["voice_id"]

        body = {
            "store": True,
            "voice": {
                "model": self.model,
                "type": "prompted",
                "display_name": display_name,
                "gender": gender,
                "language_code": language_code,
                "prompted": {"input": prompt},
            },
        }
        try:
            resp = httpx.post(f"{API_ROOT}/voices", headers=self._headers(), json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise VoiceDesignError(f"Gagal menghubungi Gemini Voice Design: {exc}") from exc
        if resp.status_code >= 400:
            raise VoiceDesignError(self._explain_error(resp))
        data = resp.json()
        voice_id = data.get("id") or data.get("name")
        if not voice_id:
            raise VoiceDesignError("Gemini Voice Design tidak mengembalikan voice_id.")

        cache[key] = {"voice_id": voice_id, "prompt": prompt, "display_name": display_name}
        _save_cache(cache)
        return voice_id

    def synthesize(self, text: str, voice_id: str, style: str = "") -> bytes:
        """Sintesis `text` dengan `voice_id` (dari `ensure_voice`), kembalikan bytes WAV lengkap
        (RIFF header, 24kHz mono 16-bit - permintaan unary Gemini 3.8 TTS memang begitu defaultnya,
        jadi bisa langsung ditulis ke file .wav tanpa perlu dibungkus manual)."""
        if not self.api_key:
            raise VoiceDesignError("Kunci Gemini belum diisi (GEMINI_API_KEY).")
        part: dict = {"text": text}
        if style:
            part["speech_metadata"] = {"style": style}
        body = {
            "contents": [{"role": "user", "parts": [part]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"voice": voice_id}},
            },
        }
        url = f"{API_ROOT}/models/{self.model}:generateContent"
        try:
            resp = httpx.post(url, headers=self._headers(), json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise VoiceDesignError(f"Gagal menghubungi Gemini TTS: {exc}") from exc
        if resp.status_code >= 400:
            raise VoiceDesignError(self._explain_error(resp))
        data = resp.json()
        try:
            b64 = data["candidates"][0]["content"]["parts"][0]["inline_data"]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VoiceDesignError("Gemini TTS tidak mengembalikan audio (format respons tidak dikenal).") from exc
        import base64
        return base64.b64decode(b64)

    @staticmethod
    def _explain_error(resp: httpx.Response) -> str:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except Exception:        # noqa: BLE001 - respons bukan JSON valid
            msg = resp.text[:200]
        if resp.status_code == 429:
            return "kuota Gemini TTS habis (429), coba lagi nanti"
        if resp.status_code in (401, 403):
            return f"API key Gemini ditolak ({resp.status_code}): {msg or 'periksa GEMINI_API_KEY'}"
        return f"HTTP {resp.status_code}: {msg or 'kesalahan tak dikenal'}"