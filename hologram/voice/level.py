"""Tingkat suara (RMS) untuk menggerakkan bar suara."""
from __future__ import annotations

import numpy as np


def rms(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))


class LevelMeter:
    """Menghaluskan RMS: naik cepat, turun pelan, hasil 0..1. Aman dibaca dari thread lain."""

    def __init__(self, attack: float = 0.7, release: float = 0.12, gain: float = 2.4) -> None:
        self._attack, self._release, self._gain = attack, release, gain
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value

    def push(self, chunk: np.ndarray) -> None:
        target = min(1.0, (rms(chunk) ** 0.6) * self._gain)
        rate = self._attack if target > self._value else self._release
        self._value += (target - self._value) * rate

    def reset(self) -> None:
        self._value = 0.0
