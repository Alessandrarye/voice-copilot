#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python seminar_copilot.py --context ~/dev/seminar-copilot/course-digest.md ~/dev/seminar-copilot/capstone.md ~/dev/seminar-copilot/tooling.md --source alsa_output.pci-0000_0f_00.6.analog-stereo.monitor "$@"