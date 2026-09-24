"""Gesture kontinu, bukan sekali sentak seperti swipe lama:

- Satu tangan menunjuk (telunjuk saja), dimiringkan kanan/kiri -> model berputar (yaw). Makin miring, makin cepat.
- Satu tangan dua jari (telunjuk + tengah), dimiringkan kanan/kiri -> model mengangguk (pitch), dengan cara
  dan rasa yang persis sama seperti putar kiri/kanan, hanya polanya beda supaya mudah dibedakan tanpa dilihat.
- Kedua tangan sekaligus menunjuk satu jari -> zoom dari jarak dua ujung telunjuk. Menjauh = zoom in.

Modul ini murni logika (tidak tahu kamera atau Qt), supaya mudah diuji tanpa kamera sungguhan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .swipe import OneEuroFilter

Point = tuple[float, float]


def signed_tilt_deg(base: Point, tip: Point) -> float:
    """Sudut kemiringan jari dari garis vertikal (lurus ke atas), dalam koordinat gambar (Y ke bawah).
    0 derajat = tegak lurus ke atas. Positif = miring ke kanan. Negatif = miring ke kiri."""
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    return math.degrees(math.atan2(dx, -dy))


@dataclass
class RotationConfig:
    deadzone_deg: float = 8.0     # kemiringan di bawah ini dianggap netral (tegak), tidak bergerak
    max_tilt_deg: float = 45.0    # kemiringan sebesar ini atau lebih = kecepatan maksimum
    max_dps: float = 150.0        # kecepatan maksimum, derajat per detik
    min_cutoff: float = 1.2
    beta: float = 3.0

    @classmethod
    def from_dict(cls, data: dict, prefix: str = "") -> "RotationConfig":
        """`prefix`: baca kunci mis. "pitch_deadzone_deg" alih-alih "deadzone_deg", untuk dua sumbu terpisah."""
        out: dict = {}
        for name in cls.__dataclass_fields__:
            key = f"{prefix}{name}" if prefix else name
            if key in data:
                out[name] = data[key]
        return cls(**out)


class RotationGesture:
    """Kemiringan jari (kanan/kiri) jadi kecepatan gerak kontinu. Dipakai dua kali: untuk yaw (satu jari)
    dan untuk pitch (dua jari) -- logika dan rasanya sengaja dibuat identik, supaya begitu satu sumbu terasa
    enak dikendalikan, sumbu satunya terasa sama enaknya."""

    def __init__(self, cfg: RotationConfig | None = None) -> None:
        self.cfg = cfg or RotationConfig()
        self._filter = OneEuroFilter(self.cfg.min_cutoff, self.cfg.beta)

    def reset(self) -> None:
        self._filter.reset()

    def update(self, base: Point, tip: Point, t: float, dt: float) -> tuple[float, str]:
        """Kembalikan (derajat gerak untuk frame ini, label singkat "" / "kanan" / "kiri")."""
        angle = self._filter(signed_tilt_deg(base, tip), t)
        mag = abs(angle)
        c = self.cfg
        if mag <= c.deadzone_deg:
            return 0.0, ""
        span = max(1e-6, c.max_tilt_deg - c.deadzone_deg)
        u = min(1.0, (mag - c.deadzone_deg) / span)
        speed = (u * u * (3 - 2 * u)) * c.max_dps      # smoothstep: mulus dari pelan ke cepat
        delta = math.copysign(speed, angle) * dt
        return delta, ("kanan" if angle > 0 else "kiri")


@dataclass
class ZoomConfig:
    deadzone_per_s: float = 0.03   # perubahan jarak di bawah ini (per detik) dianggap diam
    gain: float = 1.6              # makin besar, makin sensitif menjauh/mendekat jadi zoom
    max_rate_per_s: float = 1.2    # batas laju zoom per detik, supaya tidak melompat
    min_cutoff: float = 1.0
    beta: float = 2.0

    @classmethod
    def from_dict(cls, data: dict) -> "ZoomConfig":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


class PinchGesture:
    """Dua tangan menunjuk satu jari: jarak dua ujung telunjuk berubah jadi faktor zoom (cubit di layar sentuh)."""

    def __init__(self, cfg: ZoomConfig | None = None) -> None:
        self.cfg = cfg or ZoomConfig()
        self._filter = OneEuroFilter(self.cfg.min_cutoff, self.cfg.beta)
        self._prev: float | None = None

    def reset(self) -> None:
        self._filter.reset()
        self._prev = None

    def update(self, a: Point, b: Point, aspect: float, t: float, dt: float) -> tuple[float, str]:
        """Kembalikan (pengali zoom untuk frame ini, label "" / "zoom in" / "zoom out")."""
        dist = math.hypot(a[0] - b[0], (a[1] - b[1]) * aspect)
        smooth = self._filter(dist, t)
        if self._prev is None:
            self._prev = smooth
            return 1.0, ""
        rate = (smooth - self._prev) / max(dt, 1e-6)
        self._prev = smooth
        if abs(rate) <= self.cfg.deadzone_per_s:
            return 1.0, ""
        rate = math.copysign(min(abs(rate), self.cfg.max_rate_per_s), rate)
        factor = 1.0 + rate * self.cfg.gain * dt
        return factor, ("zoom in" if rate > 0 else "zoom out")


@dataclass
class GestureOutput:
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    zoom_factor: float = 1.0
    label: str = ""


# Bentuk satu tangan per frame: "point" (satu jari, telunjuk) atau "two" (dua jari, telunjuk + tengah).
HandInput = tuple[str, Point, Point]   # (mode, pangkal, ujung)


@dataclass
class GestureController:
    """Menggabungkan tiga gesture dari sampai dua tangan per frame:

    - Satu tangan "point" (satu jari) -> putar kiri/kanan (yaw).
    - Satu tangan "two" (dua jari)    -> mengangguk atas/bawah (pitch), mekanisme sama seperti yaw.
    - Dua tangan "point" sekaligus    -> zoom dari jarak dua ujung telunjuk.
    - Satu "point" + satu "two" sekaligus -> yaw dan pitch jalan bersamaan, independen.
    - Kombinasi lain (mis. dua tangan "two") -> diam, artinya tidak jelas.
    """

    rotation: RotationGesture = field(default_factory=RotationGesture)
    pitch: RotationGesture = field(default_factory=RotationGesture)
    pinch: PinchGesture = field(default_factory=PinchGesture)

    def update(self, hands: list[HandInput], aspect: float, t: float, dt: float) -> GestureOutput:
        points = [h for h in hands if h[0] == "point"]
        twos = [h for h in hands if h[0] == "two"]

        if len(points) == 2 and not twos:
            self.rotation.reset()
            self.pitch.reset()
            factor, zlabel = self.pinch.update(points[0][2], points[1][2], aspect, t, dt)
            return GestureOutput(zoom_factor=factor, label=zlabel)

        self.pinch.reset()
        yaw = pitch = 0.0
        yaw_label = pitch_label = ""
        if len(points) == 1:
            _, base, tip = points[0]
            yaw, yaw_label = self.rotation.update(base, tip, t, dt)
        else:
            self.rotation.reset()
        if len(twos) == 1:
            _, base, tip = twos[0]
            pitch, pitch_label = self.pitch.update(base, tip, t, dt)
        else:
            self.pitch.reset()

        label = ""
        if yaw_label and (not pitch_label or abs(yaw) >= abs(pitch)):
            label = "memutar " + yaw_label
        elif pitch_label:
            label = "menunduk" if pitch_label == "kanan" else "mendongak"
        return GestureOutput(yaw_deg=yaw, pitch_deg=pitch, label=label)