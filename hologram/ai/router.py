"""Pemilihan model Ollama (lokal) untuk HologramOS. TIDAK ADA mode online di sini sama sekali -
AI online (Gemini) sekarang murni urusan Mode AI (lihat ai/full_session.py), berdiri sendiri lewat
instance yang sama sekali berbeda. HologramOS (tampilan model 3D) HANYA pernah memakai Ollama lokal.
"""
from __future__ import annotations

from typing import Callable

from ..core import device
from .base import ProviderError, Reply, Turn
from .ollama_provider import NO_SERVICE, OllamaModel, OllamaProvider

NO_MODELS = "Belum ada model Ollama. Jalankan misalnya: ollama pull qwen2.5:1.5b"
HEADER = ["NAME", "ID", "SIZE", "MODIFIED"]


class AllFailed(Exception):
    """Ollama gagal menjawab. Pesannya siap ditampilkan."""


class Router:
    def __init__(self, ollama: OllamaProvider, offline_choice: str = "auto", reserve_gb: float = 2.0) -> None:
        self.ollama = ollama
        self.choice = offline_choice
        self.reserve_gb = reserve_gb
        self.mode = "offline"                 # dipertahankan (bukan dihapus) karena QML/state.py masih membacanya
        self.net = False                       # idem - status internet tetap berguna sebagai info, bukan untuk ganti mode
        self.ollama_models: list[OllamaModel] = []
        self.ollama_error = "Ollama belum dicek."
        self.device = device.DeviceInfo(0, 0)
        self._used: str | None = None

    # ------------------------------------------------------------------ status
    def update_status(self, net: bool, ollama: list[OllamaModel] | str, info: device.DeviceInfo) -> list[str]:
        """Terima hasil cek berkala. Tidak ada lagi perpindahan mode otomatis di sini (hanya satu
        mode), jadi tidak pernah mengembalikan catatan - parameternya dipertahankan karena Poller
        dan Controller._on_status memanggilnya dengan bentuk ini."""
        self.net = net
        self.device = info
        if isinstance(ollama, list):
            self.ollama_models = ollama
            self.ollama_error = "" if ollama else NO_MODELS
        else:
            self.ollama_models = []
            self.ollama_error = ollama
        return []

    def ollama_ready(self) -> bool:
        return bool(self.ollama_models)

    # ------------------------------------------------------------------ dropdown
    def dropdown_available(self) -> bool:
        return bool(self.options())

    def header(self) -> list[str]:
        return HEADER

    def options(self) -> list[dict]:
        if not self.ollama_models:
            return []
        rows = [{"id": "auto", "cells": ["Auto", "sesuai RAM", "", ""], "tag": "ok"}]
        for m in self.ollama_models:
            safe = device.is_safe(m.size, self.device, self.reserve_gb)
            rows.append({
                "id": m.name,
                "cells": [m.name, m.digest[:12], device.format_size(m.size), device.humanize_age(m.modified)],
                "tag": "ok" if safe else "heavy",
            })
        return rows

    def selected(self) -> str:
        return self.choice

    def select(self, option_id: str) -> bool:
        if option_id not in {o["id"] for o in self.options()}:
            return False
        self.choice = option_id
        self._used = None
        return True

    def model_warning(self) -> str:
        """Peringatan kalau model yang dipilih berat untuk RAM perangkat."""
        name = self._offline_model()
        model = next((m for m in self.ollama_models if m.name == name), None)
        if model and not device.is_safe(model.size, self.device, self.reserve_gb):
            return f"{model.name} ({device.format_size(model.size)}) berat untuk RAM yang tersedia. Jawaban bisa lambat."
        return ""

    # ------------------------------------------------------------------ pilihan model
    def _offline_model(self) -> str | None:
        names = [m.name for m in self.ollama_models]
        if not names:
            return None
        if self.choice != "auto" and self.choice in names:
            return self.choice
        return device.pick_model([(m.name, m.size) for m in self.ollama_models], self.device, self.reserve_gb)

    def info(self) -> str:
        """Teks seperti "Ollama/qwen2.5:1.5b" untuk kartu info."""
        if self._used:
            return self._used
        model = self._offline_model()
        return f"Ollama/{model}" if model else "Ollama (tidak aktif)"

    # ------------------------------------------------------------------ bertanya
    def ask(self, build_system: Callable[[bool], str], history: list[Turn], image: bytes | None = None,
            light: bool = False) -> Reply:
        """Kirim ke Ollama. `image`/`light`/parameter "online" di `build_system` dipertahankan di
        signature supaya AskWorker (workers.py) tidak perlu berubah, meski di sini `image` tidak
        pernah dipakai (Ollama lokal tidak menerima gambar) dan `build_system` selalu dipanggil
        dengan False (tidak ada mode online lagi)."""
        model = self._offline_model()
        if not model:
            raise AllFailed(self.ollama_error or NO_SERVICE)
        try:
            text = self.ollama.generate(model, build_system(False), history, None)
        except ProviderError as exc:
            raise AllFailed(str(exc)) from exc
        self._used = f"Ollama/{model}"
        return Reply(text=text, provider="Ollama", model=model, mode="offline", notes=[])
