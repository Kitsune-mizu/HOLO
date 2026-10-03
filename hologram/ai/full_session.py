"""Sesi percakapan untuk Mode AI (AI Full).

SENGAJA TERPISAH dari `router.py` (punya HologramOS): tidak ada Ollama/offline, tidak ada
`parse_command`/skema aksi JSON, tidak ada `ModelRegistry`. Dua engine online tersedia - Gemini
(Google AI Studio) dan OpenRouter (model gratis pilihan) - dipilih lewat `[ai_full] engine` di
config.toml atau `select_engine()` saat berjalan. Menambah engine lain tinggal menambah satu
Provider baru (lihat openrouter_provider.py sebagai contoh) + satu cabang di `_provider()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import ROOT, Config
from .base import ProviderError, Turn
from .full_prompts import build_system
from .gemini_provider import GeminiProvider
from .openrouter_provider import OpenRouterProvider

HISTORY_PATH = ROOT / ".cache" / "ai_full_history.json"
ENGINES: list[tuple[str, str]] = [("gemini", "Gemini"), ("openrouter", "OpenRouter")]


@dataclass
class FullSession:
    """Satu percakapan AI Full: riwayat sendiri, dua provider siap pakai (Gemini & OpenRouter).
    `ask()` melempar `ProviderError` kalau gagal - pemanggil (`FullLink`) yang menampilkannya ke
    pengguna."""

    cfg: Config
    history: list[Turn] = field(default_factory=list)
    max_turns: int = 30

    def __post_init__(self) -> None:
        if not self.history:
            self.history = self._load_history()
        on = self.cfg.section("online")
        full = self.cfg.section("ai_full")
        max_tokens = int(full.get("max_output_tokens", 2048))   # jauh lebih besar dari 800 punya hologram - balasan boleh panjang

        self._gemini_models = [str(m) for m in (on.get("gemini_models") or ["gemini-2.0-flash"])]
        self._gemini = GeminiProvider(
            self.cfg.secret("GEMINI_API_KEY"),
            use_search=bool(full.get("use_search", on.get("use_search", True))), timeout=float(on.get("timeout_s", 45)),
            min_interval_s=float(on.get("min_interval_s", 4.0)), cooldown_s=float(on.get("cooldown_s", 90.0)),
            max_output_tokens=max_tokens,
            force_json=False,   # Mode AI selalu jawab teks bebas, tidak pernah JSON
        )

        self._openrouter_model = str(full.get("openrouter_model", "google/gemma-3-27b-it:free"))
        self._openrouter = OpenRouterProvider(
            self.cfg.secret("OPENROUTER_API_KEY"),
            timeout=float(on.get("timeout_s", 45)), max_output_tokens=max_tokens,
        )

        self.engine = str(full.get("engine", "gemini"))
        if self.engine not in dict(ENGINES):
            self.engine = "gemini"

    @property
    def engines(self) -> list[tuple[str, str]]:
        return ENGINES

    def select_engine(self, engine_id: str) -> bool:
        if engine_id not in dict(ENGINES):
            return False
        self.engine = engine_id
        return True

    def reset(self) -> None:
        """Hapus riwayat percakapan, termasuk yang tersimpan di disk. HologramOS TIDAK punya ini -
        riwayatnya cuma di memori selama aplikasi jalan (lihat controller.py), sesuai permintaan:
        riwayat + tombol hapus hanya untuk Mode AI."""
        self.history.clear()
        try:
            HISTORY_PATH.unlink(missing_ok=True)
        except Exception:        # noqa: BLE001 - gagal hapus file cache bukan alasan untuk gagal total
            pass

    def ask(self, text: str, lang: str = "id") -> str:
        """Kirim satu giliran, kembalikan balasan (teks bebas biasa, bukan JSON)."""
        self.history.append(Turn("user", text))
        del self.history[: max(0, len(self.history) - self.max_turns)]
        system = build_system(lang)
        if self.engine == "openrouter":
            raw = self._openrouter.generate(self._openrouter_model, system, self.history)
        else:
            raw = self._ask_gemini(system)
        self.history.append(Turn("assistant", raw))
        self._save_history()
        return raw

    def _ask_gemini(self, system: str) -> str:
        last_exc: ProviderError | None = None
        for model in self._gemini_models:
            try:
                return self._gemini.generate(model, system, self.history)
            except ProviderError as exc:
                # Model ini diblokir sementara (404/429/dll dari percobaan sebelumnya) atau baru
                # gagal - coba model berikutnya di gemini_models sebelum benar-benar menyerah,
                # daripada macet permanen di model pertama yang kebetulan bermasalah.
                last_exc = exc
        raise last_exc or ProviderError("Semua model Gemini di gemini_models gagal/diblokir.")

    @property
    def _active_provider(self):
        return self._openrouter if self.engine == "openrouter" else self._gemini

    # ------------------------------------------------------------------ persistensi riwayat
    def _load_history(self) -> list[Turn]:
        try:
            raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return [Turn(role=t["role"], text=t["text"]) for t in raw]
        except Exception:        # noqa: BLE001 - belum ada riwayat, atau file rusak: mulai kosong saja
            return []

    def _save_history(self) -> None:
        try:
            HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = [{"role": t.role, "text": t.text} for t in self.history]
            HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:        # noqa: BLE001 - gagal simpan riwayat bukan alasan untuk gagal total
            pass