"""Menampilkan model Gemini yang benar-benar tersedia untuk kunci API kamu.

Memanggil daftar model (bukan generate), jadi tidak memakai kuota permintaan.

    python tools/check_gemini.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("GEMINI_API_KEY belum ada. Isi di file .env dulu.")
        return 1
    try:
        resp = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=20)
    except httpx.HTTPError as exc:
        print(f"Tidak bisa menghubungi Google: {exc}")
        return 1
    if resp.status_code != 200:
        print(f"Galat {resp.status_code}. Kunci ditolak atau salah salin.")
        return 1
    names = sorted(
        m["name"].removeprefix("models/")
        for m in resp.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    )
    print("Model yang bisa dipakai (salin salah satu ke gemini_models di config.toml):\n")
    for n in names:
        if "gemini" in n and not any(x in n for x in ("image", "tts", "embedding", "live", "audio", "robotics")):
            print("  ", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())