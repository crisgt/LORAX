#!/bin/bash

echo "Starting ComfyUI daemon..."

cd /app/ComfyUI

mkdir -p models
rm -rf models
ln -s /runpod-volume/runpod-slim/ComfyUI models

python main.py \
--listen 0.0.0.0 \
--port 8188 \
--force-fp16 \
--dont-print-server \
--disable-auto-launch
