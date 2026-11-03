import subprocess
import sys
from pathlib import Path

import pytest

import verify
from verify import local_counts, local_files, missing, parse_lsf


def make_albums(tmp_path: Path) -> Path:
    tmp_path.mkdir(exist_ok=True)
    for album, files in {"WhatsApp - A": ["1.jpg", "2.jpg"], "WhatsApp - B": ["3.mp4"]}.items():
        (tmp_path / album).mkdir()
        for name in files:
            (tmp_path / album / name).write_bytes(f"{album}/{name}".encode())
    (tmp_path / "WhatsApp - A" / ".DS_Store").write_bytes(b"")
    return tmp_path


def test_parse_lsf_splits_on_first_slash_only() -> None:
    lines = ["WhatsApp - A/1.jpg", "WhatsApp - A/x/y.jpg", "no-slash"]
    assert parse_lsf(lines) == {("WhatsApp - A", "1.jpg"), ("WhatsApp - A", "x/y.jpg")}


def test_local_listing_skips_hidden_files(tmp_path: Path) -> None:
    root = str(make_albums(tmp_path))
    assert local_counts(root) == {"WhatsApp - A": 2, "WhatsApp - B": 1}
    assert ("WhatsApp - A", ".DS_Store") not in local_files(root)


def test_missing_reports_only_files_not_in_remote(tmp_path: Path) -> None:
    root = str(make_albums(tmp_path))
    remote = parse_lsf(["WhatsApp - A/1.jpg", "WhatsApp - B/3.mp4", "WhatsApp - Z/extra.jpg"])
    assert missing(local_files(root), remote) == [("WhatsApp - A", "2.jpg")]


def test_main_writes_missing_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_albums(tmp_path / "albums")
    listing = "WhatsApp - A/1.jpg\nWhatsApp - B/3.mp4\n"
    monkeypatch.setattr(verify.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, listing, ""))
    monkeypatch.setattr(sys, "argv", ["verify.py", "--root", str(tmp_path)])
    assert verify.main() == 1
    assert (tmp_path / "missing.txt").read_text() == "WhatsApp - A/2.jpg\n"


def test_main_reports_rclone_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "albums").mkdir()
    monkeypatch.setattr(verify.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "auth error"))
    monkeypatch.setattr(sys, "argv", ["verify.py", "--root", str(tmp_path)])
    assert verify.main() == 2


def test_byte_identical_copy_counts_as_backed_up(tmp_path: Path) -> None:
    (tmp_path / "WhatsApp - A").mkdir()
    (tmp_path / "WhatsApp - B").mkdir()
    (tmp_path / "WhatsApp - A" / "orig.jpg").write_bytes(b"same bytes")
    (tmp_path / "WhatsApp - B" / "forwarded.jpg").write_bytes(b"same bytes")
    (tmp_path / "WhatsApp - B" / "unique.jpg").write_bytes(b"different!")  # same size, other bytes
    gone = [("WhatsApp - B", "forwarded.jpg"), ("WhatsApp - B", "unique.jpg")]
    present = [("WhatsApp - A", "orig.jpg")]
    assert verify.covered_by_duplicate(str(tmp_path), gone, present) == {
        ("WhatsApp - B", "forwarded.jpg")
    }
