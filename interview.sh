#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python seminar_copilot.py --context ~/dev/seminar-copilot/interview.md ~/dev/seminar-copilot/capstone.md ~/dev/seminar-copilot/footnote.md --source combined.monitor "$@"
