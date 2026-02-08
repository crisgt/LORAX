FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Install ComfyUI dependencies
RUN pip install --no-cache-dir \
    -r /app/ComfyUI/requirements.txt

# Install additional requirements
RUN pip install --no-cache-dir \
    runpod \
    opencv-python \
    scikit-image

# Copy workflow and handler
COPY workflow.json /app/workflow.json
COPY handler.py /app/handler.py

# Set environment variables
ENV PYTHONPATH="${PYTHONPATH}:/app/ComfyUI"
ENV COMFYUI_PATH="/app/ComfyUI"

CMD ["python", "-u", "/app/handler.py"]
