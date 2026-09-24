"""Menghubungkan kamera + deteksi tangan ke Controller: status, frame untuk kartu kamera, dan gesture kontinu."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Slot

from ..config import HAND_MODEL
from ..vision.camera import CameraWorker
from ..vision.frame_provider import compose_display
from ..vision.hands import NO_HANDS, HandTracker

OFF_MESSAGE = "Kamera mati. Tekan ikon kamera di pojok kartu untuk menyalakan."


class CameraLink(QObject):
    def __init__(self, ctl) -> None:
        super().__init__(ctl)
        self.ctl = ctl
        self.camera: CameraWorker | None = None
        self.tracker: HandTracker | None = None
        self._cam_err = self._hand_err = ""
        self._gesture_timer = QTimer(self, singleShot=True, interval=900)
        self._gesture_timer.timeout.connect(lambda: ctl._set("gesture", ""))

    def start(self, disabled: bool) -> None:
        ctl = self.ctl
        if disabled or not ctl.cfg.get("camera.enabled"):
            self._cam_err = OFF_MESSAGE
            self._refresh()
            return
        self._launch()

    def set_enabled(self, on: bool) -> None:
        """Tombol kecil di kartu kamera: matikan atau hidupkan kamera dan deteksi tangan."""
        ctl = self.ctl
        if on == ctl.get("cameraOn"):
            return
        if on:
            self._cam_err = self._hand_err = ""
            self._refresh()
            self._launch()
            return
        self.stop()
        self.camera = self.tracker = None
        ctl._set("cameraOn", False)
        ctl._set("cameraFrame", 0)
        ctl._set("handState", "none")
        ctl._set("gesture", "")
        self._cam_err = OFF_MESSAGE
        self._refresh()

    def _launch(self) -> None:
        ctl = self.ctl
        self.camera = CameraWorker(ctl.cfg.section("camera"), self._on_frame)
        self.tracker = HandTracker(self.camera, HAND_MODEL, ctl.cfg, self)
        self.camera.statusChanged.connect(self._on_camera_status)
        self.camera.frameUpdated.connect(self._on_frame_updated)
        self.tracker.spin.connect(self._on_spin)
        self.tracker.zoomFactor.connect(self._on_zoom)
        self.tracker.gestureLabel.connect(self._on_gesture_label)
        self.tracker.stateChanged.connect(self._on_hand_state)
        self.tracker.failed.connect(self._on_hand_failed)
        self.camera.start()
        self.tracker.start()
        ctl._set("cameraOn", True)

    def stop(self) -> None:
        for part in (self.tracker, self.camera):
            if part:
                part.stop()

    # ------------------------------------------------------------------ dari thread kamera
    def _on_frame(self, frame) -> None:
        """Dipanggil di thread kamera: susun gambar tampilan dan simpan di image provider."""
        try:
            hands = self.tracker.latest() if self.tracker else NO_HANDS
            self.ctl.provider.set_image(compose_display(frame, hands))
        except Exception:
            pass

    # ------------------------------------------------------------------ di thread utama
    @Slot()
    def _on_frame_updated(self) -> None:
        if not self.ctl.get("cameraOn"):
            return
        self.ctl._set("cameraFrame", self.ctl.get("cameraFrame") + 1)

    @Slot(str)
    def _on_camera_status(self, text: str) -> None:
        if not self.ctl.get("cameraOn"):
            return                                   # sinyal terlambat dari kamera yang baru dimatikan
        self._cam_err = text
        self._refresh()

    @Slot(str)
    def _on_hand_failed(self, text: str) -> None:
        if not self.ctl.get("cameraOn"):
            return
        self._hand_err = text
        self._refresh()

    @Slot(str)
    def _on_hand_state(self, label: str) -> None:
        self.ctl._set("handState", label)

    def _refresh(self) -> None:
        self.ctl._set("cameraStatus", self._cam_err or self._hand_err)

    @Slot(float, float)
    def _on_spin(self, yaw: float, pitch: float) -> None:
        if self.ctl.get("cameraOn"):
            self.ctl.spin(yaw, pitch)

    @Slot(float)
    def _on_zoom(self, factor: float) -> None:
        if self.ctl.get("cameraOn"):
            self.ctl.viewCommand.emit("zoom", str(factor))

    @Slot(str)
    def _on_gesture_label(self, text: str) -> None:
        self.ctl._set("gesture", text)
        if text:
            self._gesture_timer.start()
        else:
            self._gesture_timer.stop()