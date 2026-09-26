"""Editor kode sederhana di dalam aplikasi: lihat folder proyek, buka file teks, ubah, simpan, terapkan.

Sengaja dibuat sederhana (bukan IDE penuh): tidak ada penyorotan sintaks, pencarian, atau banyak tab.
Yang penting bisa melihat struktur folder proyek dan mengubah sebuah file tanpa pindah ke editor lain.

Ada dua cara menyimpan:
- **Simpan**: hanya menulis ke disk. File berubah, tapi aplikasi yang sedang berjalan belum tahu
  (kode Python yang sudah dimuat tetap versi lama sampai aplikasi ditutup dan dibuka lagi).
- **Simpan & Terapkan**: menulis ke disk, LALU membuat perubahan itu benar-benar berlaku sekarang juga:
    - File `.qml` dimuat ulang langsung di tempat (tampilan diperbarui dalam sepersekian detik, tanpa
      menutup aplikasi, karena Qt memang mendukung memuat ulang QML dengan aman saat aplikasi jalan).
    - File lain (`.py`, `config.toml`, dll) TIDAK aman dimuat ulang sebagian saat aplikasi jalan --
      kode Python yang sudah aktif (thread kamera, AI, dan lainnya) tidak bisa ditukar diam-diam tanpa
      risiko rusak. Jadi untuk file jenis ini, "Terapkan" berarti me-restart aplikasi secara otomatis
      (proses Python ini mengganti dirinya sendiri dengan proses baru yang membaca ulang semua file),
      sehingga tidak perlu kembali ke terminal untuk menjalankan ulang secara manual.

Semua path dibatasi ketat ke dalam folder proyek (ROOT), supaya tidak bisa membaca atau menimpa file
lain di komputer lewat "../../" atau path absolut.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from ..config import ROOT, UI_DIR

MAX_SIZE = 2_000_000   # 2 MB: di atas ini dianggap bukan file teks yang wajar dibuka di editor kecil ini
SKIP_NAMES = {
    "__pycache__", ".git", ".pytest_cache", "venv", ".venv", "node_modules", ".vscode", ".mypy_cache",
}
QML_APPLY_DELAY_MS = 120     # jeda kecil supaya overlay "menerapkan" sempat tergambar sebelum reload QML
RESTART_APPLY_DELAY_MS = 500  # jeda sebelum proses di-restart, supaya overlay "menerapkan" sempat terlihat


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
    fileSaved = Signal(str)           # (path relatif) -- ditulis ke disk, belum tentu diterapkan
    logMessage = Signal(str)          # satu baris log berstempel waktu, untuk panel log kecil di UI
    reloading = Signal(bool)          # True: mulai menerapkan (tampilkan overlay). False: selesai/batal.

    def __init__(self, engine, controller, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._controller = controller

    @Property(str, constant=True)
    def rootName(self) -> str:
        return ROOT.name

    def _log(self, message: str) -> None:
        self.logMessage.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    @Slot(str, result=list)
    def listDir(self, rel: str) -> list:
        try:
            return list_dir(rel)
        except Exception as exc:
            msg = f"Tidak bisa membuka folder: {exc}"
            self.errorOccurred.emit(msg)
            self._log(msg)
            return []

    @Slot(str)
    def openFile(self, rel: str) -> None:
        try:
            content = read_file(rel)
        except Exception as exc:
            msg = f'Tidak bisa membuka "{rel}": {exc}'
            self.errorOccurred.emit(msg)
            self._log(msg)
            return
        self.fileOpened.emit(rel, content)
        self._log(f"Membuka {rel}")

    @Slot(str, str)
    def saveFile(self, rel: str, content: str) -> None:
        """Simpan saja: tulis ke disk. Aplikasi yang sedang jalan tidak diberi tahu."""
        if not self._write(rel, content):
            return
        self.fileSaved.emit(rel)
        self._log(f"Tersimpan: {rel}")

    @Slot(str, str)
    def applyFile(self, rel: str, content: str) -> None:
        """Simpan LALU terapkan sekarang juga (lihat penjelasan di docstring modul)."""
        if not self._write(rel, content):
            return
        self.fileSaved.emit(rel)
        self._log(f"Tersimpan: {rel}")

        if rel.endswith(".qml"):
            self.reloading.emit(True)
            self._log("Memuat ulang tampilan (QML)...")
            QTimer.singleShot(QML_APPLY_DELAY_MS, self._reload_qml)
        else:
            self.reloading.emit(True)
            self._log("Perubahan pada file ini perlu memulai ulang aplikasi supaya berlaku. Memulai ulang...")
            QTimer.singleShot(RESTART_APPLY_DELAY_MS, self._restart_app)

    def _write(self, rel: str, content: str) -> bool:
        try:
            write_file(rel, content)
        except Exception as exc:
            msg = f'Tidak bisa menyimpan "{rel}": {exc}'
            self.errorOccurred.emit(msg)
            self._log(msg)
            return False
        return True

    def _reload_qml(self) -> None:
        """Muat ulang seluruh antarmuka dari berkas QML di disk, tanpa menutup aplikasi.

        Window baru dimuat DULU, baru window lama ditutup -- kalau dibalik, ada sesaat tanpa
        window sama sekali, dan beberapa versi Qt menganggap itu sinyal untuk keluar aplikasi.
        """
        old_roots = list(self._engine.rootObjects())
        try:
            self._engine.clearComponentCache()
            self._engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
        except Exception as exc:
            self._log(f"Gagal memuat ulang QML: {exc}")
            self.errorOccurred.emit(f"Gagal memuat ulang tampilan: {exc}")
            self.reloading.emit(False)
            return

        new_roots = [r for r in self._engine.rootObjects() if r not in old_roots]
        if not new_roots:
            self._log("Gagal memuat ulang QML (kemungkinan ada galat sintaks). Tampilan lama dipertahankan.")
            self.errorOccurred.emit("QML tidak valid, tampilan lama dipertahankan. Periksa lagi filenya.")
            self.reloading.emit(False)
            return

        for r in old_roots:
            try:
                r.close()
            except Exception:
                pass
            r.deleteLater()

        self._log("Tampilan berhasil dimuat ulang.")
        self.reloading.emit(False)

    def _restart_app(self) -> None:
        """Ganti proses Python ini sepenuhnya dengan proses baru, supaya semua modul dan konfigurasi
        dibaca ulang dari awal -- persis seperti menutup lalu menjalankan aplikasinya lagi secara
        manual, tapi otomatis."""
        self._log("Menutup thread yang berjalan sebelum memulai ulang...")
        try:
            self._controller.shutdown()
        except Exception as exc:
            self._log(f"Peringatan saat menutup: {exc}")
        args = self._relaunch_args()
        os.execv(args[0], args)

    @staticmethod
    def _relaunch_args() -> list[str]:
        """Susun argumen untuk menjalankan ulang aplikasi ini.

        Aplikasi ini dijalankan dengan `python -m hologram ...`. Saat dijalankan lewat `-m`,
        `sys.argv[0]` TIDAK menyimpan "-m hologram" -- Python sudah menggantinya jadi path absolut
        ke `hologram/__main__.py`. Kalau `os.execv` memakai `sys.argv` apa adanya, proses baru
        menjalankan `__main__.py` langsung sebagai skrip biasa (bukan sebagai bagian dari paket
        `hologram`), dan `from .app import run` di dalamnya gagal dengan "attempted relative
        import with no known parent package". Jadi argumen `-m hologram` disusun ulang secara
        eksplisit, bukan mengandalkan `sys.argv[0]`.
        """
        extra_args = sys.argv[1:]   # mis. --no-camera, --no-voice, --config ...
        if getattr(sys, "frozen", False):
            # Dibungkus jadi satu executable (PyInstaller dkk): jalankan ulang executable itu sendiri.
            return [sys.executable] + extra_args
        return [sys.executable, "-m", "hologram"] + extra_args