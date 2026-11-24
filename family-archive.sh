#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python seminar_copilot.py --brief ~/dev/seminar-copilot/ARCHIVE_QA_BRIEF.md --source combined.monitor "$@"
