#!/usr/bin/env python3
"""
Seminar Copilot
Listens to a PulseAudio/PipeWire source (your mic OR a .monitor source that
captures what's playing through your speakers), transcribes locally with
faster-whisper on GPU, detects questions, asks Claude, and pushes answers
to a browser teleprompter over a websocket.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python seminar_copilot.py --list-sources          # find your audio source
    python seminar_copilot.py --source <name>         # run it
    python seminar_copilot.py                          # auto-picks first .monitor

Then open http://localhost:8770 in a browser for the teleprompter.
"""

import os
import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import uvicorn
from anthropic import AsyncAnthropic, APIConnectionError, APITimeoutError
from dotenv import load_dotenv
# Load ANTHROPIC_API_KEY (and anything else) from this project's own .env;
# values there take precedence over the shell environment.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
from faster_whisper import WhisperModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# ---------------- Config ----------------
SAMPLE_RATE = 16000
CHUNK_SECONDS = 5           # audio window per transcription pass
CONTEXT_WINDOW_SECONDS = int(os.environ.get("CONTEXT_WINDOW_SECONDS", "120"))  # rolling transcript context sent to Claude
MIN_SECONDS_BETWEEN_AUTO = 20 # throttle auto-triggered questions
WHISPER_MODEL = "small.en"    # good speed/accuracy balance on GPU; try "medium.en" if you have headroom
CLAUDE_MODEL = "claude-sonnet-5"
PORT = 8770
TRANSCRIPT_DIR = Path.home() / "dev" / "seminar-copilot" / "transcripts"
EXTRA_CONTEXT = ""
BRIEF_TEXT = ""  # --brief file, injected whole into the system prompt


