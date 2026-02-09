#!/bin/bash

echo "[DAEMON] Starting ComfyUI..."

python /app/ComfyUI/main.py \
  --listen 127.0.0.1 \
  --port 8188 \
  --disable-auto-launch \
  --dont-print-server \
  --output-directory /tmp/output \
  --extra-model-paths-config \
  /runpod-volume/runpod-slim/ComfyUI/extra_model_paths.yaml
