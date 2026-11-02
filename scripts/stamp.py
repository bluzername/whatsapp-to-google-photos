"""Match extracted WhatsApp media to its message, write the real send date, sort into per-chat albums.

Reads <root>/raw (from extract.py) and moves files into
<root>/albums/WhatsApp - <chat>/<YYYY-MM-DD_HHMMSS>_<name>. Dates are written with one batched
exiftool run, and every file is logged to <root>/manifest.csv.
Files no message refers to go to "WhatsApp - Unmatched (no date)" untouched.
"""
import argparse
import csv
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

UNMATCHED = "WhatsApp - Unmatched (no date)"
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
VIDEO_EXT = {".mp4", ".mov", ".3gp", ".m4v"}

QUERY = """
SELECT m.ZMEDIALOCALPATH, msg.ZMESSAGEDATE, COALESCE(s.ZPARTNERNAME, s.ZCONTACTJID, 'Unknown')
FROM ZWAMEDIAITEM m
JOIN ZWAMESSAGE msg ON msg.Z_PK = m.ZMESSAGE
LEFT JOIN ZWACHATSESSION s ON s.Z_PK = msg.ZCHATSESSION
WHERE m.ZMEDIALOCALPATH IS NOT NULL AND msg.ZMESSAGEDATE IS NOT NULL
"""


def album_name(chat: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", chat).strip(" .")
    return f"WhatsApp - {cleaned or 'Unknown'}"


def apple_to_local(seconds: float, tz: tzinfo | None = None) -> datetime:
    """WhatsApp stores dates as seconds since 2001-01-01 UTC (Apple epoch)."""
    return (APPLE_EPOCH + timedelta(seconds=seconds)).astimezone(tz)


def dest_name(local_dt: datetime, src_path: str) -> str:
    return f"{local_dt:%Y-%m-%d_%H%M%S}_{os.path.basename(src_path)}"


def exif_tags(path: str, local_dt: datetime) -> list[str]:
    stamp = local_dt.strftime("%Y:%m:%d %H:%M:%S")
    offset = local_dt.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}"
    if os.path.splitext(path)[1].lower() in VIDEO_EXT:
        # QuickTime dates are UTC by spec; QuickTimeUTC makes exiftool convert from the offset.
        return ["-api", "QuickTimeUTC", f"-QuickTime:CreateDate={stamp}{offset}",
                f"-QuickTime:ModifyDate={stamp}{offset}", f"-Keys:CreationDate={stamp}{offset}"]
    return [f"-EXIF:DateTimeOriginal={stamp}", f"-EXIF:CreateDate={stamp}",
            f"-EXIF:OffsetTimeOriginal={offset}"]


def move_matched(rows: list[tuple[str, float, str]], raw: str, albums: str,
                 log: Any) -> list[list[str]]:
    blocks = []
    for local_path, msg_date, chat in rows:
        src = os.path.join(raw, "Message", local_path.lstrip("/"))
        if not os.path.exists(src):
            continue
        local_dt = apple_to_local(msg_date)
        album = album_name(chat)
        os.makedirs(os.path.join(albums, album), exist_ok=True)
        dest = os.path.join(albums, album, dest_name(local_dt, src))
        os.replace(src, dest)
        ts = local_dt.timestamp()
        os.utime(dest, (ts, ts))
        blocks.append([*exif_tags(dest, local_dt), dest, "-execute"])
        log.writerow([album, os.path.basename(dest), local_dt.isoformat(), os.path.getsize(dest)])
    return blocks


def move_unmatched(raw: str, albums: str, log: Any) -> int:
    dest_dir = os.path.join(albums, UNMATCHED)
    moved = 0
    for dirpath, _, files in os.walk(os.path.join(raw, "Message")):
        for name in files:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, f"{os.path.basename(dirpath)}_{name}")
            os.replace(os.path.join(dirpath, name), dest)
            log.writerow([UNMATCHED, os.path.basename(dest), "", os.path.getsize(dest)])
            moved += 1
    return moved


def run_exiftool(blocks: list[list[str]], argfile: str) -> list[str]:
    with open(argfile, "w") as fh:
        args = [arg for block in blocks for arg in block][:-1]  # no trailing empty command
        fh.write("\n".join(args) + "\n")
    res = subprocess.run(["exiftool", "-@", argfile,
                          "-common_args", "-overwrite_original", "-P", "-m"],
                         capture_output=True, text=True)
    return [line for line in res.stderr.splitlines() if line.startswith("Error")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.path.expanduser("~/WhatsAppArchive"))
    args = parser.parse_args()
    raw, albums = os.path.join(args.root, "raw"), os.path.join(args.root, "albums")

    db = sqlite3.connect(f"file:{os.path.join(raw, 'ChatStorage.sqlite')}?immutable=1", uri=True)
    rows = db.execute(QUERY).fetchall()
    with open(os.path.join(args.root, "manifest.csv"), "a", newline="") as fh:
        log = csv.writer(fh)
        blocks = move_matched(rows, raw, albums, log)
        unmatched = move_unmatched(raw, albums, log)
    print(f"Moved {len(blocks)} dated files, {unmatched} unmatched. Running exiftool...", flush=True)
    if not blocks:
        return 0
    errors = run_exiftool(blocks, os.path.join(args.root, "exiftool-args.txt"))
    print(f"exiftool: {len(errors)} errors")
    for line in errors[:20]:
        print("  ", line)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
