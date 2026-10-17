#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python interviewer.py --persona ~/dev/seminar-copilot/panel-ai4i.md --context ~/dev/seminar-copilot/capstone.md --voice ~/dev/seminar-copilot/voices/en_US-lessac-medium.onnx --source combined.monitor "$@"
