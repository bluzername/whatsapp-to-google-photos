#!/bin/bash
# One-line upload progress summary from upload.log. Rate and ETA use the last hour only.
ROOT="${WA_ROOT:-$HOME/WhatsAppArchive}"
LOG="$ROOT/upload.log"
TOTAL=$(find "$ROOT/albums" -type f | wc -l | tr -d ' ')
DONE=$(grep -c 'Copied (new)' "$LOG")
ERRS=$(grep -c ERROR "$LOG")
CUTOFF=$(date -v-1H '+%Y/%m/%d %H:%M:%S')
RATE=$(grep 'Copied (new)' "$LOG" | awk -v c="$CUTOFF" 'substr($0,1,19) >= c' | wc -l | tr -d ' ')
LEFT=$(( TOTAL - DONE ))
ETA=$( [ "$RATE" -gt 0 ] && echo "~$(( LEFT / RATE ))h left at this pace" || echo "no uploads in the last hour" )
STATE="stopped"
pgrep -f "rclone copy" >/dev/null && STATE="uploading"
pgrep -f "upload.sh" >/dev/null && ! pgrep -f "rclone copy" >/dev/null && STATE="waiting ($(grep '^===' "$LOG" | tail -1))"
grep -q '=== DONE' "$LOG" && STATE="DONE"
echo "$DONE/$TOTAL ($(( DONE * 100 / (TOTAL > 0 ? TOTAL : 1) ))%) | $RATE files in last hour | $ETA | errors $ERRS | $STATE"
grep ERROR "$LOG" | tail -2
