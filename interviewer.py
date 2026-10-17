#!/usr/bin/env python3
"""
Mock Interviewer v2
Claude asks interview questions (optionally aloud via Piper TTS),
listens to your spoken answer, critiques it against your briefings,
shows a stronger version of your answer, and asks the next question.

Usage:
    python interviewer.py --context interview.md capstone.md footnote.md \
        --source <mic or combined source> \
        [--voice /path/to/piper-voice.onnx]

Open http://localhost:8766. Flow: Begin -> listen to the question ->
answer aloud -> Done answering -> read critique + stronger version ->
next question. Sessions log to interviews/interview-<timestamp>.txt
Requires ANTHROPIC_API_KEY. Voice requires: pip install piper-tts
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import uvicorn
from anthropic import AsyncAnthropic
from faster_whisper import WhisperModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# ---------------- Config ----------------
SAMPLE_RATE = 16000
CHUNK_SECONDS = 4
WHISPER_MODEL = "small.en"
CLAUDE_MODEL = "claude-sonnet-5"
PORT = 8766
LOG_DIR = Path.home() / "dev" / "seminar-copilot" / "interviews"

SYSTEM_PROMPT = """You are a rigorous but encouraging job interviewer
conducting a realistic mock interview. You have briefing material about
the candidate: their background, prepared stories, and projects.

Rules:
- Ask ONE question at a time. Mix question types across the session:
  background walkthrough, behavioral (tell me about a time...),
  project deep-dives drawn from their actual projects, and the
  uncomfortable classics (gaps, career change, why should we hire you).
- Ask follow-ups when an answer is vague, claims something without
  evidence, or contradicts the briefing material. Push the way a sharp
  interviewer would, but stay professional.
- After each answer, produce two coaching pieces before the next
  question:
  1. critique: 2-4 sentences. Name what landed, what to tighten,
     whether the answer matched their prepared material, and any
     factual slip or missed opportunity. Specific, never generic.
  2. better: a stronger version of the answer the candidate could
     have given, 2-5 sentences, first person, spoken style, in the
     candidate's own plain voice. Use ONLY facts from the briefing
     and from what they actually said; never invent accomplishments
     or numbers.
- Keep questions, critiques, and the better answer concise and
  spoken-style. No markdown anywhere.

