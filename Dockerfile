FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git wget ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

RUN pip install --no-cache-dir -r /app/ComfyUI/requirements.txt
RUN pip install --no-cache-dir xformers runpod requests

COPY handler.py /app/handler.py
COPY start_comfy_daemon.sh /app/start_comfy_daemon.sh

RUN chmod +x /app/start_comfy_daemon.sh

CMD /app/start_comfy_daemon.sh & python -u /app/handler.py


