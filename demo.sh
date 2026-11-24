#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
export COPILOT_MODE=demo
export CONTEXT_WINDOW_SECONDS=1200
python seminar_copilot.py --context demo-briefing.md demo-slides.md demo-script.md demo-qa.md capstone.md ai4i-repo.md interviews/ai4i-rehearsals.txt --source combined.monitor "$@"
