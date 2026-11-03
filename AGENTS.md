# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Aider and similar) running this pipeline for a user. Read the [README](README.md) first for the why.

## Goal

Move a user's WhatsApp photos and videos from their iPhone into Google Photos, with the true send date in each file and one album per chat, so they can then clear WhatsApp media from the phone.

## Hard rules

- **Never delete anything.** Not files in `~/WhatsAppArchive`, not media in WhatsApp, not anything in Google Photos. The final deletion in WhatsApp is the user's job, after `verify.py` reports nothing missing.
- **Never handle the backup password or OAuth client secret yourself.** The user types the password into `extract.py` (via `getpass`) and pastes the client secret into `rclone config`. Do not echo, log, store or commit them.
- **Never commit** anything under `~/WhatsAppArchive`, `rclone.conf`, `manifest.csv` or logs. They hold private chat data.
- Ask before any step that leaves the machine beyond the user's own Google account.

## Steps, and who does what

| Step | Command | Agent | Human |
|---|---|---|---|
| Install | `brew install libimobiledevice exiftool rclone`, `pip install -r requirements.txt` | runs it | |
| Backup | `idevicebackup2 -i encryption on` then `idevicebackup2 backup --full <dir>` | runs it | unlocks phone, taps Trust, sets the password |
| Extract | `python3 scripts/extract.py` | | runs it in a Terminal with Full Disk Access (macOS blocks agent shells from the backup folder) |
| Stamp | `python3 scripts/stamp.py` | runs it, reports exiftool errors | |
| Google OAuth | see README "Google setup" | can drive the Cloud Console in a browser; must not accept cookie or consent banners unasked | signs in, copies the client secret, runs `rclone config create` |
| Upload | `nohup caffeinate -i -s scripts/upload.sh >/dev/null 2>&1 &` | starts it, monitors with `scripts/status.sh` | keeps the Mac on and online |
| Verify | `python3 scripts/verify.py` (after `=== DONE` or `=== CONVERGED`) | runs it, reports per-album gaps | spot-checks albums in Google Photos |
| Free space | WhatsApp > Settings > Storage and Data > Manage Storage | **never** | deletes media |

Test the upload with one small album before the full run:

```bash
rclone copy "$HOME/WhatsAppArchive/albums/WhatsApp - <small chat>" "gphotos:album/WhatsApp - <small chat>" -v
rclone lsl "gphotos:album/WhatsApp - <small chat>"   # dates must match the WhatsApp send dates
```

## Reading the log

`~/WhatsAppArchive/upload.log` is rclone's log plus `===` marker lines from `upload.sh`.

| Log text | Meaning | Action |
|---|---|---|
| `Copied (new)` | one file uploaded | none |
| `=== daily quota hit, sleeping until ...` | daily API quota used up | none; it resumes on its own |
| `=== no upload for 15 min, restarting rclone` | watchdog caught a frozen rclone | none |
| `409 ABORTED`, `concurrent write request` | transient Google error | none; retried next pass |
| `Read requests per minute` right after a restart | album re-listing burst | none |
| `error while trying to create this media item` on tiny files | Google rejects icons and cache junk | report the count; usually not real photos |
| `panic:` | rclone crash | check `rclone version`; do not enable async batch mode |
| `invalid_grant` / token errors | OAuth refresh token expired (7-day testing limit) | ask the user to run `rclone config reconnect gphotos:` |
| `=== DONE` | every file uploaded | run `verify.py` |
| `=== CONVERGED` | only forwarded duplicates are left, which Google already holds under another name | run `verify.py` |
| more `Copied (new)` lines than files | the same duplicates re-sent each pass | none; not a problem |

`status.sh` rates use the last hour of `Copied (new)` lines, so right after a pause the ETA is pessimistic for a while.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check scripts tests
```

Pure logic (date conversion, album naming, EXIF tag building, verification diff) lives in importable functions and is unit-tested. Keep side effects in `main()`.
