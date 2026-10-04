# Voice Copilot

A real-time AI assistant pipeline that listens to live audio, transcribes
it locally on GPU, detects questions, answers them through the Claude API
using swappable briefing files, and displays answers on a browser
teleprompter. Built for live seminars; now runs as a multi-mode system
for classes, presentation rehearsal, and interview practice.

Running daily on a Linux desktop (Ubuntu 24.04, RTX GPU). Everything
except the answer generation runs locally: capture, transcription,
archiving, and display never leave the machine.

## How it works

```
PipeWire/PulseAudio source (mic, speakers, or a merged virtual source)
        v  ffmpeg (16 kHz PCM)
faster-whisper on GPU (5s chunks, VAD, silence skipping)
        v
rolling transcript buffer -- archived to daily transcript files
        v
question detection (heuristics + manual trigger from the UI)
        v
Claude API (rolling transcript context + injected briefing files)
        v
websocket broadcast -> browser teleprompter (FastAPI + vanilla JS)
```

A background pipeline turns the archive into reusable context:

```
daily transcripts + lecture-video transcripts
        v  summarize_transcripts.py  (incremental, per-file, checkpointed)
per-class study notes (summaries/)
        v  digest_notes.py  (map-reduce style merge)
one topic-organized course digest, sized for cheap per-question injection
```

## Features

- Live transcription of any audio source: a microphone, system audio
  (what's playing through the speakers), or a merged virtual source
  that carries both (setup_audio.sh builds it with PipeWire loopbacks)
- Automatic question detection with throttling, plus a manual
  "answer the last 30 seconds" button for anything detection misses
- Context injection: one or more markdown briefing files loaded at
  launch, so answers draw on the right project, course, or prep
  material; missing files are skipped gracefully
- Daily timestamped transcript archive, including every question asked
  and answer given
- Hierarchical summarization: transcripts -> per-class notes -> a single
  topic-organized digest, cutting per-question context cost ~10x
- Frame extraction from class recordings (extract_frames.sh) for a
  slide archive
- Mode launchers: thin shell scripts compose a source and a set of
  briefings into one-word commands (class, interview practice,
  project rehearsal) over one shared engine

## Stack

Python (asyncio), faster-whisper (CUDA), ffmpeg, FastAPI + websockets,
Anthropic API, PipeWire/PulseAudio, bash.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install faster-whisper anthropic fastapi "uvicorn[standard]" numpy
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # CUDA libs for whisper
sudo apt install ffmpeg pulseaudio-utils
export ANTHROPIC_API_KEY=...
```

Find an audio source and run:

```bash
python seminar_copilot.py --list-sources
python seminar_copilot.py --source <name> [--context briefing1.md briefing2.md ...]
```

Teleprompter at http://localhost:8765 (any device on the LAN works as
the display). See run.sh for a launcher template; setup_audio.sh builds
the merged mic+speakers source.

Briefing files, transcripts, and generated notes are intentionally
gitignored: they contain personal and course material. The engine is
general; the content is yours.

## Roadmap

- Mock interviewer mode: inverted loop (the model asks, listens, and
  critiques) over a shared core
- Retrieval (RAG) over the transcript archive, replacing whole-digest
  injection with per-question retrieval
- Wake-word voice router dispatching to tools, not just answers
