#!/usr/bin/env python3
"""
One-time patch for seminar_copilot.py:
  1. CONTEXT_WINDOW_SECONDS becomes env-configurable (demo.sh can set 1200).
  2. A demo-mode addendum is appended to SYSTEM_PROMPT when COPILOT_MODE=demo.
  3. The Claude stream call retries up to 3 times on connection errors.

Run from ~/dev/seminar-copilot:   python patch_copilot.py
A backup is written to seminar_copilot.py.bak-<timestamp>.
"""
import re, sys, time
from pathlib import Path

p = Path("seminar_copilot.py")
src = p.read_text()
orig = src

# ---------- 1. env-configurable context window ----------
src, n1 = re.subn(
    r'^CONTEXT_WINDOW_SECONDS\s*=\s*120(\s*#.*)?$',
    'CONTEXT_WINDOW_SECONDS = int(os.environ.get("CONTEXT_WINDOW_SECONDS", "120"))  # rolling transcript context sent to Claude',
    src, count=1, flags=re.M)
if n1 != 1:
    sys.exit("could not find CONTEXT_WINDOW_SECONDS = 120")
if not re.search(r'^import os\b|^import .*\bos\b', src, re.M):
    src = src.replace("import argparse", "import os\nimport argparse", 1) if "import argparse" in src \
          else "import os\n" + src

# ---------- 2. demo-mode system prompt addendum ----------
DEMO_ADDENDUM = '''
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
'''
m = re.search(r'^SYSTEM_PROMPT = \(\n(?:.*\n)*?\)\n', src, re.M)
if not m:
    sys.exit("could not find the SYSTEM_PROMPT block")
src = src[:m.end()] + DEMO_ADDENDUM + src[m.end():]

# ---------- 3. retry around the stream call ----------
lines = src.split("\n")
start = next((i for i, l in enumerate(lines) if l.strip().startswith("async with claude.messages.stream(")), None)
if start is None:
    sys.exit("could not find 'async with claude.messages.stream('")
indent = len(lines[start]) - len(lines[start].lstrip())
# block ends at the first later non-blank line indented <= the 'async with' line,
# skipping the ') as stream:' closer, which shares that indent.
end = start + 1
while end < len(lines):
    l = lines[end]
    if l.strip() and (len(l) - len(l.lstrip())) <= indent and not l.strip().startswith(")"):
        break
    end += 1
pad = " " * indent
block = lines[start:end]
wrapped = [
    pad + "for _attempt in range(3):",
    pad + "    try:",
] + ["        " + l if l.strip() else l for l in block] + [
    pad + "        break",
    pad + "    except (APIConnectionError, APITimeoutError) as _e:",
    pad + "        if _attempt == 2:",
    pad + "            raise",
    pad + '        print(f"[claude] connection problem, retrying ({_attempt + 1}/2): {_e}")',
    pad + "        answer = \"\"",
    pad + "        started = False",
    pad + "        await asyncio.sleep(1.5)",
]
lines[start:end] = wrapped
src = "\n".join(lines)

# imports for the retry
if "APIConnectionError" not in orig:
    src = src.replace("from anthropic import AsyncAnthropic",
                      "from anthropic import AsyncAnthropic, APIConnectionError, APITimeoutError", 1)
if not re.search(r'^import asyncio\b', src, re.M):
    src = "import asyncio\n" + src

bak = p.with_name(f"seminar_copilot.py.bak-{time.strftime('%Y%m%d-%H%M%S')}")
bak.write_text(orig)
p.write_text(src)
print(f"patched seminar_copilot.py (backup: {bak.name})")
print("now add to demo.sh, before the python line:")
print("  export COPILOT_MODE=demo")
print("  export CONTEXT_WINDOW_SECONDS=1200")
