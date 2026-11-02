"""Decrypt WhatsApp's chat database and photo/video media from an encrypted iPhone backup.

Prompts for the backup password (never stored or printed). Run it in a terminal that has
Full Disk Access, since macOS guards ~/Library/Application Support/MobileSync.

Output: <out>/ChatStorage.sqlite and <out>/Message/Media/...
"""
import argparse
import getpass
import os
import shutil
import sys
from typing import Callable

BACKUP_ROOT = os.path.expanduser("~/Library/Application Support/MobileSync/Backup")
DOMAIN = "AppDomainGroup-group.net.whatsapp.WhatsApp.shared"
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".3gp", ".m4v"}
MIN_FREE_BYTES = 8 * 1024**3


def latest_backup(root: str = BACKUP_ROOT) -> str:
    """Return the most recently modified backup folder that has a Manifest.db."""
    candidates = [os.path.join(root, d) for d in os.listdir(root)
                  if os.path.exists(os.path.join(root, d, "Manifest.db"))]
    if not candidates:
        sys.exit(f"No iPhone backup found in {root}. Make an encrypted backup first.")
    return max(candidates, key=os.path.getmtime)


def is_media(relative_path: str) -> bool:
    return os.path.splitext(relative_path)[1].lower() in MEDIA_EXT


def make_filter(out_dir: str) -> Callable[..., bool]:
    def keep_media(*, relative_path: str, n: int, total_files: int, **_: object) -> bool:
        if n % 500 == 0:
            free = shutil.disk_usage(out_dir).free
            print(f"  {n}/{total_files} scanned, {free / 1024**3:.1f} GB free", flush=True)
            if free < MIN_FREE_BYTES:
                sys.exit("Stopping: disk below 8 GB free. Nothing lost; rerun after freeing space.")
        return is_media(relative_path)
    return keep_media


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup-dir", help="backup folder (default: most recent one)")
    parser.add_argument("--out", default=os.path.expanduser("~/WhatsAppArchive/raw"))
    args = parser.parse_args()
    from iphone_backup_decrypt import EncryptedBackup  # heavy optional dep, only needed here

    backup_dir = args.backup_dir or latest_backup()
    os.makedirs(args.out, exist_ok=True)
    print(f"Backup: {backup_dir}")
    backup = EncryptedBackup(backup_directory=backup_dir,
                             passphrase=getpass.getpass("iPhone backup password: "))
    backup.test_decryption()
    print("Password OK.")
    backup.extract_file(relative_path="ChatStorage.sqlite", domain_like=DOMAIN,
                        output_filename=os.path.join(args.out, "ChatStorage.sqlite"))
    print("Chat database extracted. Extracting photos/videos (incremental, safe to rerun)...")
    count = backup.extract_files(relative_paths_like="Message/Media/%", domain_like=DOMAIN,
                                 output_folder=args.out, preserve_folders=True, incremental=True,
                                 filter_callback=make_filter(args.out))
    print(f"Done: {count} media files extracted to {args.out}")


if __name__ == "__main__":
    main()
