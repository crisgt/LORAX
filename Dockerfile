FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV COMFYUI_PATH=/app/ComfyUI
ENV MODEL_PATH=/runpod-volume/runpod-slim/ComfyUI

RUN apt-get update && apt-get install -y \
    git wget curl ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip uninstall -y torch torchvision torchaudio

RUN pip install --no-cache-dir \
torch==2.3.1 \
torchvision==0.18.1 \
--index-url https://download.pytorch.org/whl/cu121

RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

RUN pip install --no-cache-dir -r /app/ComfyUI/requirements.txt
RUN pip install --no-cache-dir xformers runpod requests aiohttp

COPY handler.py /app/handler.py
COPY start_comfy_daemon.sh /app/start_comfy_daemon.sh

RUN chmod +x /app/start_comfy_daemon.sh

CMD ["/bin/bash","-c","/app/start_comfy_daemon.sh & sleep 10 && python -u /app/handler.py"]
