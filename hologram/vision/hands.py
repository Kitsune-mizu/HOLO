"""Deteksi tangan (sampai dua) dengan MediaPipe HandLandmarker, lalu umpan ke gesture kontinu:
satu tangan menunjuk dan dimiringkan = putar model; dua tangan menunjuk = zoom (jarak berubah)."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

from ..threads import stop_thread
from .cv import load_cv2
from .gesture import GestureController, RotationConfig, ZoomConfig

PALM_POINTS = (0, 5, 9, 13, 17)
FINGERS = ((8, 6), (12, 10), (16, 14), (20, 18))   # (ujung, sendi tengah): telunjuk, tengah, manis, kelingking
INDEX_TIP = 8
INDEX_MCP = 5      # pangkal telunjuk: dipakai sebagai titik "pangkal" untuk mengukur arah kemiringan


@dataclass(frozen=True)
class HandState:
    present: bool = False
    open_palm: bool = False
    pointing: bool = False     # satu jari: telunjuk lurus, tiga jari lain menekuk -> kendali putar (yaw)
    two_finger: bool = False   # dua jari: telunjuk + tengah lurus, dua jari lain menekuk -> kendali angguk (pitch)
    confidence: float = 0.0
    points: tuple[tuple[float, float], ...] = ()
    palm: tuple[float, float] = (0.0, 0.0)


NO_HAND = HandState()
NO_HANDS: tuple[HandState, ...] = ()


def palm_center(points: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [points[i][0] for i in PALM_POINTS]
    ys = [points[i][1] for i in PALM_POINTS]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _reaches(points: list[tuple[float, float]], aspect: float) -> list[float]:
    """Jarak tiap ujung jari ke pergelangan, dalam satuan yang sama di X dan Y (aspect membetulkan rasio frame)."""
    wx, wy = points[0][0], points[0][1] * aspect

    def reach(i: int) -> float:
        return math.hypot(points[i][0] - wx, points[i][1] * aspect - wy)

    return [reach(tip) - reach(pip) * 1.08 for tip, pip in FINGERS]


def count_open_fingers(points: list[tuple[float, float]], aspect: float = 1.0) -> int:
    """Jari dianggap terbuka kalau ujungnya lebih jauh dari pergelangan daripada sendi tengahnya."""
    return sum(1 for margin in _reaches(points, aspect) if margin > 0)


def is_pointing(points: list[tuple[float, float]], aspect: float = 1.0) -> bool:
    """Telunjuk lurus, tiga jari lain (tengah, manis, kelingking) menekuk. Ibu jari tidak dicek."""
    index_m, middle_m, ring_m, pinky_m = _reaches(points, aspect)
    return index_m > 0 and middle_m <= 0 and ring_m <= 0 and pinky_m <= 0


def is_two_finger(points: list[tuple[float, float]], aspect: float = 1.0) -> bool:
    """Telunjuk DAN tengah lurus, manis dan kelingking menekuk. Ibu jari tidak dicek."""
    index_m, middle_m, ring_m, pinky_m = _reaches(points, aspect)
    return index_m > 0 and middle_m > 0 and ring_m <= 0 and pinky_m <= 0


class DropoutGate:
    """Menahan sebentar kalau tangan berkedip hilang (gerakan cepat, cahaya kurang), supaya gesture
    yang sedang berjalan tidak dibatalkan gara-gara satu-dua frame terlewat."""

    def __init__(self, grace_s: float = 0.15) -> None:
        self.grace_s = grace_s
        self._last_ok: float | None = None

    def update(self, ok: bool, now: float) -> bool:
        """True: dianggap benar-benar hilang, boleh direset. False: lanjutkan (atau baru berhenti sebentar)."""
        if ok:
            self._last_ok = now
            return False
        if self._last_ok is None:
            return True
        return (now - self._last_ok) > self.grace_s


def _detect_hands(result, min_open_fingers: int, aspect: float) -> tuple[HandState, ...]:
    out = []
    for landmarks, handedness in zip(result.hand_landmarks or [], result.handedness or []):
        points = [(lm.x, lm.y) for lm in landmarks]
        out.append(HandState(
            present=True,
            open_palm=count_open_fingers(points, aspect) >= min_open_fingers,
            pointing=is_pointing(points, aspect),
            two_finger=is_two_finger(points, aspect),
            confidence=float(handedness[0].score) if handedness else 1.0,
            points=tuple(points),
            palm=palm_center(points),
        ))
    return tuple(out)


class HandTracker(QThread):
    spin = Signal(float, float)    # (yaw, pitch) derajat putar untuk frame ini, bisa negatif
    zoomFactor = Signal(float)     # pengali zoom untuk frame ini (1.0 = tidak berubah)
    gestureLabel = Signal(str)     # teks singkat untuk ditampilkan sesaat, "" = sembunyikan
    stateChanged = Signal(str)     # "none", "open", "closed", "point", atau "pinch" (dua tangan menunjuk)
    failed = Signal(str)

    def __init__(self, camera, model_path: Path, cfg, parent=None) -> None:
        super().__init__(parent)
        self._camera = camera
        self._model_path = model_path
        self._hands_cfg = cfg.section("hands")
        self._detect_fps = max(1, int(cfg.get("camera.detect_fps", 24)))
        self._gesture_cfg = cfg.section("gesture")
        self._grace_s = float(cfg.get("gesture.dropout_grace_s", cfg.get("swipe.dropout_grace_s", 0.15)))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state: tuple[HandState, ...] = NO_HANDS

    def latest(self) -> tuple[HandState, ...]:
        """Semua tangan yang terlihat saat ini (0, 1, atau 2), untuk digambar di kartu kamera."""
        with self._lock:
            return self._state

    def stop(self) -> None:
        self._stop.set()
        stop_thread(self, 3000)

    # ------------------------------------------------------------------ thread
    def run(self) -> None:
        try:
            landmarker, mp = self._create()
        except FileNotFoundError:
            self.failed.emit("Model tangan belum diunduh. Jalankan: python tools/download_assets.py")
            return
        except Exception as exc:  # mediapipe belum terpasang atau gagal dimuat
            self.failed.emit(f"Deteksi tangan tidak bisa dimulai: {exc}")
            return
        cv2 = load_cv2()
        gesture = _build_controller(self._gesture_cfg)
        gate = DropoutGate(self._grace_s)
        min_open = int(self._hands_cfg.get("min_open_fingers", 3))
        period = 1.0 / self._detect_fps
        last_seq, last_ts, last_label = -1, 0, "none"
        last_now = time.monotonic()
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                frame, seq = self._camera.latest()
                if frame is None or seq == last_seq:
                    self._stop.wait(0.01)
                    continue
                last_seq = seq
                h, w = frame.shape[:2]
                aspect = h / w
                small = cv2.resize(frame, (320, max(1, int(320 * aspect))))
                rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                last_ts = max(last_ts + 1, int(time.monotonic() * 1000))
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), last_ts)
                states = _detect_hands(result, min_open, aspect)
                with self._lock:
                    self._state = states
                label = self._label(states)
                if label != last_label:
                    last_label = label
                    self.stateChanged.emit(label)
                now = time.monotonic()
                self._feed(gesture, gate, states, aspect, now, now - last_now)
                last_now = now
                rest = period - (time.monotonic() - started)
                if rest > 0:
                    self._stop.wait(rest)
        finally:
            landmarker.close()

    @staticmethod
    def _label(states: tuple[HandState, ...]) -> str:
        pointing = [s for s in states if s.pointing]
        twos = [s for s in states if s.two_finger]
        if len(pointing) >= 2:
            return "pinch"
        if len(pointing) == 1 and twos:
            return "point_two"
        if len(pointing) == 1:
            return "point"
        if twos:
            return "two"
        if any(s.open_palm for s in states):
            return "open"
        if states:
            return "closed"
        return "none"

    def _create(self):
        if not self._model_path.exists():
            raise FileNotFoundError(self._model_path)
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        conf = float(self._hands_cfg.get("min_confidence", 0.6))
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=conf,
            min_hand_presence_confidence=conf,
            min_tracking_confidence=conf,
        )
        return vision.HandLandmarker.create_from_options(options), mp

    def _feed(self, gesture: GestureController, gate: DropoutGate, states: tuple[HandState, ...],
              aspect: float, now: float, dt: float) -> None:
        min_conf = float(self._hands_cfg.get("min_confidence", 0.6))
        usable_hands = [s for s in states if s.present and s.confidence >= min_conf and (s.pointing or s.two_finger)]
        usable = bool(usable_hands)
        if gate.update(usable, now):
            gesture.rotation.reset()
            gesture.pitch.reset()
            gesture.pinch.reset()
            self.gestureLabel.emit("")
            return
        if not usable or dt <= 0 or dt > 0.5:              # kedip sebentar, atau lompatan waktu (mis. baru dibuka)
            return
        hands_in = [
            ("point" if s.pointing else "two", s.points[INDEX_MCP], s.points[INDEX_TIP]) for s in usable_hands
        ]
        out = gesture.update(hands_in, aspect, now, dt)
        if out.yaw_deg or out.pitch_deg:
            self.spin.emit(out.yaw_deg, out.pitch_deg)
        if out.zoom_factor != 1.0:
            self.zoomFactor.emit(out.zoom_factor)
        self.gestureLabel.emit(out.label)


def _build_controller(gesture_cfg: dict) -> GestureController:
    from .gesture import PinchGesture, RotationGesture

    return GestureController(
        rotation=RotationGesture(RotationConfig.from_dict(gesture_cfg)),
        pitch=RotationGesture(RotationConfig.from_dict(gesture_cfg, prefix="pitch_")),
        pinch=PinchGesture(ZoomConfig.from_dict(gesture_cfg)),
    )