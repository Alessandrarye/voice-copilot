# Seminar Copilot v2 — Class Archive

What's new over v1:
- Every transcribed chunk is saved to a daily transcript file
- Questions and Claude's answers are logged into the same file (Q >>> / A >>>)
- Screen recording via OBS Studio
- extract_frames.sh turns any recording into a folder of slide images

## Install the update

1. Replace ~/dev/seminar-copilot/seminar_copilot.py with the new version
2. Drop extract_frames.sh into ~/dev/seminar-copilot/ and make it runnable:

```bash
chmod +x ~/dev/seminar-copilot/extract_frames.sh
```

3. Restart the copilot (Ctrl+C, then `copilot`). Nothing else changes —
   run.sh, the prompter, and all settings carry over.

Transcripts land in: ~/dev/seminar-copilot/transcripts/transcript-YYYY-MM-DD.txt
One file per day, appended across sessions, timestamped per line.

## Screen recording with OBS (one-time setup)

```bash
sudo apt install obs-studio
```

First launch: run the auto-configuration wizard, choose "Optimize for
recording", accept defaults.

Then add what to record:
- Sources panel -> + -> Screen Capture (PipeWire) -> pick your monitor
- To also capture class audio in the video: + -> Audio Output Capture
  (it records the same speaker audio the copilot listens to; the two
  don't conflict)

Settings worth setting once (File -> Settings -> Output):
- Recording path: ~/Videos (or wherever you want class recordings)
- Recording format: mkv (survives crashes; convert later if needed)

Class-time ritual: click Start Recording when class starts, Stop when it
ends. That's the only manual part. OBS and the copilot run side by side.

## Extracting slides after class

```bash
~/dev/seminar-copilot/extract_frames.sh ~/Videos/YOUR_RECORDING.mkv 30
```

Second argument is seconds between frames (default 30). Frames land in
~/dev/seminar-copilot/frames/<recording-name>/ as numbered PNGs.

For a slide-heavy class, 30-60s intervals capture every slide with few
duplicates. For fast-moving demos, drop to 10-15s.

## The archive per class session

- transcripts/transcript-DATE.txt  — what was said + Q&A
- ~/Videos/recording.mkv           — full video
- frames/recording-name/           — the slides as images

v3 (later): send frames to the Claude API for slide text extraction and
merge with the transcript by timestamp.
