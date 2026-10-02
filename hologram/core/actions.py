"""Aksi yang boleh dilakukan AI terhadap tampilan, dan penguraian balasan JSON dari model."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

ACTIONS = ("zoom_in", "zoom_out", "rotate", "load_model", "list_models", "reply")
DIRECTIONS = {
    "right": "right", "kanan": "right", "left": "left", "kiri": "left",
    "up": "up", "atas": "up", "down": "down", "bawah": "down",
}
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

# Teks bawaan aplikasi (dipakai kalau AI tidak menulis balasan sendiri), per bahasa.
_T = {
    "id": {
        "zoom_in": "Zoom in.", "zoom_out": "Zoom out.", "rotate": "Memutar model.",
        "rotate_bad": "Arah putar tidak jelas. Sebut kanan, kiri, atas, atau bawah.",
        "shown": "Menampilkan {name}.", "missing": 'Model "{name}" tidak ada.', "missing_anon": "Model itu tidak ada.",
        "listing": "Model yang tersedia: {names}.", "none": "Belum ada model 3D di assets/models.",
        "empty": "Model AI tidak memberi jawaban yang bisa ditampilkan. Coba ulangi, atau ganti model AI di dropdown.",
    },
    "en": {
        "zoom_in": "Zooming in.", "zoom_out": "Zooming out.", "rotate": "Rotating the model.",
        "rotate_bad": "The direction is unclear. Say left, right, up, or down.",
        "shown": "Showing {name}.", "missing": 'There is no model called "{name}".', "missing_anon": "There is no such model.",
        "listing": "Available models: {names}.", "none": "There are no 3D models in assets/models yet.",
        "empty": "The AI model gave no usable answer. Try again, or switch the AI model in the dropdown.",
    },
}


@dataclass
class Command:
    action: str = "reply"
    args: dict[str, Any] = field(default_factory=dict)
    reply: str = ""


@dataclass
class ActionResult:
    text: str


class ViewPort(Protocol):
    def zoom_in(self) -> None: ...
    def zoom_out(self) -> None: ...
    def rotate(self, direction: str) -> None: ...
    def show_model(self, entry: Any) -> None: ...


def _first_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


def parse_command(raw: str) -> Command | None:
    """Ambil objek JSON pertama dari keluaran model. None kalau tidak ada yang bisa dipakai."""
    text = _THINK.sub("", raw or "").strip()
    blob = _first_json_object(text)
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "reply").strip().lower()
    reply = str(data.get("reply") or data.get("text") or data.get("message") or "").strip()
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    if not args:
        args = {k: data[k] for k in ("name", "model", "direction", "mode", "answer") if k in data}
    if action not in ACTIONS:
        if not reply:
            return None
        action = "reply"
    if "direction" in args:
        args["direction"] = DIRECTIONS.get(str(args["direction"]).lower(), args["direction"])
    return Command(action, args, reply)


class ActionRunner:
    """Menjalankan Command. `view` dan `registry` diberikan oleh Controller."""

    def __init__(self, registry: Any, view: ViewPort) -> None:
        self.registry = registry
        self.view = view

    def run(self, cmd: Command, lang: str = "id") -> ActionResult:
        act = cmd.action
        t = _T.get(lang, _T["id"])
        if act == "zoom_in":
            self.view.zoom_in()
            return ActionResult(cmd.reply or t["zoom_in"])
        if act == "zoom_out":
            self.view.zoom_out()
            return ActionResult(cmd.reply or t["zoom_out"])
        if act == "rotate":
            direction = cmd.args.get("direction")
            if direction not in ("left", "right", "up", "down"):
                return ActionResult(cmd.reply or t["rotate_bad"])
            self.view.rotate(direction)
            return ActionResult(cmd.reply or t["rotate"])
        if act == "load_model":
            return self._load(cmd, t)
        if act == "list_models":
            return ActionResult(self._listing(t))
        return ActionResult(cmd.reply or t["empty"])

    def _load(self, cmd: Command, t: dict) -> ActionResult:
        name = str(cmd.args.get("name") or cmd.args.get("model") or "").strip()
        entry = self.registry.find(name) if name else None
        if entry is None:
            label = t["missing"].format(name=name) if name else t["missing_anon"]
            return ActionResult(f"{label} {self._listing(t)}")
        self.view.show_model(entry)
        return ActionResult(cmd.reply or t["shown"].format(name=entry.name))

    def _listing(self, t: dict) -> str:
        names = self.registry.names()
        if not names:
            return t["none"]
        return t["listing"].format(names=", ".join(names))