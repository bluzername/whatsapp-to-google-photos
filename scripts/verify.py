"""Compare local albums with what Google Photos actually holds, album by album.

Lists every app-created album once with `rclone lsf -R` and reports albums with missing files.
Writes the full list of missing files to <root>/missing.txt. Run it after upload.sh says DONE,
and before deleting anything from WhatsApp.

Google Photos stores byte-identical uploads once and keeps the first upload's filename, so a
photo forwarded to two chats shows up under one name only. A file whose exact bytes are already
in Google Photos under another name counts as backed up.
"""
import argparse
import hashlib
import os
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable


def local_counts(albums_dir: str) -> Counter[str]:
    return Counter(
        album
        for album in os.listdir(albums_dir)
        if os.path.isdir(os.path.join(albums_dir, album))
        for name in os.listdir(os.path.join(albums_dir, album))
        if not name.startswith(".")
    )


def parse_lsf(lines: list[str]) -> set[tuple[str, str]]:
    """`rclone lsf -R --files-only remote:album` prints `Album/file.jpg` per line."""
    return {tuple(line.split("/", 1)) for line in lines if "/" in line}  # type: ignore[misc]


def local_files(albums_dir: str) -> set[tuple[str, str]]:
    return {
        (album, name)
        for album in os.listdir(albums_dir)
        if os.path.isdir(os.path.join(albums_dir, album))
        for name in os.listdir(os.path.join(albums_dir, album))
        if not name.startswith(".")
    }


def missing(local: set[tuple[str, str]], remote: set[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(local - remote)


def file_hash(path: str) -> str:
    digest = hashlib.md5()  # content identity only, not security
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def covered_by_duplicate(albums_dir: str, gone: Iterable[tuple[str, str]],
                         present: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    """Missing files whose exact bytes exist in Google Photos under another name.

    Only files sharing a size with a missing file are hashed, which keeps this fast.
    """
    def path(item: tuple[str, str]) -> str:
        return os.path.join(albums_dir, *item)

    gone = list(gone)
    sizes = {os.path.getsize(path(item)) for item in gone}
    present_by_size: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for item in present:
        size = os.path.getsize(path(item))
        if size in sizes:
            present_by_size[size].append(item)
    present_hashes = {file_hash(path(item)) for items in present_by_size.values() for item in items}
    return {item for item in gone
            if present_by_size.get(os.path.getsize(path(item)))
            and file_hash(path(item)) in present_hashes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.path.expanduser("~/WhatsAppArchive"))
    parser.add_argument("--remote", default="gphotos")
    args = parser.parse_args()
    albums_dir = os.path.join(args.root, "albums")

    res = subprocess.run(["rclone", "lsf", "-R", "--files-only", f"{args.remote}:album"],
                         capture_output=True, text=True, check=False)
    if res.returncode != 0:
        print(res.stderr.strip()[-2000:], file=sys.stderr)
        return 2
    local = local_files(albums_dir)
    by_name = missing(local, parse_lsf(res.stdout.splitlines()))
    dupes = covered_by_duplicate(albums_dir, by_name, local - set(by_name))
    gone = [item for item in by_name if item not in dupes]
    totals = local_counts(albums_dir)
    if dupes:
        print(f"{len(dupes)} files are byte-identical to photos already in Google Photos "
              "under another name; counted as backed up")
    by_album = Counter(album for album, _ in gone)

    with open(os.path.join(args.root, "missing.txt"), "w") as fh:
        fh.writelines(f"{album}/{name}\n" for album, name in gone)
    for album, count in by_album.most_common():
        print(f"{count:6d} / {totals[album]:6d} missing  {album}")
    total = sum(totals.values())
    print(f"{total - len(gone)} of {total} files are in Google Photos; "
          f"{len(gone)} missing (listed in missing.txt)")
    return 0 if not gone else 1


if __name__ == "__main__":
    sys.exit(main())
