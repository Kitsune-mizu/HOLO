"""Menyusun aplikasi: Qt, mesin QML, image provider kamera, dan Controller."""
from __future__ import annotations

import os
import sys

from .config import UI_DIR, Config, load_config


def _preload_quick3d() -> None:
    """Windows: muat DLL Quick 3D lebih dulu supaya Qt menemukan dependensinya."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import glob

        import PySide6

        base = os.path.dirname(PySide6.__file__)
        os.add_dll_directory(base)
        for pattern in ("Qt6Quick3D*.dll", "qml/QtQuick3D/*.dll", "qml/QtQuick3D/*/*.dll"):
            for path in sorted(glob.glob(os.path.join(base, pattern))):
                try:
                    ctypes.WinDLL(path)
                except OSError:
                    pass
    except Exception:
        pass


def build(cfg: Config, no_camera: bool = False, no_voice: bool = False):
    """Buat QGuiApplication, engine, dan controller. Dipisah dari run() supaya bisa diuji."""
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")   # gaya yang bisa dikustom penuh
    _preload_quick3d()

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from .core.controller import Controller
    from .core.editor import ProjectEditor
    from .vision.frame_provider import FrameProvider

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("HologramOS")

    provider = FrameProvider()
    controller = Controller(cfg, provider, no_camera=no_camera, no_voice=no_voice)

    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", provider)
    # Diberi parent controller (bukan dibiarkan sementara) supaya tidak dibuang Python sebelum QML memakainya.
    # Perlu `engine` untuk bisa memuat ulang QML sendiri saat tombol "Simpan & Terapkan" ditekan pada file .qml.
    project_editor = ProjectEditor(engine, controller, controller)
    context = engine.rootContext()
    context.setContextProperty("controller", controller)
    context.setContextProperty("messageModel", controller.messages)
    context.setContextProperty("editor", project_editor)
    context.setContextProperty("viewCfg", {
        "initialWidth": int(cfg.get("app.window_width", 1280)),
        "initialHeight": int(cfg.get("app.window_height", 720)),
        "wireframe": bool(cfg.get("viewer.wireframe", True)),
        "idleSpin": float(cfg.get("viewer.idle_spin_dps", 8)),
        "rotateStep": float(cfg.get("viewer.rotate_step_deg", 45)),
    })
    engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
    return app, engine, controller


def run(no_camera: bool = False, no_voice: bool = False, config_path=None) -> int:
    cfg = load_config(config_path)
    app, engine, controller = build(cfg, no_camera, no_voice)
    if not engine.rootObjects():
        print("Gagal memuat antarmuka. Lihat pesan QML di atas.", file=sys.stderr)
        return 1
    app.aboutToQuit.connect(controller.shutdown)
    controller.start()
    return app.exec()