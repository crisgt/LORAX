import runpod
import requests
import subprocess
import time
import os
import base64
import traceback
import json

COMFY_URL = "http://127.0.0.1:8188"

MODEL_BASE = "/runpod-volume/runpod-slim/ComfyUI"
MODEL_PATH = f"{MODEL_BASE}/models"

COMFY_CMD = [
    "python",
    "/app/ComfyUI/main.py",
    "--listen", "127.0.0.1",
    "--port", "8188",
    "--disable-auto-launch",
    "--output-directory", "/tmp/output",
    "--extra-model-paths-config",
    f"{MODEL_BASE}/extra_model_paths.yaml"
]

# --------------------------------------------------
# Utilities
# --------------------------------------------------

def fail(stage, error, extra=None):
    return {
        "status": "failed",
        "stage": stage,
        "error": str(error),
        "extra": extra,
        "traceback": traceback.format_exc()
    }

# --------------------------------------------------
# Validation
# --------------------------------------------------

def validate_volume():
    if not os.path.exists(MODEL_BASE):
        raise RuntimeError(f"Volume missing: {MODEL_BASE}")

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"Model folder missing: {MODEL_PATH}")

    summary = {}

    for sub in ["unet", "vae", "clip", "loras"]:
        p = f"{MODEL_PATH}/{sub}"
        if os.path.exists(p):
            summary[sub] = os.listdir(p)[:5]
        else:
            summary[sub] = "missing"

    return summary

# --------------------------------------------------
# Comfy Lifecycle
# --------------------------------------------------

def ensure_comfy():
    try:
        r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
        if r.status_code == 200:
            return "already_running"
    except:
        pass

    subprocess.Popen(
        COMFY_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )

    for i in range(60):
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.status_code == 200:
                return f"started_in_{i+1}s"
        except:
            pass
        time.sleep(1)

    raise RuntimeError("ComfyUI failed to start")

# --------------------------------------------------
# Execution
# --------------------------------------------------

def queue_prompt(prompt):
    r = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": prompt},
        timeout=60
    )

    if r.status_code != 200:
        raise RuntimeError(f"Queue failed: {r.text}")

    data = r.json()

    if "prompt_id" not in data:
        raise RuntimeError(f"No prompt_id returned: {data}")

    return data["prompt_id"]

def collect_images(prompt_id):
    images = []

    for tick in range(150):
        r = requests.get(
            f"{COMFY_URL}/history/{prompt_id}",
            timeout=5
        )

        if r.status_code != 200:
            raise RuntimeError(f"History fetch failed: {r.text}")

        history = r.json()

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})

            for node_id, node in outputs.items():
                if "images" in node:
                    for img in node["images"]:
                        url = (
                            f"{COMFY_URL}/view?"
                            f"filename={img['filename']}&"
                            f"subfolder={img['subfolder']}&"
                            f"type=output"
                        )

                        ir = requests.get(url, timeout=10)

                        if ir.status_code == 200:
                            images.append(
                                base64.b64encode(
                                    ir.content
                                ).decode()
                            )
                        else:
                            raise RuntimeError(
                                f"Image download failed: {url}"
                            )

            if images:
                return images

        time.sleep(2)

    raise RuntimeError("Timeout waiting for images")

# --------------------------------------------------
# Handler
# --------------------------------------------------

def handler(event):
    try:
        stage = "input_validation"

        data = event.get("input", {})

        if "prompt" not in data:
            return fail(stage, "Missing input.prompt")

        prompt = data["prompt"]

        if not isinstance(prompt, dict):
            return fail(stage, "prompt must be JSON object")

        stage = "volume_validation"
        volume_summary = validate_volume()

        stage = "comfy_start"
        comfy_status = ensure_comfy()

        stage = "queue_prompt"
        prompt_id = queue_prompt(prompt)

        stage = "collect_images"
        images = collect_images(prompt_id)

        return {
            "status": "success",
            "stage": "complete",
            "prompt_id": prompt_id,
            "images": images,
            "volume_summary": volume_summary,
            "comfy_status": comfy_status
        }

    except Exception as e:
        return fail(stage, e)

# --------------------------------------------------

runpod.serverless.start({"handler": handler})    raise RuntimeError("ComfyUI failed to start")

def queue_prompt(prompt):
    r = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": prompt},
        timeout=30
    )

    if r.status_code != 200:
        raise RuntimeError(r.text)

    data = r.json()
    return data.get("prompt_id")

def wait_for_images(prompt_id):
    images = []

    for _ in range(150):
        try:
            r = requests.get(
                f"{COMFY_URL}/history/{prompt_id}",
                timeout=5
            )

            if r.status_code == 200:
                hist = r.json()

                if prompt_id in hist:
                    outputs = hist[prompt_id].get("outputs", {})

                    for node in outputs.values():
                        if "images" in node:
                            for img in node["images"]:
                                url = (
                                    f"{COMFY_URL}/view?"
                                    f"filename={img['filename']}&"
                                    f"subfolder={img['subfolder']}&"
                                    f"type=output"
                                )

                                img_r = requests.get(url, timeout=10)

                                if img_r.status_code == 200:
                                    images.append(
                                        base64.b64encode(
                                            img_r.content
                                        ).decode()
                                    )
                    if images:
                        return images
        except:
            pass

        time.sleep(2)

    return []

def handler(event):
    try:
        input_data = event.get("input", {})

        if "prompt" not in input_data:
            return {"error": "Missing input.prompt"}

        prompt = input_data["prompt"]

        if not isinstance(prompt, dict):
            return {"error": "prompt must be JSON object"}

        if not os.path.exists("/runpod-volume/ComfyUI/models"):
            return {"error": "Model volume missing"}

        process = start_comfy()

        prompt_id = queue_prompt(prompt)

        if not prompt_id:
            process.kill()
            return {"error": "No prompt_id returned"}

        images = wait_for_images(prompt_id)

        process.kill()

        if not images:
            return {"error": "No images generated"}

        return {
            "status": "success",
            "prompt_id": prompt_id,
            "images": images
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

runpod.serverless.start({"handler": handler})
