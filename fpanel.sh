#!/bin/bash
cd ~/dev/seminar-copilot
source venv/bin/activate
export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cublas/lib:$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib
python interviewer.py --persona ~/dev/seminar-copilot/panel-footnote.md --context ~/dev/seminar-copilot/footnote.md ~/dev/footnote/DECISIONS.md ~/dev/footnote/docs/tech-notes.md ~/dev/footnote/docs/deploy.md ~/dev/footnote/server/pipeline/index.js ~/dev/footnote/server/pipeline/adapter.js ~/dev/footnote/server/pipeline/classify.js ~/dev/footnote/server/pipeline/source.js ~/dev/footnote/server/pipeline/policy.js ~/dev/footnote/server/pipeline/invite.js --voice ~/dev/seminar-copilot/voices/en_US-lessac-medium.onnx --source combined.monitor "$@"
