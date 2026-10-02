"""Daftar model 3D dari assets/models.json. Model baru cukup ditambah di JSON dan folder models."""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Kata perintah yang dibuang sebelum mencocokkan nama model.
_NOISE = {
    "ganti", "ubah", "ke", "model", "tampilkan", "munculkan", "perlihatkan", "buka", "lihat",
    "show", "load", "switch", "change", "to", "the", "dong", "tolong", "saya", "aku", "minta",
    "yang", "sebuah", "3d", "menjadi", "jadi", "pakai", "gunakan", "display", "please",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


@dataclass(frozen=True)
class ModelEntry:
    id: str
    name: str
    aliases: tuple[str, ...]
    category: str
    country: str | None
    kind: str
    file: str
    description: str
    license: str
    source: str

    @property
    def label(self) -> str:
        return self.name

    def keys(self) -> list[str]:
        return [normalize(k) for k in (self.id, self.name, *self.aliases)]

    def summary(self) -> str:
        parts = [f"{self.name} (id: {self.id})", f"kategori: {self.category}", f"jenis: {self.kind}"]
        parts.append(f"negara: {self.country}" if self.country else "negara: tidak dicatat")
        return "; ".join(parts) + f". {self.description}"


class ModelRegistry:
    def __init__(self, json_path: Path, models_dir: Path) -> None:
        self.models_dir = models_dir
        self.entries: list[ModelEntry] = []
        self.skipped: list[str] = []
        self._load(json_path)

    def _load(self, json_path: Path) -> None:
        if not json_path.exists():
            return
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        for item in raw.get("models", []):
            entry = ModelEntry(
                id=item["id"], name=item.get("name", item["id"]),
                aliases=tuple(item.get("aliases", ())), category=item.get("category", ""),
                country=item.get("country"), kind=item.get("kind", ""), file=item["file"],
                description=item.get("description", ""), license=item.get("license", ""),
                source=item.get("source", ""),
            )
            if (self.models_dir / entry.file).exists():
                self.entries.append(entry)
            else:
                self.skipped.append(entry.id)

    def all(self) -> list[ModelEntry]:
        return list(self.entries)

    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def get(self, model_id: str) -> ModelEntry | None:
        return next((e for e in self.entries if e.id == model_id), None)

    def path(self, entry: ModelEntry) -> Path:
        return self.models_dir / entry.file

    def find(self, query: str) -> ModelEntry | None:
        """Cari lewat id, nama, atau alias. Kata perintah ("ganti ke") diabaikan."""
        cleaned = " ".join(w for w in normalize(query).split() if w not in _NOISE)
        if not cleaned or not self.entries:
            return None
        for entry in self.entries:
            if cleaned in entry.keys():
                return entry
        contained: list[tuple[int, ModelEntry]] = []
        for entry in self.entries:
            for key in entry.keys():
                if key and re.search(rf"\b{re.escape(key)}\b", cleaned):
                    contained.append((len(key), entry))
        if contained:
            return max(contained, key=lambda pair: pair[0])[1]
        pool = {key: entry for entry in self.entries for key in entry.keys() if key}
        close = difflib.get_close_matches(cleaned, list(pool), n=1, cutoff=0.78)
        return pool[close[0]] if close else None
