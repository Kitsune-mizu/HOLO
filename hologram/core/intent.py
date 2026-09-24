"""Jaring pengaman: mengenali perintah sederhana lewat kata kunci kalau model kecil salah format."""
from __future__ import annotations

import re

from .actions import DIRECTIONS, Command

_QUESTION = {"apa", "siapa", "kenapa", "mengapa", "bagaimana", "gimana", "berapa", "kapan", "dimana", "what", "who", "why", "how"}
_ZOOM_IN = ("zoom in", "zoom masuk", "zoomin", "perbesar", "memperbesar", "besarkan", "dekatkan", "lebih dekat")
_ZOOM_OUT = ("zoom out", "zoom keluar", "zoomout", "perkecil", "memperkecil", "kecilkan", "jauhkan", "lebih jauh")
_LIST = (
    "model apa saja", "apa saja model", "daftar model", "list model", "list models", "model yang tersedia",
    "model apa yang ada", "ada model apa", "model apa yang tersedia", "available models", "what models",
)
_ROTATE = ("putar", "rotasi", "rotate", "miringkan", "turn")
_LOAD = re.compile(r"^(?:tolong |please )?(?:ganti|ubah|tampilkan|munculkan|perlihatkan|buka|lihat|show|load|switch|change|display)\b(.*)$")
_MODE_VERB = re.compile(r"\b(pindah|ganti|ubah|mode|pakai|gunakan|switch|go|use|ke)\b")
_ANSWER = re.compile(r"\b(jelaskan|jawab|cari|carikan|tanya|explain|search|apa|siapa|bagaimana|kenapa)\b")
LIGHT = {"zoom_in", "zoom_out", "rotate", "load_model", "list_models"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def guess(text: str) -> Command | None:
    t = _clean(text)
    if not t:
        return None
    if any(p in t for p in _LIST):
        return Command("list_models")

    mode = _mode_command(t)
    if mode:
        return mode
    if t.split()[0] in _QUESTION:
        return None

    if any(w in t.split() for w in _ROTATE):
        for word in t.split():
            if word in DIRECTIONS:
                return Command("rotate", {"direction": DIRECTIONS[word]})
        return None
    if any(p in t for p in _ZOOM_IN):
        return Command("zoom_in")
    if any(p in t for p in _ZOOM_OUT):
        return Command("zoom_out")

    match = _LOAD.match(t)
    if match:
        name = " ".join(w for w in match.group(1).split() if w not in ("ke", "model", "jadi", "menjadi"))
        if name:
            return Command("load_model", {"name": name})
    return None


def _mode_command(t: str) -> Command | None:
    words = set(t.split())
    if "online" in words and "offline" not in words:
        mode = "online"
    elif "offline" in words and "online" not in words:
        mode = "offline"
    else:
        return None
    if not _MODE_VERB.search(t):
        return None
    rest = " ".join(w for w in t.split() if w not in ("online", "offline"))
    wants_answer = mode == "online" and bool(_ANSWER.search(rest))
    return Command("switch_mode", {"mode": mode, "answer": wants_answer})


def is_light(text: str) -> bool:
    cmd = guess(text)
    return cmd is not None and cmd.action in LIGHT
