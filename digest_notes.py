#!/usr/bin/env python3
"""
Digest pass for the seminar copilot.

Reads every per-class summary in summaries/ and merges them into ONE
compact, topic-organized digest (course-digest.md) sized for cheap
per-question context injection. The per-class summaries and the full
course-notes.md are left untouched.

Run it after summarize_transcripts.py whenever new classes have been
added (weekly is plenty). Each run rebuilds the digest from scratch.

Usage:
    python digest_notes.py

Requires ANTHROPIC_API_KEY in the environment.
"""

import sys
from pathlib import Path

from anthropic import Anthropic

BASE = Path.home() / "dev" / "seminar-copilot"
SUMMARY_DIR = BASE / "summaries"
OUTPUT = BASE / "course-digest.md"
MODEL = "claude-sonnet-5"
TARGET_CHARS = 20_000       # aim for roughly this size
CHUNK_CHARS = 300_000       # split input if the summaries outgrow one call

DIGEST_PROMPT = f"""You are building ONE compact course digest from many
per-class study notes. Reorganize by TOPIC, not by day: merge everything
said about a concept across all classes into one place. Keep definitions,
formulas, algorithms, named tools and libraries, and anything flagged as
exam- or capstone-relevant. Note instructor emphasis where it existed.
Include a short final section listing assignments/deadlines mentioned,
newest last. Drop logistics, repetition, and filler entirely.
Plain prose under simple topic headers. Target at most
{TARGET_CHARS} characters total. Dense beats complete: if forced to
choose, keep what a student would need to answer questions about the
course."""


def call(client: Anthropic, text: str) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=DIGEST_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def main():
    files = sorted(SUMMARY_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No summaries found in {SUMMARY_DIR}. Run summarize_transcripts.py first.")

    full = "\n\n".join(f.read_text() for f in files)
    print(f"[digest] merging {len(files)} summaries ({len(full)} chars)...")

    client = Anthropic()
    if len(full) <= CHUNK_CHARS:
        digest = call(client, full)
    else:
        pieces = [full[i:i + CHUNK_CHARS] for i in range(0, len(full), CHUNK_CHARS)]
        partials = [call(client, p) for p in pieces]
        print(f"[digest] merged {len(pieces)} chunks, combining...")
        digest = call(
            client,
            "These are partial digests of one course. Merge them into one "
            "digest under the same rules:\n\n" + "\n\n---\n\n".join(partials),
        )

    OUTPUT.write_text("# Course digest (topic-organized, auto-generated)\n\n" + digest)
    size = OUTPUT.stat().st_size
    print(f"[digest] course-digest.md written: {size} chars "
          f"(~{size // 4} tokens per question when injected).")


if __name__ == "__main__":
    main()
