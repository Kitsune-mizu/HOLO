import json
import struct
import subprocess
import sys
import time

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from hologram.config import MODELS_DIR, MODELS_JSON, ROOT, Config
from hologram.models3d.registry import ModelRegistry
from hologram.vision import camera as camod


class FakeCap:
    def __init__(self):
        self.n = 0

    def isOpened(self): return True
    def release(self): pass
    def set(self, *a): pass

    def read(self):
        self.n += 1
        frame = np.zeros((480, 640, 3), np.uint8)
        frame[:, :100] = (0, 0, 255)          # sisi kiri merah
        return True, frame


def test_camera_crops_to_16_9_and_mirrors(monkeypatch, qapp):
    monkeypatch.setattr(camod.CameraWorker, "_open", lambda self, cv2: FakeCap())
    seen = []
    worker = camod.CameraWorker({"fps": 100}, on_frame=seen.append)
    statuses = []
    worker.statusChanged.connect(statuses.append)
    worker.start()
    end = time.time() + 5
    while not seen and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    worker.stop()
    frame, seq = worker.latest()
    assert frame.shape[:2] == (360, 640) and seq >= 1
    assert frame[0, -1].tolist() == [0, 0, 255] and frame[0, 0].tolist() == [0, 0, 0]   # dicerminkan


def test_camera_reports_missing_device(monkeypatch, qapp):
    monkeypatch.setattr(camod.CameraWorker, "_open", lambda self, cv2: None)
    worker = camod.CameraWorker({"index": 3})
    statuses = []
    worker.statusChanged.connect(statuses.append)
    worker.start()
    end = time.time() + 5
    while not statuses and time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.01)
    worker.stop()
    assert statuses and "indeks 3" in statuses[0] and "--no-camera" in statuses[0]


def test_registry_reads_all_shipped_models_and_flags_missing(tmp_path):
    reg = ModelRegistry(MODELS_JSON, MODELS_DIR)
    assert {"pyramid", "drone", "fighter", "bomber"} <= {e.id for e in reg.all()} and not reg.skipped
    assert reg.find("pesawat tempur").id == "fighter" and reg.find("piramida").id == "pyramid"
    data = {"models": [{"id": "ghost", "file": "ghost.glb"}]}
    (tmp_path / "m.json").write_text(json.dumps(data))
    ghost = ModelRegistry(tmp_path / "m.json", tmp_path)
    assert ghost.all() == [] and ghost.skipped == ["ghost"]


@pytest.mark.parametrize("name", ["pyramid", "drone", "fighter", "bomber"])
def test_shipped_glb_files_are_valid(name):
    blob = (MODELS_DIR / f"{name}.glb").read_bytes()
    magic, version, total = struct.unpack("<4sII", blob[:12])
    assert (magic, version, total) == (b"glTF", 2, len(blob))
    length, kind = struct.unpack("<I4s", blob[12:20])
    doc = json.loads(blob[20:20 + length])
    assert kind == b"JSON" and doc["meshes"] and doc["accessors"][0]["count"] >= 18


def test_config_defaults_and_secret_lookup():
    cfg = Config({"swipe": {"distance": 0.5}}, env={"GEMINI_API_KEY": " abc "})
    assert cfg.get("swipe.distance") == 0.5 and cfg.get("swipe.cooldown_s") == 0.70
    assert cfg.secret("GEMINI_API_KEY") == "abc" and cfg.secret("NOPE") == ""
    assert cfg.get("a.b.c", "x") == "x"


def test_shipped_config_toml_parses_and_lists_gemini_models():
    from hologram.config import load_config
    cfg = load_config(ROOT / "config.toml")
    assert cfg.get("online.gemini_models") and cfg.get("app.mode") in ("offline", "online")
    assert cfg.get("online.fallback")[0]["enabled"] is False


def test_qml_loads_without_warnings():
    """Memuat Main.qml tanpa GPU (offscreen). View3D tidak menggambar di sini, tapi semua QML harus terurai."""
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from hologram.config import load_config\n"
        "from hologram import app\n"
        "a, engine, ctl = app.build(load_config(), True, True)\n"
        "ok = bool(engine.rootObjects()); print('LOADED' if ok else 'FAILED')\n"
        "os._exit(0)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                         env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"})
    combined = out.stdout + out.stderr
    assert "LOADED" in out.stdout, combined
    bad = [l for l in combined.splitlines() if ".qml" in l and ("Error" in l or "Warning" in l or "Cannot" in l or "TypeError" in l or "ReferenceError" in l)]
    assert not bad, "\n".join(bad)