def log_line(text: str):
    """Append a timestamped line to today's transcript file."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = TRANSCRIPT_DIR / f"transcript-{time.strftime('%Y-%m-%d')}.txt"
    with open(log_path, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")

QUESTION_STARTERS = re.compile(
    r"^(what|how|why|when|where|who|which|can|could|would|should|do|does|did|is|are|will|any(one|body)? know)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "You are a live seminar assistant. You receive a rolling transcript of a "
    "seminar and a question that just came up. Answer the question concisely "
    "and accurately for display on a teleprompter: 2-5 short sentences, plain "
    "prose, no markdown, no preamble. If the transcript gives context that "
    "changes the answer, use it. If the question is unclear or not really a "
    "question, reply with exactly: SKIP"
)

DEMO_ADDENDUM = (
    " You are assisting the presenter during her own capstone demo, and the "
    "rolling transcript includes what she herself has already said out loud. "
    "Before answering, check whether she already covered the point in her "
    "narration. If she did, do not repeat it. Open with a few words that "
    "acknowledge it, such as 'I touched on this earlier,' and then add "
    "something new: a different angle, one level more technical detail, a "
    "concrete example, or the trade-off behind the choice. If she has not "
    "covered it, answer directly from the briefing files. Read how the "
    "question is asked and shape the first sentence to match it. A skeptical "
    "or challenging question gets the honest concession first and then the "
    "evidence. A curious or technical question gets the mechanism first. A "
    "practical or business question gets the shop-owner consequence first. "
    "Write in the first person as the presenter. If the text looks like the "
    "presenter narrating her own slides rather than a question from the "
    "audience, reply with exactly: SKIP"
)
if os.environ.get("COPILOT_MODE") == "demo":
    SYSTEM_PROMPT = SYSTEM_PROMPT + DEMO_ADDENDUM

BRIEF_INSTRUCTION = (
    "Answer every question in 2 to 4 sentences, warm and plain, suitable for "
    "reading aloud to family. This overrides any other length guidance. Base "
    "your answers on the briefing below and use its specifics (names, numbers, "
    "equipment) when they apply.\n\n"
    "BRIEFING:\n"
)


def system_blocks():
    """System prompt as content blocks; the brief (if any) is a cached block."""
    blocks = [{"type": "text", "text": SYSTEM_PROMPT}]
    if BRIEF_TEXT:
        blocks.append({
            "type": "text",
            "text": BRIEF_INSTRUCTION + BRIEF_TEXT,
            "cache_control": {"type": "ephemeral"},
        })
    return blocks

# ---------------- State ----------------
transcript_buffer = deque()   # (timestamp, text)
clients: set = set()
last_auto_trigger = 0.0
event_loop = None

app = FastAPI()
claude = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env


# ---------------- Teleprompter page ----------------
@app.get("/")
async def index():
    html = (Path(__file__).parent / "prompter.html").read_text()
    return HTMLResponse(html)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "ask_now":
                # Manual trigger from the page: answer based on recent context
                await handle_question(data.get("question") or recent_transcript(30), manual=True)
    except WebSocketDisconnect:
        clients.discard(ws)


async def broadcast(payload: dict):
    dead = []
    for ws in clients:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


# ---------------- Transcript handling ----------------
def recent_transcript(seconds: float) -> str:
    cutoff = time.time() - seconds
    return " ".join(t for ts, t in transcript_buffer if ts >= cutoff)


def prune_buffer():
    cutoff = time.time() - CONTEXT_WINDOW_SECONDS
    while transcript_buffer and transcript_buffer[0][0] < cutoff:
        transcript_buffer.popleft()


def looks_like_question(text: str) -> str | None:
    """Return the question sentence if the chunk seems to contain one."""
    # Split on sentence-ish boundaries
    sentences = re.split(r"(?<=[.?!])\s+", text.strip())
    for s in reversed(sentences):
        s = s.strip()
        if not s:
            continue
        if s.endswith("?") or QUESTION_STARTERS.match(s):
            return s
    return None


# ---------------- Claude ----------------
async def handle_question(question: str, manual: bool = False):
    global last_auto_trigger
    if not question or not question.strip():
        return
    context = recent_transcript(CONTEXT_WINDOW_SECONDS)
    await broadcast({"type": "thinking", "question": question})
    try:
        content = []
        if EXTRA_CONTEXT:
            content.append({
                "type": "text",
                "text": (
                    "Reference material about the presenter's project. When a "
                    "question matches something covered here, base the answer "
                    "on this material and its prepared answers:\n"
                    f"{EXTRA_CONTEXT}"
                ),
                "cache_control": {"type": "ephemeral"},
            })
        content.append({
            "type": "text",
            "text": (
                f"Rolling transcript (last {CONTEXT_WINDOW_SECONDS}s):\n"
                f"{context}\n\n"
                f"Question to answer:\n{question}"
            ),
        })
        answer = ""
        started = False
        for _attempt in range(3):
            try:
                async with claude.messages.stream(
                    model=CLAUDE_MODEL,
                    max_tokens=400,
                    system=system_blocks(),
                    messages=[{"role": "user", "content": content}],
                ) as stream:
                    async for text in stream.text_stream:
                        answer += text
                        head = answer.strip()
                        if not started:
                            if len(head) <= 4 and "SKIP".startswith(head):
                                continue
                            if head.startswith("SKIP"):
                                break
                            started = True
                        await broadcast({"type": "answer_chunk", "question": question, "answer": head})
                break
            except (APIConnectionError, APITimeoutError) as _e:
                if _attempt == 2:
                    raise
                print(f"[claude] connection problem, retrying ({_attempt + 1}/2): {_e}")
                answer = ""
                started = False
                await asyncio.sleep(1.5)
        answer = answer.strip()
        if answer.startswith("SKIP") and not manual:
            await broadcast({"type": "skipped"})
            return
        await broadcast({"type": "answer", "question": question, "answer": answer})
        log_line(f"Q >>> {question}")
        log_line(f"A >>> {answer}")
        last_auto_trigger = time.time()
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        print(f"[claude error] {e}", file=sys.stderr)


# ---------------- Audio + transcription ----------------
def list_sources():
    out = subprocess.run(
        ["pactl", "list", "short", "sources"], capture_output=True, text=True
    ).stdout
    print("Available sources (use the NAME column with --source):\n")
    print(out)
    monitors = [l.split("\t")[1] for l in out.splitlines() if ".monitor" in l]
    if monitors:
        print("Speaker-capture (monitor) sources:")
        for m in monitors:
            print(f"  {m}")


def pick_default_source() -> str:
    out = subprocess.run(
        ["pactl", "list", "short", "sources"], capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and ".monitor" in parts[1]:
            return parts[1]
    raise SystemExit("No .monitor source found. Run with --list-sources and pass --source.")


def audio_worker(source: str, model: WhisperModel):
    """Blocking thread: read PCM from ffmpeg, transcribe in fixed chunks."""
    global last_auto_trigger
    cmd = [
        "ffmpeg", "-loglevel", "quiet",
        "-f", "pulse", "-i", source,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    bytes_per_chunk = SAMPLE_RATE * 2 * CHUNK_SECONDS
    print(f"[audio] capturing from: {source}")

    while True:
        raw = proc.stdout.read(bytes_per_chunk)
        if not raw:
            print("[audio] stream ended", file=sys.stderr)
            break
        audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0

        # Skip near-silent chunks cheaply
        if np.abs(audio).mean() < 0.004:
            continue

        segments, _ = model.transcribe(audio, language="en", vad_filter=True, beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        if not text:
            continue

        now = time.time()
        transcript_buffer.append((now, text))
        log_line(text)
        prune_buffer()
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "transcript", "text": text}), event_loop
        )

        q = looks_like_question(text)
        if q and (now - last_auto_trigger) > MIN_SECONDS_BETWEEN_AUTO:
            last_auto_trigger = now  # set immediately to avoid double-fires
            asyncio.run_coroutine_threadsafe(handle_question(q), event_loop)


# ---------------- Main ----------------
async def main(source: str):
    global event_loop
    event_loop = asyncio.get_running_loop()

    print(f"[whisper] loading {WHISPER_MODEL} on GPU...")
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
    print("[whisper] ready")

    await asyncio.gather(
        asyncio.to_thread(audio_worker, source, model),
        uvicorn.Server(
            uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning")
        ).serve(),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="PulseAudio/PipeWire source name")
    ap.add_argument("--list-sources", action="store_true")
    ap.add_argument("--context", nargs="+", help="one or more briefing files")
    ap.add_argument("--brief", help="briefing file included whole in the system prompt")
    args = ap.parse_args()
    if args.brief:
        brief_path = Path(args.brief).expanduser()
        if not brief_path.exists():
            sys.exit(f"[brief] file not found: {args.brief}")
        BRIEF_TEXT = brief_path.read_text()
        print(f"[brief] loaded {brief_path.name} into system prompt "
              f"({len(BRIEF_TEXT.split())} words, {len(BRIEF_TEXT)} chars)")
    if args.context:
        loaded = []
        for p in args.context:
            path = Path(p)
            if path.exists():
                loaded.append(path.read_text())
            else:
                print(f"[context] skipping missing file: {p}")
        EXTRA_CONTEXT = "\n\n".join(loaded)
        print(f"[context] loaded {len(loaded)} file(s) ({len(EXTRA_CONTEXT)} chars)")

    if args.list_sources:
        list_sources()
        sys.exit(0)

    src = args.source or pick_default_source()
    print(f"Teleprompter: http://localhost:{PORT}")
    try:
        asyncio.run(main(src))
    except KeyboardInterrupt:
        pass
