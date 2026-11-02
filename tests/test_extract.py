import os
from collections import namedtuple
from pathlib import Path

import pytest

import extract

Usage = namedtuple("Usage", "total used free")


def test_latest_backup_picks_newest_with_manifest(tmp_path: Path) -> None:
    for name, mtime in [("old", 1_000), ("new", 2_000)]:
        (tmp_path / name).mkdir()
        (tmp_path / name / "Manifest.db").write_bytes(b"")
        os.utime(tmp_path / name, (mtime, mtime))
    (tmp_path / "no-manifest").mkdir()
    assert extract.latest_backup(str(tmp_path)) == str(tmp_path / "new")


def test_latest_backup_exits_when_none(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        extract.latest_backup(str(tmp_path))


@pytest.mark.parametrize(
    ("path", "keep"),
    [("Media/a.JPG", True), ("Media/b.mov", True), ("Media/c.opus", False), ("Media/d.pdf", False)],
)
def test_is_media(path: str, keep: bool) -> None:
    assert extract.is_media(path) is keep


def test_filter_keeps_media_and_stops_on_low_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    keep = extract.make_filter("/tmp")
    monkeypatch.setattr(extract.shutil, "disk_usage", lambda _: Usage(0, 0, 100 * 1024**3))
    assert keep(relative_path="x.jpg", n=500, total_files=1000) is True
    assert keep(relative_path="x.opus", n=1, total_files=1000) is False
    monkeypatch.setattr(extract.shutil, "disk_usage", lambda _: Usage(0, 0, 1024))
    with pytest.raises(SystemExit):
        keep(relative_path="x.jpg", n=1000, total_files=1000)
