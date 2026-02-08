FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

RUN pip install --no-cache-dir \
    -r /app/ComfyUI/requirements.txt

RUN pip install --no-cache-dir \
    runpod \
    requests

COPY handler.py /app/handler.py

ENV PYTHONPATH="${PYTHONPATH}:/app/ComfyUI"

CMD ["python", "-u", "/app/handler.py"]
