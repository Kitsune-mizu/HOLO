"""Sesi percakapan untuk Mode AI (AI Full).

SENGAJA TERPISAH dari `router.py` (punya HologramOS): tidak ada Ollama/offline, tidak ada
`parse_command`/skema aksi JSON, tidak ada `ModelRegistry`. Kelas ini hanya tahu cara mengobrol
dengan satu penyedia AI online sekaligus, dipilih dari `ENGINES`. Untuk saat ini hanya Gemini -
menambah GPT/Claude nanti tinggal menambah satu entri di `ENGINES` dan satu cabang di `ask()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import ROOT, Config
from .base import ProviderError, Turn
from .full_prompts import build_system
from .gemini_provider import GeminiProvider

HISTORY_PATH = ROOT / ".cache" / "ai_full_history.json"


@dataclass
class FullSession:
    """Satu percakapan AI Full: riwayat sendiri, provider sendiri (Gemini saja). `ask()` melempar
    `ProviderError` kalau gagal - pemanggil (`FullLink`) yang menampilkannya ke pengguna."""

    cfg: Config
    history: list[Turn] = field(default_factory=list)
    max_turns: int = 30

    def __post_init__(self) -> None:
        if not self.history:
            self.history = self._load_history()
        on = self.cfg.section("online")
        full = self.cfg.section("ai_full")
        key = self.cfg.secret("GEMINI_API_KEY")
        self._gemini_models = [str(m) for m in (on.get("gemini_models") or ["gemini-2.0-flash"])]
        self._gemini = GeminiProvider(
            key, use_search=bool(full.get("use_search", on.get("use_search", True))), timeout=float(on.get("timeout_s", 45)),
            min_interval_s=float(on.get("min_interval_s", 4.0)), cooldown_s=float(on.get("cooldown_s", 90.0)),
            max_output_tokens=int(full.get("max_output_tokens", 2048)),   # jauh lebih besar dari 800 punya hologram - balasan boleh panjang
            force_json=False,   # Mode AI selalu jawab teks bebas, tidak pernah JSON
        )

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
        last_exc: ProviderError | None = None
        for model in self._gemini_models:
            try:
                raw = self._gemini.generate(model, system, self.history)
                break
            except ProviderError as exc:
                # Model ini diblokir sementara (404/429/dll dari percobaan sebelumnya) atau baru
                # gagal - coba model berikutnya di gemini_models sebelum benar-benar menyerah,
                # daripada macet permanen di model pertama yang kebetulan bermasalah.
                last_exc = exc
                continue
        else:
            raise last_exc or ProviderError("Semua model Gemini di gemini_models gagal/diblokir.")
        self.history.append(Turn("assistant", raw))
        self._save_history()
        return raw

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