import pytest

from hologram.config import ROOT
from hologram.core import editor


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Proyek tiruan kecil, supaya tes tidak menyentuh folder proyek asli."""
    (tmp_path / "hologram").mkdir()
    (tmp_path / "hologram" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01")
    (tmp_path / ".git").mkdir()
    (tmp_path / "config.toml").write_text("[app]\nmode='offline'\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe\x00\x01\x02")
    monkeypatch.setattr(editor, "ROOT", tmp_path)
    return tmp_path


def test_list_dir_skips_hidden_and_cache_folders(project):
    names = {e["name"] for e in editor.list_dir("")}
    assert names == {"hologram", "config.toml", "binary.bin"}
    assert "__pycache__" not in names and ".git" not in names


def test_list_dir_folders_first_then_alphabetical(project):
    (project / "zzz.py").write_text("x", encoding="utf-8")
    (project / "aaa.py").write_text("x", encoding="utf-8")
    entries = editor.list_dir("")
    assert entries[0]["name"] == "hologram" and entries[0]["isDir"] is True
    names = [e["name"] for e in entries if not e["isDir"]]
    assert names == sorted(names, key=str.lower)


def test_list_dir_nested_folder(project):
    entries = editor.list_dir("hologram")
    assert entries == [{"name": "app.py", "path": "hologram/app.py", "isDir": False}]


def test_read_and_write_round_trip(project):
    editor.write_file("hologram/app.py", "print('diubah')\n")
    assert editor.read_file("hologram/app.py") == "print('diubah')\n"


def test_write_creates_missing_parent_folders(project):
    editor.write_file("new/deep/file.txt", "halo")
    assert (project / "new" / "deep" / "file.txt").read_text() == "halo"


def test_read_binary_file_raises_readable_error(project):
    with pytest.raises(ValueError, match="biner"):
        editor.read_file("binary.bin")


def test_read_missing_file_raises(project):
    with pytest.raises(ValueError, match="bukan file"):
        editor.read_file("tidak-ada.txt")


def test_path_traversal_is_rejected(project):
    with pytest.raises(ValueError, match="di luar folder proyek"):
        editor.read_file("../secret.txt")
    with pytest.raises(ValueError, match="di luar folder proyek"):
        editor.write_file("../../etc/passwd", "jahat")


def test_absolute_and_drive_paths_are_rejected(project):
    with pytest.raises(ValueError, match="tidak valid"):
        editor.read_file("/etc/passwd")
    with pytest.raises(ValueError, match="tidak valid"):
        editor.read_file("C:/Windows/system.ini")


def test_write_over_a_directory_is_rejected(project):
    with pytest.raises(ValueError, match="folder"):
        editor.write_file("hologram", "oops")


def test_file_larger_than_limit_is_rejected(project, monkeypatch):
    big = project / "big.txt"
    big.write_text("x")
    monkeypatch.setattr(editor, "MAX_SIZE", 0)
    with pytest.raises(ValueError, match="terlalu besar"):
        editor.read_file("big.txt")


def test_real_project_root_is_listable():
    """Sanity check terhadap folder proyek asli (bukan tiruan), tanpa mengubah apa pun."""
    entries = editor.list_dir("")
    names = {e["name"] for e in entries}
    assert "hologram" in names and "config.toml" in names
    assert ROOT.name in str(ROOT)


# ---------------------------------------------------------------- ProjectEditor (kelas QObject)
from PySide6.QtCore import QCoreApplication  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def pump(ms=50):
    import time as _time

    end = _time.time() + ms / 1000
    while _time.time() < end:
        QCoreApplication.processEvents()
        _time.sleep(0.005)


class FakeRoot:
    def __init__(self):
        self.closed = False
        self.delete_later_called = False

    def close(self):
        self.closed = True

    def deleteLater(self):
        self.delete_later_called = True


class FakeEngine:
    """Meniru QQmlApplicationEngine secukupnya untuk uji _reload_qml, tanpa Qt Quick sungguhan."""

    def __init__(self, succeed=True):
        self._roots = [FakeRoot()]
        self._succeed = succeed
        self.cache_cleared = False
        self.load_calls = 0

    def rootObjects(self):
        return list(self._roots)

    def clearComponentCache(self):
        self.cache_cleared = True

    def load(self, url):
        self.load_calls += 1
        if self._succeed:
            self._roots.append(FakeRoot())   # window baru berhasil dibuat


class FakeController:
    def __init__(self):
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def project_qobject(project, qapp):
    """`project` (fixture di atas) sudah mem-patch editor.ROOT ke folder tiruan."""
    engine = FakeEngine()
    controller = FakeController()
    ed = editor.ProjectEditor(engine, controller)
    return ed, engine, controller


def test_save_file_writes_to_disk_and_emits_signals(project, project_qobject):
    ed, engine, controller = project_qobject
    saved, logs = [], []
    ed.fileSaved.connect(saved.append)
    ed.logMessage.connect(logs.append)
    ed.saveFile("hologram/app.py", "print('baru')\n")
    assert saved == ["hologram/app.py"]
    assert editor.read_file("hologram/app.py") == "print('baru')\n"
    assert any("Tersimpan" in m for m in logs)
    assert engine.load_calls == 0 and not controller.shutdown_called   # "Simpan" saja tidak menerapkan apa-apa


def test_save_file_error_emits_error_and_log_not_saved_signal(project, project_qobject):
    ed, engine, controller = project_qobject
    errors, saved = [], []
    ed.errorOccurred.connect(errors.append)
    ed.fileSaved.connect(saved.append)
    ed.saveFile("../outside.txt", "jahat")
    assert saved == [] and errors and "di luar folder proyek" in errors[0]


def test_apply_on_qml_file_reloads_engine_without_restart(project, project_qobject, qapp):
    ed, engine, controller = project_qobject
    (project / "view.qml").write_text("Item {}", encoding="utf-8")
    reloading_events, logs = [], []
    ed.reloading.connect(reloading_events.append)
    ed.logMessage.connect(logs.append)
    ed.applyFile("view.qml", "Item { visible: true }")
    assert editor.read_file("view.qml") == "Item { visible: true }"
    assert reloading_events == [True]                 # overlay langsung tampil
    pump(300)
    assert reloading_events == [True, False]           # lalu ditutup lagi setelah selesai
    assert engine.cache_cleared and engine.load_calls == 1
    assert not controller.shutdown_called              # QML tidak pernah me-restart proses
    assert any("dimuat ulang" in m for m in logs)


def test_apply_on_qml_file_keeps_old_window_if_reload_fails(project, qapp):
    engine = FakeEngine(succeed=False)     # load() tidak membuat window baru (mis. galat sintaks)
    controller = FakeController()
    ed = editor.ProjectEditor(engine, controller)
    (project / "broken.qml").write_text("x", encoding="utf-8")
    errors = []
    ed.errorOccurred.connect(errors.append)
    old_root = engine.rootObjects()[0]
    ed.applyFile("broken.qml", "ini bukan qml valid {{{")
    pump(300)
    assert not old_root.closed                          # window lama TIDAK ditutup kalau yang baru gagal
    assert errors and "tidak valid" in errors[0]


def test_apply_on_python_file_restarts_the_whole_process(project, project_qobject, qapp, monkeypatch):
    ed, engine, controller = project_qobject
    execv_calls = []
    monkeypatch.setattr(editor.os, "execv", lambda *a: execv_calls.append(a))
    monkeypatch.setattr(editor.sys, "argv", ["A:\\HologramOS\\hologram\\__main__.py"])
    ed.applyFile("hologram/app.py", "print('ubah total')\n")
    pump(700)
    assert controller.shutdown_called                   # thread dimatikan dulu sebelum restart
    assert len(execv_calls) == 1
    path, args = execv_calls[0]
    assert path == editor.sys.executable
    assert args == [editor.sys.executable, "-m", "hologram"]   # bukan sys.argv apa adanya (lihat _relaunch_args)
    assert engine.load_calls == 0                        # bukan file .qml: tidak menyentuh QML sama sekali


def test_relaunch_args_uses_module_flag_not_raw_argv(project_qobject, monkeypatch):
    ed, _, _ = project_qobject
    monkeypatch.setattr(editor.sys, "argv", ["A:\\HologramOS\\hologram\\__main__.py", "--no-camera"])
    monkeypatch.setattr(editor.sys, "frozen", False, raising=False)
    args = ed._relaunch_args()  # Panggil dari instance `ed`
    assert args == [editor.sys.executable, "-m", "hologram", "--no-camera"]


def test_relaunch_args_reruns_frozen_executable_directly(project_qobject, monkeypatch):
    ed, _, _ = project_qobject
    monkeypatch.setattr(editor.sys, "argv", ["HologramOS.exe", "--no-voice"])
    monkeypatch.setattr(editor.sys, "frozen", True, raising=False)
    args = ed._relaunch_args()  # Panggil dari instance `ed`
    assert args == [editor.sys.executable, "--no-voice"]


def test_apply_on_config_toml_also_restarts(project, project_qobject, qapp, monkeypatch):
    ed, engine, controller = project_qobject
    execv_calls = []
    monkeypatch.setattr(editor.os, "execv", lambda *a: execv_calls.append(a))
    ed.applyFile("config.toml", "[app]\nmode='online'\n")
    pump(700)
    assert len(execv_calls) == 1 and controller.shutdown_called


def test_open_and_error_paths_are_logged(project, project_qobject):
    ed, engine, controller = project_qobject
    logs = []
    ed.logMessage.connect(logs.append)
    ed.openFile("hologram/app.py")
    ed.openFile("tidak-ada.py")
    assert any("Membuka hologram/app.py" in m for m in logs)
    assert any("Tidak bisa membuka" in m for m in logs)


def test_log_lines_are_timestamped():
    engine = FakeEngine()
    controller = FakeController()
    ed = editor.ProjectEditor(engine, controller)
    lines = []
    ed.logMessage.connect(lines.append)
    ed._log("halo")
    assert len(lines) == 1
    import re
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] halo$", lines[0])