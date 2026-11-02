"""End-to-end stamp.py run against a tiny fake WhatsApp database and real exiftool."""
import csv
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import stamp

# Smallest valid JPEG (1x1 px), so exiftool can write EXIF into it.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c19"
    "1213 0f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b08"
    "0001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b51000"
    "02010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f0"
    "2433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768"
    "696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3"
    "c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fb"
    "d3ffd9".replace(" ", "")
)


def build_fake_whatsapp(raw: Path) -> None:
    media = raw / "Message" / "Media" / "chat1"
    media.mkdir(parents=True)
    (media / "known.jpg").write_bytes(TINY_JPEG)
    (media / "orphan.jpg").write_bytes(TINY_JPEG)
    db = sqlite3.connect(raw / "ChatStorage.sqlite")
    db.executescript(
        """
        CREATE TABLE ZWACHATSESSION (Z_PK INTEGER, ZPARTNERNAME TEXT, ZCONTACTJID TEXT);
        CREATE TABLE ZWAMESSAGE (Z_PK INTEGER, ZMESSAGEDATE REAL, ZCHATSESSION INTEGER);
        CREATE TABLE ZWAMEDIAITEM (ZMESSAGE INTEGER, ZMEDIALOCALPATH TEXT);
        INSERT INTO ZWACHATSESSION VALUES (1, 'Family', NULL);
        INSERT INTO ZWAMESSAGE VALUES (10, 600000000, 1);
        INSERT INTO ZWAMESSAGE VALUES (11, 600000001, 1);
        INSERT INTO ZWAMEDIAITEM VALUES (10, 'Media/chat1/known.jpg');
        INSERT INTO ZWAMEDIAITEM VALUES (11, 'Media/chat1/deleted-from-disk.jpg');
        """
    )
    db.commit()
    db.close()


def test_move_matched_and_unmatched(tmp_path: Path) -> None:
    raw, albums = tmp_path / "raw", tmp_path / "albums"
    build_fake_whatsapp(raw)
    rows = [("Media/chat1/known.jpg", 600000000.0, "Family"),
            ("Media/chat1/missing.jpg", 600000000.0, "Family")]
    log: list[list[object]] = []

    class Log:
        def writerow(self, row: list[object]) -> None:
            log.append(row)

    blocks = stamp.move_matched(rows, str(raw), str(albums), Log())
    assert len(blocks) == 1 and blocks[0][-1] == "-execute"
    moved = list((albums / "WhatsApp - Family").iterdir())
    assert [p.name.endswith("_known.jpg") for p in moved] == [True]

    assert stamp.move_unmatched(str(raw), str(albums), Log()) == 1
    assert (albums / stamp.UNMATCHED / "chat1_orphan.jpg").exists()
    assert log[-1][0] == stamp.UNMATCHED and log[-1][2] == ""


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_main_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_fake_whatsapp(tmp_path / "raw")
    monkeypatch.setattr(sys, "argv", ["stamp.py", "--root", str(tmp_path)])
    assert stamp.main() == 0

    (dated,) = (tmp_path / "albums" / "WhatsApp - Family").iterdir()
    expected = stamp.apple_to_local(600000000)
    out = subprocess.run(["exiftool", "-s3", "-DateTimeOriginal", str(dated)],
                         capture_output=True, text=True).stdout.strip()
    assert out == expected.strftime("%Y:%m:%d %H:%M:%S")

    with open(tmp_path / "manifest.csv") as fh:
        rows = list(csv.reader(fh))
    assert {r[0] for r in rows} == {"WhatsApp - Family", stamp.UNMATCHED}
