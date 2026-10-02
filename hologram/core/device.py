"""Info perangkat: RAM (dan VRAM kalau ada) untuk menandai model offline yang aman."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import psutil

GB = 1000 ** 3


@dataclass(frozen=True)
class DeviceInfo:
    ram_total: int
    ram_available: int
    vram_free: int = 0


@lru_cache(maxsize=1)
def _vram_free() -> int:
    """VRAM bebas kartu NVIDIA saat aplikasi mulai. 0 kalau tidak ada atau tidak terbaca."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return 0
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout
        return max(int(line.strip()) for line in out.splitlines() if line.strip()) * 1024 * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def snapshot() -> DeviceInfo:
    mem = psutil.virtual_memory()
    return DeviceInfo(ram_total=mem.total, ram_available=mem.available, vram_free=_vram_free())


def is_safe(size_bytes: int, info: DeviceInfo, reserve_gb: float = 2.0) -> bool:
    """Ukuran model ditambah cadangan sistem harus muat di RAM, atau model muat penuh di VRAM."""
    if size_bytes + reserve_gb * GB <= info.ram_available:
        return True
    return info.vram_free > 0 and size_bytes * 1.1 <= info.vram_free


def pick_model(models: list[tuple[str, int]], info: DeviceInfo, reserve_gb: float = 2.0) -> str | None:
    """Model terbesar yang aman. Kalau tidak ada yang aman, yang terkecil."""
    if not models:
        return None
    safe = [m for m in models if is_safe(m[1], info, reserve_gb)]
    if safe:
        return max(safe, key=lambda m: m[1])[0]
    return min(models, key=lambda m: m[1])[0]


def format_size(size: int) -> str:
    """Format seperti `ollama list`: 4.9 GB, 986 MB."""
    if size >= GB:
        return f"{size / GB:.1f} GB"
    return f"{size / 1000 ** 2:.0f} MB"


def ram_text(info: DeviceInfo) -> str:
    used = info.ram_total - info.ram_available
    return f"{used / GB:.1f} / {info.ram_total / GB:.1f} GB"


def humanize_age(moment: datetime | None, now: datetime | None = None) -> str:
    """"2 days ago" seperti kolom MODIFIED di `ollama list`."""
    if moment is None:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    seconds = max(0, int((now - moment).total_seconds()))
    for unit, span in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= span:
            n = seconds // span
            return f"{n} {unit}{'' if n == 1 else 's'} ago"
    return "just now"
