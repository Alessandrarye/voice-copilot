#!/usr/bin/env bash
# Run this on foundry from anywhere. It rewrites ai4i-repo.md, the repo context file demo.sh loads.
set -e
REPO=~/dev/ai4i-capstone
OUT=~/dev/seminar-copilot/ai4i-repo.md
mkdir -p "$(dirname "$OUT")"

{
  echo "# Repository context: ai4i-capstone"
  echo
  echo "Selected source files and notebook text. Code is authoritative for how the system actually behaves."
  echo
  echo "## README.md"; echo '```markdown'; cat "$REPO/README.md"; echo '```'; echo
  for f in backend/app/ml/scorer.py backend/app/ml/train_anomaly.py backend/app/routes/readings.py backend/app/main.py backend/app/models.py scripts/replay.py; do
    if [ -f "$REPO/$f" ]; then
      echo "## $f"; echo '```python'; cat "$REPO/$f"; echo '```'; echo
    fi
  done
  # ESP32 firmware (lives in the Arduino folder, not the repo). Wi-Fi credentials are masked.
  INO=~/Arduino/sketch_oct28a/sketch_oct28a.ino
  if [ -f "$INO" ]; then
    echo "## ESP32 firmware (sketch_oct28a.ino, credentials removed)"; echo '```cpp'
    sed -E 's/^(.*(ssid|password|SSID|PASSWORD)[^=]*=).*/\1 "<removed>";/' "$INO"
    echo '```'; echo
  fi
  echo "## notebooks/ai4i_baseline.ipynb (markdown cells and code, outputs stripped)"
  "$REPO/.venv/bin/jupyter" nbconvert --to markdown --stdout --no-input=False \
      --ClearOutputPreprocessor.enabled=True "$REPO/notebooks/ai4i_baseline.ipynb" 2>/dev/null \
      | grep -v '^!\[' || echo "(nbconvert not available; open the notebook directly)"
} > "$OUT"

echo "wrote $OUT ($(wc -c < "$OUT") bytes)"
