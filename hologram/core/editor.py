"""Editor kode sederhana di dalam aplikasi: lihat folder proyek, buka file teks, ubah, simpan, terapkan."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from PySide6.QtCore import Property, QCoreApplication, QObject, QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from ..config import ROOT, UI_DIR

MAX_SIZE = 2_000_000
SKIP_NAMES = {
    "__pycache__", ".git", ".pytest_cache", "venv", ".venv", "node_modules", ".vscode", ".mypy_cache",
    ".idea", ".DS_Store",
}
QML_APPLY_DELAY_MS = 120
RESTART_APPLY_DELAY_MS = 500


def _safe_path(rel: str) -> Path:
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
    items = [p for p in base.iterdir() if p.name not in SKIP_NAMES]
    items.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    return [_entry(p) for p in items]


def read_file(rel: str) -> str:
    path = _safe_path(rel)
    if not path.is_file():
        raise ValueError("bukan file")
    if path.stat().st_size > MAX_SIZE:
        raise ValueError("file terlalu besar untuk dibuka di sini")
    
    # Deteksi cepat file biner (menghindari alokasi memori berlebih)
    try:
        with open(path, "rb") as f:
            if b"\x00" in f.read(1024):
                raise ValueError("file ini adalah file biner (bukan teks biasa)")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise exc

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("file ini bukan teks biasa (encoding non-UTF8)") from exc


def write_file(rel: str, content: str) -> None:
    path = _safe_path(rel)
    if path.is_dir():
        raise ValueError("itu folder, bukan file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SimpleHighlighter(QSyntaxHighlighter):
    """Syntax highlighter bergaya VS Code Dark+ untuk Python/QML/JS/JSON/TOML."""

    def __init__(self, parent: QTextDocument):
        super().__init__(parent)
        self.rules = []

        # Formats
        self.keyword_fmt = QTextCharFormat(); self.keyword_fmt.setForeground(QColor("#C586C0"))
        self.control_fmt = QTextCharFormat(); self.control_fmt.setForeground(QColor("#C586C0"))
        self.builtin_fmt = QTextCharFormat(); self.builtin_fmt.setForeground(QColor("#4EC9B0"))
        self.function_fmt = QTextCharFormat(); self.function_fmt.setForeground(QColor("#DCDCAA"))
        self.class_fmt = QTextCharFormat(); self.class_fmt.setForeground(QColor("#4EC9B0"))
        self.decorator_fmt = QTextCharFormat(); self.decorator_fmt.setForeground(QColor("#DCDCAA"))
        self.string_fmt = QTextCharFormat(); self.string_fmt.setForeground(QColor("#CE9178"))
        self.number_fmt = QTextCharFormat(); self.number_fmt.setForeground(QColor("#B5CEA8"))
        self.constant_fmt = QTextCharFormat(); self.constant_fmt.setForeground(QColor("#569CD6"))
        self.comment_fmt = QTextCharFormat(); self.comment_fmt.setForeground(QColor("#6A9955")); self.comment_fmt.setFontItalic(True)
        self.operator_fmt = QTextCharFormat(); self.operator_fmt.setForeground(QColor("#D4D4D4"))
        self.env_fmt = QTextCharFormat(); self.env_fmt.setForeground(QColor("#E5C07B"))

        # Keywords & Builtins
        keywords = ["and", "as", "assert", "async", "await", "break", "case", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "match", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]
        control_words = ["if", "elif", "else", "for", "while", "try", "except", "finally", "with", "match", "case"]
        builtins = ["abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray", "bytes", "callable", "chr", "classmethod", "compile", "complex", "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass", "iter", "len", "list", "locals", "map", "max", "memoryview", "min", "next", "object", "oct", "open", "ord", "pow", "print", "property", "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip"]
        constants = ["True", "False", "None", "NotImplemented", "Ellipsis", "self", "cls"]

        # PENTING: urutan di sini menentukan PRIORITAS, bukan cuma urutan eksekusi. Aturan yang
        # didaftarkan lebih dulu "menang" dan tidak akan ditimpa oleh aturan sesudahnya (lihat
        # highlightBlock di bawah) - sebelumnya semua aturan didaftarkan lalu diterapkan mentah
        # tanpa prioritas, jadi aturan umum seperti class_fmt (menangkap SEMUA kata berhuruf besar,
        # termasuk True/False/None yang sudah diwarnai konstanta) atau operator_fmt (menangkap
        # simbol satu-per-satu, termasuk yang ada di dalam string/komentar) dijalankan belakangan
        # dan menimpa warna yang sudah benar - itu sumber tampilan belang-belang/tidak konsisten.
        # Paling spesifik dan paling "berbahaya" kalau salah tangkap (string, komentar) didahulukan,
        # lalu kata kunci/builtin/konstanta, baru terakhir aturan tangkap-umum (class, operator).

        # 1) String (paling spesifik: dalamnya tidak boleh diwarnai ulang oleh aturan lain)
        string_patterns = [r'"""(?:\\.|[^"\\])*"""', r"'''(?:\\.|[^'\\])*'''", r'f"(?:\\.|[^"\\])*"', r"f'(?:\\.|[^'\\])*'", r'r"(?:\\.|[^"\\])*"', r"r'(?:\\.|[^'\\])*'", r'b"(?:\\.|[^"\\])*"', r"b'(?:\\.|[^'\\])*'", r'"(?:\\.|[^"\\])*"', r"'(?:\\.|[^'\\])*'"]
        for p in string_patterns: self.rules.append((re.compile(p), self.string_fmt))

        # 2) Komentar satu baris
        self.rules.append((re.compile(r"#.*"), self.comment_fmt))
        self.rules.append((re.compile(r"//.*"), self.comment_fmt))

        # 3) Dekorator
        self.rules.append((re.compile(r"@[A-Za-z_][A-Za-z0-9_.]*"), self.decorator_fmt))

        # 4) Kata kunci, builtin, konstanta - kata pasti (bukan tangkap-umum)
        for w in keywords: self.rules.append((re.compile(rf"\b{w}\b"), self.keyword_fmt))
        for w in control_words: self.rules.append((re.compile(rf"\b{w}\b"), self.control_fmt))
        for w in builtins: self.rules.append((re.compile(rf"\b{w}\b"), self.builtin_fmt))
        for w in constants: self.rules.append((re.compile(rf"\b{w}\b"), self.constant_fmt))

        # 5) Angka
        number_patterns = [r"\b0[xX][0-9a-fA-F]+\b", r"\b0[bB][01]+\b", r"\b0[oO][0-7]+\b", r"\b\d+\.\d+(?:[eE][+-]?\d+)?\b", r"\b\d+\b"]
        for p in number_patterns: self.rules.append((re.compile(p), self.number_fmt))

        # 6) Nama variabel gaya .env (KEY=value)
        self.rules.append((re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*(?=\s*=)"), self.env_fmt))

        # 7) Tangkap-umum (paling rendah prioritasnya, karena paling gampang salah tangkap kalau
        # dijalankan lebih dulu): panggilan fungsi, nama kelas/konstanta berhuruf besar, operator.
        self.rules.append((re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\s*\()"), self.function_fmt))
        self.rules.append((re.compile(r"\b[A-Z][A-Za-z0-9_]*\b"), self.class_fmt))
        operators = [r"==", r"!=", r"<=", r">=", r"->", r":=", r"\+=", r"-=", r"\*=", r"/=", r"%=", r"\*\*", r"//", r"&&", r"\|\|", r"<<", r">>", r"[+\-*/%=<>!&|^~]"]
        for op in operators: self.rules.append((re.compile(op), self.operator_fmt))

    def highlightBlock(self, text: str) -> None:
        # `painted` melacak karakter mana yang sudah diwarnai di baris ini. Aturan diproses sesuai
        # urutan prioritas (lihat __init__): begitu sebuah karakter sudah diwarnai oleh aturan yang
        # lebih spesifik/lebih diprioritaskan, aturan berikutnya yang lebih umum tidak akan
        # menimpanya lagi - inilah yang menghilangkan tampilan belang-belang sebelumnya.
        painted = bytearray(len(text))
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                i = start
                while i < end:
                    if painted[i]:
                        i += 1
                        continue
                    j = i
                    while j < end and not painted[j]:
                        j += 1
                    self.setFormat(i, j - i, fmt)
                    for k in range(i, j):
                        painted[k] = 1
                    i = j

        # Dukungan Komentar Multi-baris QML/JS (/* ... */)
        self.setCurrentBlockState(0)
        start_idx = 0
        if self.previousBlockState() != 1:
            start_idx = text.find("/*")

        while start_idx >= 0:
            end_idx = text.find("*/", start_idx)
            if end_idx == -1:
                self.setCurrentBlockState(1)
                comment_len = len(text) - start_idx
            else:
                comment_len = end_idx - start_idx + 2

            self.setFormat(start_idx, comment_len, self.comment_fmt)
            start_idx = text.find("/*", start_idx + comment_len)


class ProjectEditor(QObject):
    errorOccurred = Signal(str)
    fileOpened = Signal(str, str)
    fileSaved = Signal(str)
    fileSystemChanged = Signal()
    fileDeleted = Signal(str)
    fileRenamed = Signal(str, str)
    logMessage = Signal(str)
    reloading = Signal(bool)

    _FATAL_FILES = {
        "app.py", "main.py", "__init__.py", "core/editor.py", "config.py",
        "hologram/app.py", "hologram/core/editor.py", "hologram/config.py"
    }

    def __init__(self, engine, controller, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._controller = controller

    @Property(str, constant=True)
    def rootName(self) -> str:
        return ROOT.name

    @Slot(QObject)
    def setupHighlighter(self, doc_obj: QObject) -> None:
        get_doc = getattr(doc_obj, "textDocument", None)
        doc = get_doc() if callable(get_doc) else None
        if doc is not None:
            self._highlighter = SimpleHighlighter(cast(QTextDocument, doc))

    def _log(self, message: str) -> None:
        self.logMessage.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    @Slot(str)
    def logUiEvent(self, message: str) -> None:
        if message := (message or "").strip():
            self._log(message)

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

    @Slot(str, result=str)
    def validateFileName(self, rel: str) -> str:
        rel = rel.strip().replace("\\", "/")
        if not rel: return "Nama file tidak boleh kosong."
        if rel.endswith("/"): return "Nama file tidak boleh diakhiri dengan '/'."
        if ".." in rel: return "Nama file tidak boleh mengandung '..'."
        name = rel.split("/")[-1]
        if any(c in name for c in '<>:"/\\|?*'): return "Nama file mengandung karakter yang tidak valid."
        return ""

    @Slot(str)
    def createFile(self, rel: str) -> None:
        rel = rel.strip().replace("\\", "/")
        if err := self.validateFileName(rel):
            self.errorOccurred.emit(err); self._log(err); return
        if rel.split("/")[-1].endswith("."):
            self._log(f'Batal membuat file "{rel}": nama file berakhir dengan titik tanpa ekstensi.'); return

        path = _safe_path(rel)
        if path.exists():
            msg = f'"{rel}" sudah ada.'; self.errorOccurred.emit(msg); self._log(msg); return

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        except Exception as exc:
            msg = f'Tidak bisa membuat "{rel}": {exc}'; self.errorOccurred.emit(msg); self._log(msg); return

        self._log(f"File dibuat: {rel}")
        self.fileSaved.emit(rel)
        self.fileSystemChanged.emit()

    @Slot(str, str)
    def importFile(self, source_url: str, dest_rel: str) -> None:
        source_path = Path(QUrl(source_url).toLocalFile())
        if not source_path.is_file():
            self._log(f"Gagal impor: {source_path} bukan file"); return

        dest_rel = dest_rel.strip()
        if not dest_rel: dest_rel = source_path.name
        elif dest_rel.endswith("/") or dest_rel.endswith("\\"): dest_rel += source_path.name

        dest_path = _safe_path(dest_rel)
        if dest_path.exists():
            msg = f'"{dest_rel}" sudah ada. Gagal impor.'; self.errorOccurred.emit(msg); self._log(msg); return

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
        except Exception as exc:
            msg = f'Tidak bisa mengimpor ke "{dest_rel}": {exc}'; self.errorOccurred.emit(msg); self._log(msg); return

        self._log(f"File diimpor: {dest_rel}")
        self.fileSaved.emit(dest_rel)
        self.fileSystemChanged.emit()

    @Slot(str, result=str)
    def validateFolderName(self, rel: str) -> str:
        rel = rel.strip()
        if not rel: return "Nama folder tidak boleh kosong."
        if ".." in rel: return "Nama folder tidak boleh mengandung '..'"
        name = rel.split("/")[-1].split("\\")[-1]
        if any(c in name for c in '<>:"/\\|?*'): return "Nama folder mengandung karakter yang tidak valid."
        return ""

    @Slot(str)
    def createFolder(self, rel: str) -> None:
        if err := self.validateFolderName(rel):
            self.errorOccurred.emit(err); self._log(err); return
        path = _safe_path(rel)
        if path.exists():
            msg = f'Folder "{rel}" sudah ada.'; self.errorOccurred.emit(msg); self._log(msg); return
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            msg = f'Tidak bisa membuat folder "{rel}": {exc}'; self.errorOccurred.emit(msg); self._log(msg); return
        self._log(f"Folder dibuat: {rel}")
        self.fileSystemChanged.emit()

    @Slot(str, result=bool)
    def isProtectedFile(self, rel: str) -> bool:
        rel_posix = Path(rel).as_posix()
        name = rel_posix.split("/")[-1]
        return name in self._FATAL_FILES or rel_posix in self._FATAL_FILES

    @Slot(str, result=str)
    def getDeleteWarning(self, rel: str) -> str:
        rel_posix = Path(rel).as_posix()
        name = rel_posix.split("/")[-1]
        is_fatal = name in self._FATAL_FILES or rel_posix in self._FATAL_FILES
        usages = self._find_usages(rel_posix)

        msg = f'Apakah Anda yakin ingin menghapus "{rel}"?'
        if is_fatal:
            msg += "\n\n[PERINGATAN KRITIS]: File ini adalah komponen inti sistem. Menghapusnya dapat menyebabkan aplikasi gagal berfungsi!"
        elif usages:
            preview = ", ".join(usages[:3])
            more = f" (+{len(usages) - 3} lainnya)" if len(usages) > 3 else ""
            msg += f"\n\n[PERINGATAN]: File ini terdeteksi direferensikan pada: {preview}{more}."
        return msg

    @Slot(str, str, result=str)
    def getRenameWarning(self, old_rel: str, new_name: str) -> str:
        old_rel_posix = Path(old_rel).as_posix()
        name = old_rel_posix.split("/")[-1]
        if name in self._FATAL_FILES or old_rel_posix in self._FATAL_FILES:
            return f'File inti "{name}" dilindungi dan tidak boleh diubah namanya.'

        usages = self._find_usages(old_rel_posix)
        if not usages: return ""

        preview = ", ".join(usages[:3])
        more = f" (+{len(usages) - 3} lainnya)" if len(usages) > 3 else ""
        return f'"{old_rel}" sedang digunakan/direferensikan oleh: {preview}{more}.\n\nRename dapat membuat referensi tersebut tidak bekerja sampai diperbarui. Lanjutkan?'

    @Slot(str, str)
    def renameFile(self, old_rel: str, new_name: str) -> None:
        old_path = _safe_path(old_rel)
        if not old_path.exists(): return
        new_name = new_name.strip()
        if not new_name or "/" in new_name or "\\" in new_name:
            err = "Nama baru tidak valid."; self.errorOccurred.emit(err); self._log(err); return

        old_rel_posix = Path(old_rel).as_posix()
        old_name = old_rel_posix.split("/")[-1]
        if old_name in self._FATAL_FILES or old_rel_posix in self._FATAL_FILES:
            msg = f'Batal: File inti "{old_name}" dilindungi dan tidak boleh di-rename.'; self.errorOccurred.emit(msg); self._log(msg); return

        new_path = old_path.parent / new_name
        if new_path.exists():
            err = f'Nama "{new_name}" sudah dipakai.'; self.errorOccurred.emit(err); self._log(err); return

        try:
            old_path.rename(new_path)
        except Exception as exc:
            err = f"Gagal mengubah nama: {exc}"; self.errorOccurred.emit(err); self._log(err); return

        new_rel = (new_path.relative_to(ROOT)).as_posix()
        self._log(f"Diubah nama: {old_rel} -> {new_name}")
        self.fileRenamed.emit(old_rel, new_rel)
        self.fileSystemChanged.emit()

    @Slot(str, bool)
    def deleteFile(self, rel: str, force: bool = False) -> None:
        path = _safe_path(rel)
        if not path.exists(): return

        rel_posix = Path(rel).as_posix()
        name = rel_posix.split("/")[-1]
        is_fatal = name in self._FATAL_FILES or rel_posix in self._FATAL_FILES

        if is_fatal and not force:
            usages = self._find_usages(rel_posix)
            msg = f'Batal: "{name}" adalah file inti. Centang konfirmasi di dialog jika Anda tetap yakin ingin menghapusnya.'
            self.errorOccurred.emit(msg); self._log(msg); return

        try:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
        except Exception as exc:
            err = f"Gagal menghapus: {exc}"; self.errorOccurred.emit(err); self._log(err); return

        if is_fatal and force: self._log(f"PERHATIAN: file inti dihapus paksa: {rel}")
        else: self._log(f"Dihapus: {rel}")
        self.fileDeleted.emit(rel)
        self.fileSystemChanged.emit()

    def _find_usages(self, rel: str) -> list[str]:
        name = rel.split("/")[-1]
        results: list[str] = []
        skip = SKIP_NAMES | {".git"}
        valid_extensions = {".py", ".qml", ".json", ".toml", ".txt", ".md", ".js", ".css"}
        try:
            for p in ROOT.rglob("*"):
                if p.is_dir() or p.name.startswith(".") or any(s in p.parts for s in skip): continue
                if p.suffix.lower() not in valid_extensions or p.stat().st_size > 200_000: continue
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    if name in text or rel in text: results.append(p.relative_to(ROOT).as_posix())
                except Exception: pass
                if len(results) >= 10: break
        except Exception: pass
        return results

    @Slot(str, str)
    def saveFile(self, rel: str, content: str) -> None:
        if not self._write(rel, content): return
        self.fileSaved.emit(rel)
        self._log(f"Tersimpan: {rel}")

    @Slot(str, str)
    def applyFile(self, rel: str, content: str) -> None:
        if problem := self._validate(rel, content):
            self.errorOccurred.emit(problem); self._log(problem); return
        if not self._write(rel, content): return

        self.fileSaved.emit(rel)
        self._log(f"Tersimpan: {rel}")

        if rel.endswith(".qml"):
            self.reloading.emit(True)
            self._log("Memuat ulang tampilan (QML)...")
            QTimer.singleShot(QML_APPLY_DELAY_MS, self._reload_qml)
        else:
            self.reloading.emit(True)
            self._log("Perubahan pada file ini perlu memulai ulang aplikasi. Memulai ulang...")
            QTimer.singleShot(RESTART_APPLY_DELAY_MS, self._restart_app)

    @staticmethod
    def _validate(rel: str, content: str) -> str | None:
        lower = rel.lower()
        try:
            if lower.endswith(".toml"): tomllib.loads(content)
            elif lower.endswith(".json"): json.loads(content)
            elif lower.endswith(".py"): compile(content, rel, "exec")
        except tomllib.TOMLDecodeError as exc:
            return f'"{rel}" tidak valid, tidak jadi disimpan: {exc}'
        except json.JSONDecodeError as exc:
            return f'"{rel}" tidak valid, tidak jadi disimpan: baris {exc.lineno}, kolom {exc.colno} - {exc.msg}'
        except SyntaxError as exc:
            where = f"baris {exc.lineno}" + (f", kolom {exc.offset}" if exc.offset else "")
            return f'"{rel}" tidak valid, tidak jadi disimpan: {where} - {exc.msg}'
        return None

    def _write(self, rel: str, content: str) -> bool:
        try:
            write_file(rel, content)
        except Exception as exc:
            msg = f'Tidak bisa menyimpan "{rel}": {exc}'; self.errorOccurred.emit(msg); self._log(msg); return False
        return True

    def _reload_qml(self) -> None:
        old_roots = list(self._engine.rootObjects())
        try:
            self._engine.clearComponentCache()
            self._engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
        except Exception as exc:
            self._log(f"Gagal memuat ulang QML: {exc}"); self.errorOccurred.emit(f"Gagal memuat ulang tampilan: {exc}"); self.reloading.emit(False); return

        new_roots = [r for r in self._engine.rootObjects() if r not in old_roots]
        if not new_roots:
            self._log("Gagal memuat ulang QML (kemungkinan ada galat sintaks). Tampilan lama dipertahankan.")
            self.errorOccurred.emit("QML tidak valid, tampilan lama dipertahankan. Periksa lagi filenya.")
            self.reloading.emit(False)
            return

        for r in old_roots:
            try: r.close()
            except Exception: pass
            r.deleteLater()

        self._log("Tampilan berhasil dimuat ulang.")
        self.reloading.emit(False)

    def _restart_app(self) -> None:
        self._log("Menutup thread yang berjalan sebelum memulai ulang...")
        try:
            self._controller.shutdown()
        except Exception as exc:
            self._log(f"Peringatan saat menutup: {exc}")

        args = self._relaunch_args()
        QProcess.startDetached(args[0], args[1:])
        QCoreApplication.quit()

    @staticmethod
    def _relaunch_args() -> list[str]:
        extra_args = sys.argv[1:]
        if getattr(sys, "frozen", False):
            return [sys.executable] + extra_args
        return [sys.executable, "-m", "hologram"] + extra_args