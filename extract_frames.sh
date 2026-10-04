#!/bin/bash
# Extract one frame every N seconds from a class recording.
# Usage: ./extract_frames.sh <video-file> [seconds-between-frames]
# Output lands in ~/dev/seminar-copilot/frames/<video-name>/

set -e

VIDEO="$1"
INTERVAL="${2:-30}"

if [ -z "$VIDEO" ] || [ ! -f "$VIDEO" ]; then
    echo "Usage: $0 <video-file> [seconds-between-frames]"
    echo "Example: $0 ~/Videos/2026-09-17_class.mkv 30"
    exit 1
fi

NAME=$(basename "$VIDEO" | sed 's/\.[^.]*$//')
OUTDIR="$HOME/dev/seminar-copilot/frames/$NAME"
mkdir -p "$OUTDIR"

# fps=1/INTERVAL -> one frame per INTERVAL seconds.
# Filenames carry the frame's timestamp offset in seconds so they can be
# matched against the transcript's clock times later.
ffmpeg -loglevel error -i "$VIDEO" \
    -vf "fps=1/$INTERVAL" \
    -frame_pts 1 -fps_mode passthrough \
    "$OUTDIR/frame_%04d.png"

COUNT=$(ls "$OUTDIR" | wc -l)
echo "Extracted $COUNT frames to $OUTDIR"