Respond ONLY with JSON, no other text:
{"critique": "<critique of the last answer, empty string for the first
question or after a skip>", "better": "<stronger version of the last
answer, empty string for the first question or after a skip>",
"question": "<the next interview question>"}"""

# ---------------- State ----------------
clients: set = set()
event_loop = None
answering = False
answer_buffer: list = []
history: list = []
log_path: Path = None
EXTRA_CONTEXT = ""
VOICE_MODEL = None
PERSONA_TAG = "job-interview"
QUESTION_BANK = LOG_DIR / "question-bank.md"

app = FastAPI()
claude = AsyncAnthropic()


# ---------------- Page ----------------
@app.get("/")
async def index():
    return HTMLResponse((Path(__file__).parent / "interviewer.html").read_text())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            data = json.loads(await ws.receive_text())
            action = data.get("type")
            if action == "begin":
                await next_turn(first=True)
            elif action == "done":
                await next_turn(first=False)
            elif action == "skip":
                await next_turn(first=False, skipped=True)
            elif action == "example":
                await show_example()
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


# ---------------- Logging ----------------
def log(text: str):
    if log_path:
        with open(log_path, "a") as f:
            f.write(text + "\n")


def bank_question(q: str):
    """Append every asked question to the cumulative question bank."""
    try:
        with open(QUESTION_BANK, "a") as f:
            f.write(f"- [{time.strftime('%Y-%m-%d')}] [{PERSONA_TAG}] {q}\n")
    except Exception as e:
        print(f"[bank] {e}", file=sys.stderr)


# ---------------- Voice ----------------
def speak(text: str):
    """Synthesize with Piper and play through the speakers. Blocking;
    run in a thread. Fails silent (prints a note) if piper is absent."""
    wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        subprocess.run(
            ["piper", "--model", VOICE_MODEL, "--output_file", wav],
            input=text.encode(), check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(["paplay", wav], check=True)
    except FileNotFoundError:
        print("[voice] piper or paplay not found; continuing without voice",
              file=sys.stderr)
    except Exception as e:
        print(f"[voice] {e}", file=sys.stderr)
    finally:
        if wav:
            try:
                os.unlink(wav)
            except Exception:
                pass


# ---------------- Interview turns ----------------
def parse_reply(raw: str) -> dict:
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            d = json.loads(m.group(0))
            if "question" in d:
                return {"critique": d.get("critique", ""),
                        "better": d.get("better", ""),
                        "question": d["question"]}
    except Exception:
        pass
    return {"critique": "", "better": "", "question": raw.strip()}


async def next_turn(first: bool, skipped: bool = False):
    global answering, answer_buffer, history

    answering = False  # mic off while we think and speak
    if first:
        history = [{
            "role": "user",
            "content": (
                "Briefing material about the candidate:\n\n"
                f"{EXTRA_CONTEXT}\n\n"
                "Begin the mock interview with your first question."
            ),
        }]
    else:
        answer = " ".join(t for _, t in answer_buffer).strip()
        answer_buffer = []
        if skipped:
            history.append({"role": "user",
                            "content": "The candidate skipped that question. "
                                       "No critique or better answer; ask a "
                                       "different one."})
            log("A >>> [skipped]")
        else:
            if not answer:
                answer = "[no answer was captured]"
            history.append({"role": "user",
                            "content": f"Candidate's spoken answer "
                                       f"(transcribed): {answer}"})
            log(f"A >>> {answer}")

    await broadcast({"type": "thinking"})
    try:
        resp = await claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=900,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        turn = parse_reply(raw)
        history.append({"role": "assistant", "content": raw})
        if turn["critique"]:
            log(f"C >>> {turn['critique']}")
        if turn["better"]:
            log(f"B >>> {turn['better']}")
        log(f"Q >>> {turn['question']}")
        bank_question(turn["question"])

        # Show the turn (mic still off), speak the question, then listen.
        await broadcast({"type": "turn", **turn})
        if VOICE_MODEL:
            await asyncio.to_thread(speak, turn["question"])
        answering = True
        await broadcast({"type": "listening"})
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        print(f"[claude error] {e}", file=sys.stderr)


async def show_example():
    """The candidate is stuck: produce a strong example answer to the
    current question without advancing the interview."""
    global history
    history.append({
        "role": "user",
        "content": (
            "The candidate is stuck and asked to see an example of a "
            "strong answer to the question you just asked. Respond ONLY "
            'with JSON, no other text: {"example": "<a strong answer to '
            "that question, 3-6 sentences, first person, spoken style, "
            "in the candidate's own plain voice, built only from the "
            'briefing material and this conversation>"}. Do not ask a '
            "new question and do not critique."
        ),
    })
    await broadcast({"type": "thinking"})
    try:
        resp = await claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        history.append({"role": "assistant", "content": raw})
        example = raw.strip()
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                example = json.loads(m.group(0)).get("example", example)
        except Exception:
            pass
        log(f"E >>> {example}")
        await broadcast({"type": "example", "text": example})
        await broadcast({"type": "listening"})
    except Exception as e:
        await broadcast({"type": "error", "message": str(e)})
        print(f"[claude error] {e}", file=sys.stderr)


# ---------------- Audio ----------------
def audio_worker(source: str, model: WhisperModel):
    cmd = ["ffmpeg", "-loglevel", "quiet", "-f", "pulse", "-i", source,
           "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    bytes_per_chunk = SAMPLE_RATE * 2 * CHUNK_SECONDS
    print(f"[audio] capturing from: {source}")

    while True:
        raw = proc.stdout.read(bytes_per_chunk)
        if not raw:
            print("[audio] stream ended", file=sys.stderr)
            break
        if not answering:
            continue
        audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        if np.abs(audio).mean() < 0.004:
            continue
        segments, _ = model.transcribe(audio, language="en",
                                       vad_filter=True, beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            continue
        answer_buffer.append((time.time(), text))
        asyncio.run_coroutine_threadsafe(
            broadcast({"type": "heard", "text": text}), event_loop)


# ---------------- Main ----------------
async def main(source: str):
    global event_loop
    event_loop = asyncio.get_running_loop()
    print(f"[whisper] loading {WHISPER_MODEL} on GPU...")
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
    print("[whisper] ready")
    await asyncio.gather(
        asyncio.to_thread(audio_worker, source, model),
        uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT,
                                      log_level="warning")).serve(),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="PulseAudio/PipeWire source (your mic or combined)")
    ap.add_argument("--context", nargs="+", required=True,
                    help="briefing files the interviewer draws on")
    ap.add_argument("--voice",
                    help="path to a Piper .onnx voice model; speaks questions")
    ap.add_argument("--persona",
                    help="file that redefines the interviewer's role for "
                         "this session (e.g., a capstone panel)")
    args = ap.parse_args()

    if args.persona:
        ppath = Path(args.persona)
        if ppath.exists():
            SYSTEM_PROMPT = (ppath.read_text() + "\n\n" + SYSTEM_PROMPT)
            PERSONA_TAG = ppath.stem
            print(f"[persona] {ppath.name}")
        else:
            print(f"[persona] file not found, using default interviewer: "
                  f"{args.persona}")

    loaded = []
    for p in args.context:
        path = Path(p)
        if path.exists():
            loaded.append(f"=== {path.name} ===\n{path.read_text()}")
        else:
            print(f"[context] skipping missing file: {p}")
    EXTRA_CONTEXT = "\n\n".join(loaded)
    print(f"[context] loaded {len(loaded)} file(s) ({len(EXTRA_CONTEXT)} chars)")

    if args.voice:
        if Path(args.voice).exists():
            VOICE_MODEL = args.voice
            print(f"[voice] speaking questions with {Path(args.voice).name}")
        else:
            print(f"[voice] model not found, continuing silent: {args.voice}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"interview-{time.strftime('%Y-%m-%d-%H%M')}.txt"
    print(f"[log] {log_path}")
    print(f"Interview panel: http://localhost:{PORT}")
    try:
        asyncio.run(main(args.source))
    except KeyboardInterrupt:
        pass
