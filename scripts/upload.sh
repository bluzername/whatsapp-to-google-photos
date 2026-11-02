#!/bin/bash
# Upload <root>/albums to Google Photos, one album per folder.
# Re-runs rclone until everything is up. rclone skips files already in the album,
# so each pass resumes where the last stopped.
# On the daily quota it stops rclone at once and sleeps until Google resets it (midnight Pacific).
# Batch mode stays "sync": rclone 1.75.2 crashes (nil pointer in setMetaData) with async.
#
# Usage: WA_ROOT=~/WhatsAppArchive WA_REMOTE=gphotos nohup caffeinate -i -s scripts/upload.sh &
set -u
ROOT="${WA_ROOT:-$HOME/WhatsAppArchive}"
REMOTE="${WA_REMOTE:-gphotos}"
LOG="$ROOT/upload.log"
MAX_PASSES=200
DAILY_QUOTA="Quota exceeded.*per day"

sleep_until_quota_reset() {
  local target now
  target=$(TZ=America/Los_Angeles date -v+1d -v0H -v15M -v0S +%s)
  now=$(date +%s)
  echo "=== daily quota hit, sleeping until $(date -r "$target" '+%F %T')" >> "$LOG"
  sleep $(( target - now ))
}

# Runs one rclone pass; returns 0 on success, 2 on daily quota, 3 on a stall, 1 on other failure.
run_pass() {
  local start rc
  start=$(( $(wc -l < "$LOG") + 1 ))
  rclone copy "$ROOT/albums" "$REMOTE:album" \
    --transfers 4 --gphotos-batch-size 48 --gphotos-batch-mode sync \
    --retries 3 --low-level-retries 5 \
    --stats 10m --stats-one-line --log-level INFO --log-file "$LOG" &
  rc=$!
  local copied last_copied=0 idle=0
  while kill -0 "$rc" 2>/dev/null; do
    if tail -n +"$start" "$LOG" | grep -q "$DAILY_QUOTA"; then
      kill "$rc"; wait "$rc"; return 2
    fi
    # rclone 1.75.2 has frozen mid-pass with zero traffic; restart it after 15 idle minutes.
    copied=$(tail -n +"$start" "$LOG" | grep -c 'Copied (new)')
    if [ "$copied" -gt "$last_copied" ]; then last_copied=$copied; idle=0; else idle=$((idle + 1)); fi
    if [ "$idle" -ge 30 ]; then
      echo "=== no upload for 15 min, restarting rclone $(date '+%F %T')" >> "$LOG"
      kill -9 "$rc"; wait "$rc"; return 3
    fi
    sleep 30
  done
  wait "$rc" && return 0
  tail -n +"$start" "$LOG" | grep -q "$DAILY_QUOTA" && return 2
  return 1
}

touch "$LOG"
for pass in $(seq 1 "$MAX_PASSES"); do
  echo "=== pass $pass $(date '+%F %T')" >> "$LOG"
  run_pass
  case $? in
    0) echo "=== DONE $(date '+%F %T')" >> "$LOG"; exit 0 ;;
    2) sleep_until_quota_reset ;;
    3) ;;
    # Each pass re-lists every album, which costs quota; don't spin on a fast failure.
    *) sleep 600 ;;
  esac
done
echo "=== GAVE UP after $MAX_PASSES passes" >> "$LOG"
exit 1
