"""Impor OpenCV yang aman untuk PySide6.

Paket opencv-contrib-python (dibawa mediapipe) menimpa QT_QPA_PLATFORM_PLUGIN_PATH saat
di-import dan bisa merusak plugin Qt milik PySide6. OpenCV di-import belakangan, dan
variabel itu dikembalikan seperti semula. Lihat README untuk cara membuang paket contrib.
"""
from __future__ import annotations

import os
from functools import lru_cache
from types import ModuleType

_VAR = "QT_QPA_PLATFORM_PLUGIN_PATH"


@lru_cache(maxsize=1)
def load_cv2() -> ModuleType:
    saved = os.environ.get(_VAR)
    try:
        import cv2
    finally:
        if saved is None:
            os.environ.pop(_VAR, None)
        else:
            os.environ[_VAR] = saved
    return cv2
