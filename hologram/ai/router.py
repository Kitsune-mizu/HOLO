"""Mode Offline / Online, pilihan model, dan urutan cadangan antar penyedia."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core import device
from .base import Provider, ProviderError, Reply, Turn
from .ollama_provider import NO_SERVICE, OllamaModel, OllamaProvider

NO_MODELS = "Belum ada model Ollama. Jalankan misalnya: ollama pull qwen2.5:1.5b"
OFFLINE_HEADER = ["NAME", "ID", "SIZE", "MODIFIED"]
ONLINE_HEADER = ["MODEL", "PENYEDIA", "STATUS", ""]


class AllFailed(Exception):
    """Semua jalur gagal. Pesannya siap ditampilkan."""


@dataclass(frozen=True)
class OnlineTarget:
    provider: Provider
    model: str
    has_key: bool
    vision: bool = True

    @property
    def id(self) -> str:
        return f"{self.provider.name}:{self.model}"


class Router:
    def __init__(self, ollama: OllamaProvider, targets: list[OnlineTarget], mode: str = "offline",
                 offline_choice: str = "auto", reserve_gb: float = 2.0) -> None:
        self.ollama = ollama
        self.targets = targets
        self.mode = mode
        self.choice = {"offline": offline_choice, "online": "auto"}
        self.reserve_gb = reserve_gb
        self.net = False
        self.ollama_models: list[OllamaModel] = []
        self.ollama_error = "Ollama belum dicek."
        self.device = device.DeviceInfo(0, 0)
        self._used: tuple[str, str] | None = None

    # ------------------------------------------------------------------ status
    def update_status(self, net: bool, ollama: list[OllamaModel] | str, info: device.DeviceInfo) -> list[str]:
        """Terima hasil cek berkala. Kembalikan baris info untuk chat (mis. pindah mode otomatis)."""
        self.net = net
        self.device = info
        if isinstance(ollama, list):
            self.ollama_models = ollama
            self.ollama_error = "" if ollama else NO_MODELS
        else:
            self.ollama_models = []
            self.ollama_error = ollama
        notes: list[str] = []
        if self.mode == "online":
            ok, why = self.online_ready()
            if not ok:
                self._set_mode("offline")
                notes.append(f"Pindah ke mode offline: {why[:-1].lower() if why.endswith('.') else why.lower()}.")
        return notes

    def online_ready(self) -> tuple[bool, str]:
        if not self.net:
            return False, "Tidak ada internet."
        if not any(t.has_key for t in self.targets):
            return False, "Kunci Gemini belum diisi. Salin .env.example ke .env lalu isi GEMINI_API_KEY."
        return True, ""

    def ollama_ready(self) -> bool:
        return bool(self.ollama_models)

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self._used = None

    def set_mode(self, mode: str) -> tuple[bool, str]:
        if mode == "online":
            ok, why = self.online_ready()
            if not ok:
                return False, why
        elif mode != "offline":
            return False, "Mode tidak dikenal."
        self._set_mode(mode)
        return True, f"Mode {mode}."

    # ------------------------------------------------------------------ dropdown
    def dropdown_available(self) -> bool:
        return self.net and bool(self.options())

    def header(self) -> list[str]:
        return OFFLINE_HEADER if self.mode == "offline" else ONLINE_HEADER

    def options(self) -> list[dict]:
        if self.mode == "offline":
            return self._offline_options()
        rows = [{"id": "auto", "cells": ["Auto", "semua", "", ""], "tag": "ok"}]
        for t in self.targets:
            rows.append({
                "id": t.id, "cells": [t.model, t.provider.name, "siap" if t.has_key else "tanpa kunci", ""],
                "tag": "ok" if t.has_key else "na",
            })
        return rows

    def _offline_options(self) -> list[dict]:
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
        return self.choice[self.mode]

    def select(self, option_id: str) -> bool:
        if option_id not in {o["id"] for o in self.options()}:
            return False
        self.choice[self.mode] = option_id
        self._used = None
        return True

    def model_warning(self) -> str:
        """Peringatan kalau model offline yang dipilih berat untuk RAM perangkat."""
        if self.mode != "offline":
            return ""
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
        pref = self.choice["offline"]
        if pref != "auto" and pref in names:
            return pref
        return device.pick_model([(m.name, m.size) for m in self.ollama_models], self.device, self.reserve_gb)

    def _online_targets(self) -> list[OnlineTarget]:
        ready = [t for t in self.targets if t.has_key]
        pref = self.choice["online"]
        first = [t for t in ready if t.id == pref]
        return first + [t for t in ready if t.id != pref]

    def info(self) -> str:
        """Teks seperti "Ollama/qwen2.5:1.5b" untuk kartu info."""
        if self._used and self._used[0] == self.mode:
            return self._used[1]
        if self.mode == "offline":
            model = self._offline_model()
            return f"Ollama/{model}" if model else "Ollama (tidak aktif)"
        targets = self._online_targets()
        return f"{targets[0].provider.name}/{targets[0].model}" if targets else "Online (kunci belum diisi)"

    # ------------------------------------------------------------------ bertanya
    def _order(self, light: bool) -> list[tuple[str, Provider, str, bool]]:
        offline_model = self._offline_model()
        offline = [("offline", self.ollama, offline_model, False)] if offline_model else []
        online = [("online", t.provider, t.model, t.vision) for t in self._online_targets()]
        if self.mode == "offline":
            return offline
        return offline + online if light else online + offline

    def ask(self, build_system: Callable[[bool], str], history: list[Turn], image: bytes | None = None,
            light: bool = False) -> Reply:
        """Kirim ke penyedia sesuai mode. Gagal satu, lanjut ke cadangan, dan catat pindahnya."""
        chain = self._order(light)
        if not chain:
            raise AllFailed(self._empty_reason())
        started_mode, problems = self.mode, []
        for kind, provider, model, vision in chain:
            if kind == "online" and not self.net:
                problems.append("internet terputus")
                continue
            try:
                text = provider.generate(model, build_system(kind == "online"), history, image if vision else None)
            except ProviderError as exc:
                problems.append(str(exc))
                continue
            return self._success(kind, provider, model, text, started_mode, problems, light)
        raise AllFailed(" ".join(problems) or self._empty_reason())

    def _success(self, kind, provider, model, text, started_mode, problems, light) -> Reply:
        notes: list[str] = []
        label = f"{provider.name}/{model}"
        if problems and not light:
            reason = problems[-1].rstrip(".")
            if kind == "offline" and started_mode == "online":
                self._set_mode("offline")
                notes.append(f"Pindah ke mode offline: {reason[0].lower() + reason[1:]}.")
            else:
                notes.append(f"Pindah ke {label}: {reason[0].lower() + reason[1:]}.")
        self._used = (self.mode if kind == self.mode else kind, label)
        return Reply(text=text, provider=provider.name, model=model, mode=kind, notes=notes)

    def _empty_reason(self) -> str:
        if self.mode == "offline":
            return self.ollama_error or NO_SERVICE
        ok, why = self.online_ready()
        return why if not ok else "Tidak ada penyedia online yang siap."
