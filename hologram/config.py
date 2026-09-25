"""Membaca config.toml dan .env. Semua path relatif ke folder proyek."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MODELS_DIR = ASSETS / "models"
MODELS_JSON = ASSETS / "models.json"
HAND_MODEL = ASSETS / "ai" / "hand_landmarker.task"
WHISPER_DIR = ASSETS / "whisper"
UI_DIR = ROOT / "hologram" / "ui"

DEFAULTS: dict[str, Any] = {
    "app": {"mode": "offline", "window_width": 1280, "window_height": 720, "default_model": "pyramid"},
    "viewer": {"wireframe": True, "idle_spin_dps": 8, "rotate_step_deg": 45, "zoom_step": 1.35},
    "camera": {"enabled": True, "index": 0, "width": 640, "height": 480, "fps": 30, "detect_fps": 24},
    "hands": {"min_confidence": 0.6, "min_open_fingers": 3},
    "gesture": {
        "deadzone_deg": 8.0, "max_tilt_deg": 45.0, "max_dps": 150.0,
        "pitch_deadzone_deg": 8.0, "pitch_max_tilt_deg": 45.0, "pitch_max_dps": 150.0,
        "deadzone_per_s": 0.03, "gain": 1.6, "max_rate_per_s": 1.2,
        "min_cutoff": 1.2, "beta": 3.0, "dropout_grace_s": 0.15,
    },
    "swipe": {
        "distance": 0.22, "min_speed": 0.9, "window_s": 0.40, "cooldown_s": 0.70,
        "dominance": 1.6, "min_cutoff": 1.5, "beta": 4.0, "dropout_grace_s": 0.15,
    },
    "offline": {"model": "auto", "host": "", "reserve_ram_gb": 2.0, "timeout_s": 120, "fast_commands": True},
    "online": {
        "gemini_models": ["gemini-3.1-flash-lite"], "use_search": True,
        "attach_snapshot": True, "timeout_s": 45, "fallback": [],
        "min_interval_s": 4.0, "cooldown_s": 90.0,
    },
    "voice": {
        "enabled": True, "stt_model": "base", "stt_language": "id", "silence_s": 1.2,
        "max_record_s": 20, "tts_rate": 175, "tts_language": "id",
        "tts_engine": "edge", "tts_voice": "id-ID-GadisNeural", "tts_voice_en": "en-US-JennyNeural", "tts_system_voice_en": "Zira", "tts_system_voice_id": "", "tts_edge_rate": "+0%",
    },
    "network": {"check_interval_s": 8},
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Akses bertingkat: cfg.get("swipe.distance"). Nilai hilang jatuh ke bawaan."""

    def __init__(self, data: dict | None = None, env: dict | None = None) -> None:
        self.data = _merge(DEFAULTS, data or {})
        self.env = env if env is not None else os.environ

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict:
        return dict(self.data.get(name, {}))

    def secret(self, name: str) -> str:
        return (self.env.get(name) or "").strip()


def load_config(path: Path | None = None) -> Config:
    """Baca .env lalu config.toml. File yang tidak ada dilewati, bukan error."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    path = path or ROOT / "config.toml"
    data: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    return Config(data)
