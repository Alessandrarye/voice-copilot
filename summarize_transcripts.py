#!/usr/bin/env python3
"""
Transcript summarizer for the seminar copilot.

Walks one or more transcript folders, summarizes each new or changed
transcript into dense study notes via the Claude API, and rebuilds a
single course-notes.md from all the per-file summaries.

Per-file summaries are kept in summaries/ so a rerun only pays for
new or changed transcripts. course-notes.md is regenerated from them
on every run.

Usage:
    python summarize_transcripts.py                  # default folder
    python summarize_transcripts.py DIR1 DIR2 ...    # extra folders

Requires ANTHROPIC_API_KEY in the environment.
"""

import json
import sys
import time
from pathlib import Path

from anthropic import Anthropic

BASE = Path.home() / "dev" / "seminar-copilot"
DEFAULT_DIRS = [BASE / "transcripts"]
SUMMARY_DIR = BASE / "summaries"
STATE_FILE = SUMMARY_DIR / ".state.json"
OUTPUT = BASE / "course-notes.md"
MODEL = "claude-sonnet-5"
CHUNK_CHARS = 100_000  # split very long transcripts into pieces this size

SUMMARY_PROMPT = """You are building compact study notes from a class
transcript. Produce dense, factual notes covering: concepts taught and
their definitions, formulas or algorithms mentioned, concrete examples
the instructor used, tools or libraries named, anything the instructor
emphasized or flagged as important for exams or the capstone, and
assignments or deadlines announced. Plain prose and short lines, no
markdown headers, no commentary about the transcript itself, no filler.
If the transcript is mostly logistics or off-topic talk, say so in one
line and extract whatever substance exists. The transcript is
auto-generated speech-to-text, so silently correct obvious
mistranscriptions of technical terms."""


def summarize_text(client: Anthropic, text: str) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def summarize_file(client: Anthropic, path: Path) -> str:
    text = path.read_text(errors="replace")
    if len(text) <= CHUNK_CHARS:
        return summarize_text(client, text)
    # Long transcript: summarize pieces, then merge the piece-summaries.
    pieces = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
    partials = [summarize_text(client, p) for p in pieces]
    return summarize_text(
        client,
        "These are sequential partial notes from one long class. Merge "
        "them into one set of notes, removing duplication:\n\n"
        + "\n\n---\n\n".join(partials),
    )


def main():
    dirs = [Path(d).expanduser() for d in sys.argv[1:]] or DEFAULT_DIRS
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    client = Anthropic()

    # Collect candidate transcripts
    candidates = []
    for d in dirs:
        if not d.is_dir():
            print(f"[skip] not a folder: {d}")
            continue
        for p in sorted(d.glob("*.txt")) + sorted(d.glob("*.md")):
            candidates.append(p)

    today_tag = time.strftime("%Y-%m-%d")
    done, skipped = 0, 0
    for p in candidates:
        key = str(p)
        mtime = p.stat().st_mtime
        if today_tag in p.name:
            print(f"[skip] {p.name} (today's file, still growing)")
            skipped += 1
            continue
        if state.get(key) == mtime:
            skipped += 1
            continue
        print(f"[summarizing] {p.name} ({p.stat().st_size} bytes)...")
        try:
            summary = summarize_file(client, p)
        except Exception as e:
            print(f"[error] {p.name}: {e}", file=sys.stderr)
            continue
        (SUMMARY_DIR / (p.stem + ".md")).write_text(
            f"### {p.stem}\n\n{summary}\n"
        )
        state[key] = mtime
        done += 1

    STATE_FILE.write_text(json.dumps(state, indent=2))

    # Rebuild course-notes.md from every per-file summary, oldest first
    parts = [f.read_text() for f in sorted(SUMMARY_DIR.glob("*.md"))]
    OUTPUT.write_text(
        "# Course notes (auto-summarized class transcripts)\n\n"
        + "\n\n".join(parts)
    )
    total_chars = OUTPUT.stat().st_size
    print(f"\nSummarized {done} new, skipped {skipped}. "
          f"course-notes.md rebuilt: {total_chars} chars "
          f"(~{total_chars // 4} tokens per question when injected).")


if __name__ == "__main__":
    main()
