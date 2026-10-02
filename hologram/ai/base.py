"""Bentuk dasar penyedia AI dan balasan."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """Kegagalan satu penyedia. Pesannya ditulis untuk ditampilkan ke pengguna."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Turn:
    role: str      # "user" atau "assistant"
    text: str


@dataclass
class Reply:
    text: str                      # keluaran mentah model (biasanya JSON)
    provider: str
    model: str
    mode: str                      # mode yang benar-benar dipakai: "offline" / "online"
    notes: list[str] = field(default_factory=list)


class Provider(ABC):
    name = "Provider"

    @abstractmethod
    def generate(self, model: str, system: str, history: list[Turn], image: bytes | None = None) -> str:
        """Kirim percakapan, kembalikan teks mentah. `image` = PNG tangkapan tampilan 3D."""
