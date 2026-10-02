"""Filter penghalus dan deteksi swipe udara (kanan, kiri, atas, bawah).

Modul ini murni logika: tidak tahu kamera, MediaPipe, atau Qt. Koordinat masuk
dalam satuan lebar frame (x dan y dibagi lebar), jadi jarak ke kanan dan ke atas
punya bobot yang sama walau frame berbentuk 16:9.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


class OneEuroFilter:
    """Filter One Euro: halus saat tangan diam, cepat menyusul saat tangan bergerak."""

    def __init__(self, min_cutoff: float = 1.5, beta: float = 4.0, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: float | None = None
        self._dx = 0.0
        self._t = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self) -> None:
        self._x = None

    def __call__(self, x: float, t: float) -> float:
        if self._x is None or t <= self._t:
            self._x, self._dx, self._t = x, 0.0, t
            return x
        dt = t - self._t
        dx = (x - self._x) / dt
        self._dx += self._alpha(self.d_cutoff, dt) * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        self._x += self._alpha(cutoff, dt) * (x - self._x)
        self._t = t
        return self._x


@dataclass(frozen=True)
class SwipeConfig:
    distance: float = 0.22
    min_speed: float = 0.9
    window_s: float = 0.40
    cooldown_s: float = 0.70
    dominance: float = 1.6
    min_cutoff: float = 1.5
    beta: float = 4.0
    settle_speed: float = 0.35

    @classmethod
    def from_dict(cls, data: dict) -> "SwipeConfig":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        if "window_s" not in known and "window" in data:
            known["window_s"] = data["window"]
        return cls(**known)


class SwipeDetector:
    """Mengubah aliran posisi telapak tangan menjadi peristiwa swipe.

    Swipe sah kalau gerakan dalam jendela waktu pendek melewati ambang jarak dan
    kecepatan, dan satu sumbu jelas lebih dominan. Setelah satu swipe ada jeda,
    lalu detektor menunggu tangan hampir diam sebelum aktif lagi. Dengan begitu
    gerakan tangan kembali ke posisi awal tidak terbaca sebagai swipe berlawanan.
    """

    def __init__(self, cfg: SwipeConfig | None = None) -> None:
        self.cfg = cfg or SwipeConfig()
        self._fx = OneEuroFilter(self.cfg.min_cutoff, self.cfg.beta)
        self._fy = OneEuroFilter(self.cfg.min_cutoff, self.cfg.beta)
        self._history: deque[tuple[float, float, float]] = deque()
        self._cooldown_until = 0.0
        self._armed = True

    def lost(self) -> None:
        """Tangan hilang atau keyakinan rendah: buang riwayat, rotasi tidak disentuh."""
        self._history.clear()
        self._fx.reset()
        self._fy.reset()

    def update(self, x: float, y: float, t: float) -> str | None:
        fx, fy = self._fx(x, t), self._fy(y, t)
        hist = self._history
        hist.append((t, fx, fy))
        while hist and t - hist[0][0] > self.cfg.window_s:
            hist.popleft()

        if t < self._cooldown_until:
            return None
        if not self._armed:
            if self._recent_speed() < self.cfg.settle_speed:
                self._armed = True
                hist.clear()
            return None

        direction = self._match(fx, fy, t)
        if direction is None:
            return None
        self._cooldown_until = t + self.cfg.cooldown_s
        self._armed = False
        hist.clear()
        return direction

    def _match(self, fx: float, fy: float, t: float) -> str | None:
        """Coba tiap sampel riwayat sebagai awal gerakan, supaya frame diam di depan tidak mengencerkan kecepatan."""
        best: tuple[float, float, float] | None = None
        for t0, x0, y0 in self._history:
            dt = t - t0
            if dt < 0.06:
                continue
            dx, dy = fx - x0, fy - y0
            dist = math.hypot(dx, dy)
            if dist < self.cfg.distance or dist / dt < self.cfg.min_speed:
                continue
            major, minor = max(abs(dx), abs(dy)), min(abs(dx), abs(dy))
            if major < self.cfg.dominance * minor:
                continue
            if best is None or dist > best[0]:
                best = (dist, dx, dy)
        if best is None:
            return None
        _, dx, dy = best
        if abs(dx) >= abs(dy):
            return "right" if dx > 0 else "left"
        return "down" if dy > 0 else "up"

    def _recent_speed(self) -> float:
        if len(self._history) < 2:
            return 0.0
        (t0, x0, y0), (t1, x1, y1) = self._history[-2], self._history[-1]
        dt = max(t1 - t0, 1e-3)
        return math.hypot(x1 - x0, y1 - y0) / dt
