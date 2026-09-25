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
