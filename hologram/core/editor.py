"""Editor kode sederhana di dalam aplikasi: lihat folder proyek, buka file teks, ubah, simpan.

Sengaja dibuat sederhana (bukan IDE penuh): tidak ada penyorotan sintaks, pencarian, atau banyak tab.
Yang penting bisa melihat struktur folder proyek dan mengubah sebuah file tanpa pindah ke editor lain.

Semua path dibatasi ketat ke dalam folder proyek (ROOT), supaya tidak bisa membaca atau menimpa file
lain di komputer lewat "../../" atau path absolut.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..config import ROOT

MAX_SIZE = 2_000_000   # 2 MB: di atas ini dianggap bukan file teks yang wajar dibuka di editor kecil ini
SKIP_NAMES = {
    "__pycache__", ".git", ".pytest_cache", "venv", ".venv", "node_modules", ".vscode", ".mypy_cache",
}


def _safe_path(rel: str) -> Path:
    """Gabungkan path relatif ke ROOT, dan tolak kalau hasilnya keluar dari ROOT (lawan "..", path absolut)."""
    rel = (rel or "").strip().replace("\\", "/")
    if rel.startswith("/") or ":" in rel:
        raise ValueError("path tidak valid")
    root = ROOT.resolve()
    target = (root / rel).resolve() if rel else root
    if target != root and root not in target.parents:
        raise ValueError("path di luar folder proyek")
    return target


def _entry(path: Path) -> dict:
    return {"name": path.name, "path": path.relative_to(ROOT).as_posix(), "isDir": path.is_dir()}


def list_dir(rel: str) -> list[dict]:
    base = _safe_path(rel)
    if not base.is_dir():
        return []
    items = [p for p in base.iterdir() if p.name not in SKIP_NAMES and not p.name.startswith(".")]
    items.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    return [_entry(p) for p in items]


def read_file(rel: str) -> str:
    path = _safe_path(rel)
    if not path.is_file():
        raise ValueError("bukan file")
    if path.stat().st_size > MAX_SIZE:
        raise ValueError("file terlalu besar untuk dibuka di sini")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file ini bukan teks biasa (biner)") from exc


def write_file(rel: str, content: str) -> None:
    path = _safe_path(rel)
    if path.is_dir():
        raise ValueError("itu folder, bukan file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ProjectEditor(QObject):
    """Dipakai QML sebagai `editor`. Semua operasi file lewat sini, bukan langsung dari QML."""

    errorOccurred = Signal(str)
    fileOpened = Signal(str, str)     # (path relatif, isi file)
    fileSaved = Signal(str)           # (path relatif)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    @Property(str, constant=True)
    def rootName(self) -> str:
        return ROOT.name

    @Slot(str, result=list)
    def listDir(self, rel: str) -> list:
        try:
            return list_dir(rel)
        except Exception as exc:
            self.errorOccurred.emit(f"Tidak bisa membuka folder: {exc}")
            return []

    @Slot(str)
    def openFile(self, rel: str) -> None:
        try:
            content = read_file(rel)
        except Exception as exc:
            self.errorOccurred.emit(f'Tidak bisa membuka "{rel}": {exc}')
            return
        self.fileOpened.emit(rel, content)

    @Slot(str, str)
    def saveFile(self, rel: str, content: str) -> None:
        try:
            write_file(rel, content)
        except Exception as exc:
            self.errorOccurred.emit(f'Tidak bisa menyimpan "{rel}": {exc}')
            return
        self.fileSaved.emit(rel)
