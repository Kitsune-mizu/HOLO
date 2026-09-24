"""Properti yang dilihat QML. Hanya data dan sinyal perubahan, tanpa logika."""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


def _get(name: str):
    return lambda self: self._v[name]


class AppState(QObject):
    modeChanged = Signal()
    netOnlineChanged = Signal()
    aiInfoChanged = Signal()
    busyChanged = Signal()
    speakingChanged = Signal()
    listeningChanged = Signal()
    levelChanged = Signal()
    voiceEnabledChanged = Signal()
    cameraStatusChanged = Signal()
    cameraFrameChanged = Signal()
    handStateChanged = Signal()
    cameraOnChanged = Signal()
    gestureChanged = Signal()
    ramTextChanged = Signal()
    shapeNameChanged = Signal()
    modelSourceChanged = Signal()
    optionsChanged = Signal()
    optionHeaderChanged = Signal()
    selectedOptionChanged = Signal()
    dropdownAvailableChanged = Signal()

    mode = Property(str, _get("mode"), notify=modeChanged)
    netOnline = Property(bool, _get("netOnline"), notify=netOnlineChanged)
    aiInfo = Property(str, _get("aiInfo"), notify=aiInfoChanged)
    busy = Property(bool, _get("busy"), notify=busyChanged)
    speaking = Property(bool, _get("speaking"), notify=speakingChanged)
    listening = Property(bool, _get("listening"), notify=listeningChanged)
    level = Property(float, _get("level"), notify=levelChanged)
    voiceEnabled = Property(bool, _get("voiceEnabled"), notify=voiceEnabledChanged)
    cameraStatus = Property(str, _get("cameraStatus"), notify=cameraStatusChanged)
    cameraOn = Property(bool, _get("cameraOn"), notify=cameraOnChanged)
    cameraFrame = Property(int, _get("cameraFrame"), notify=cameraFrameChanged)
    handState = Property(str, _get("handState"), notify=handStateChanged)
    gesture = Property(str, _get("gesture"), notify=gestureChanged)
    ramText = Property(str, _get("ramText"), notify=ramTextChanged)
    shapeName = Property(str, _get("shapeName"), notify=shapeNameChanged)
    modelSource = Property(str, _get("modelSource"), notify=modelSourceChanged)
    options = Property(list, _get("options"), notify=optionsChanged)
    optionHeader = Property(list, _get("optionHeader"), notify=optionHeaderChanged)
    selectedOption = Property(str, _get("selectedOption"), notify=selectedOptionChanged)
    dropdownAvailable = Property(bool, _get("dropdownAvailable"), notify=dropdownAvailableChanged)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._v: dict = {
            "mode": "offline", "netOnline": False, "aiInfo": "", "busy": False, "speaking": False,
            "listening": False, "level": 0.0, "voiceEnabled": True, "cameraStatus": "", "cameraOn": False, "cameraFrame": 0,
            "handState": "none", "gesture": "", "ramText": "", "shapeName": "", "modelSource": "",
            "options": [], "optionHeader": [], "selectedOption": "auto", "dropdownAvailable": False,
        }

    def _set(self, name: str, value) -> None:
        if self._v[name] != value:
            self._v[name] = value
            getattr(self, f"{name}Changed").emit()

    def get(self, name: str):
        return self._v[name]