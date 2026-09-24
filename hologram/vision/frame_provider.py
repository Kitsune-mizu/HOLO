"""Menyusun gambar kamera abu-abu + kerangka tangan (sampai dua), lalu menyajikannya ke QML lewat image provider."""
from __future__ import annotations

import threading

import numpy as np
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickImageProvider

from .cv import load_cv2
from .hands import INDEX_TIP, HandState

CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)
INK = (255, 255, 200)     # krem: garis kerangka tangan, sama dengan garis wireframe model
ACCENT = (60, 176, 255)   # oranye-amber: titik ujung telunjuk yang sedang dilacak untuk gesture


def _draw_hand(cv2, rgb: np.ndarray, hand: HandState, w: int, h: int) -> tuple[int, int] | None:
    pts = [(int(x * w), int(y * h)) for x, y in hand.points]
    for a, b in CONNECTIONS:
        cv2.line(rgb, pts[a], pts[b], INK, 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(rgb, p, 3, INK, -1, cv2.LINE_AA)
    if hand.pointing or hand.two_finger:
        cv2.circle(rgb, pts[INDEX_TIP], 9, ACCENT, 2, cv2.LINE_AA)
        cv2.circle(rgb, pts[INDEX_TIP], 3, ACCENT, -1, cv2.LINE_AA)
        if hand.two_finger:                    # dua jari: tandai juga ujung jari tengah, beda dari satu-jari
            cv2.circle(rgb, pts[12], 9, ACCENT, 2, cv2.LINE_AA)
        return pts[INDEX_TIP]
    return None


def compose_display(frame_bgr: np.ndarray, hands: tuple[HandState, ...]) -> QImage:
    """Frame abu-abu (RGB, tiga kanal sama) dengan kerangka tiap tangan yang terlihat di atasnya."""
    cv2 = load_cv2()
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    rgb = np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB))
    h, w = rgb.shape[:2]
    tips = []
    for hand in hands:
        if hand.present and hand.points:
            tip = _draw_hand(cv2, rgb, hand, w, h)
            if tip:
                tips.append(tip)
    if len(tips) == 2:                # dua tangan menunjuk: garis penghubung menandai jarak yang diukur untuk zoom
        cv2.line(rgb, tips[0], tips[1], ACCENT, 1, cv2.LINE_AA)
    return QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()


class FrameProvider(QQuickImageProvider):
    """Dipakai QML sebagai image://camera/<nomor>. Nomor hanya memaksa muat ulang."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._lock = threading.Lock()
        blank = QImage(16, 9, QImage.Format.Format_RGB888)
        blank.fill(QColor(0, 0, 0))
        self._image = blank

    def set_image(self, image: QImage) -> None:
        with self._lock:
            self._image = image

    def requestImage(self, id, size, requestedSize):  # noqa: A002 (nama dari Qt)
        with self._lock:
            return self._image