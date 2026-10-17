#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python interviewer.py --context ~/dev/seminar-copilot/interview.md ~/dev/seminar-copilot/capstone.md ~/dev/seminar-copilot/footnote.md --voice ~/dev/seminar-copilot/voices/en_US-lessac-medium.onnx --source combined.monitor "$@"
