#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python seminar_copilot.py --context ~/dev/seminar-copilot/course-digest.md ~/dev/seminar-copilot/capstone.md demo-script.md demo-qa.md ~/dev/seminar-copilot/tooling.md ~/dev/seminar-copilot/interviews/ai4i-rehearsals.txt --source combined.monitor "$@"