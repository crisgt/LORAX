import runpod
import subprocess
import requests
import time
import os
import base64
import json

COMFY_PORT = "8188"
COMFY_URL = f"http://127.0.0.1:{COMFY_PORT}"
COMFY_CMD = [
    "python",
    "/app/ComfyUI/main.py",
    "--listen", "127.0.0.1",
    "--port", COMFY_PORT,
    "--output-directory", "/tmp/output",
    "--disable-auto-launch"
]

def start_comfy():
    process = subprocess.Popen(
        COMFY_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )

    for _ in range(60):
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.status_code == 200:
                return process
        except:
            pass
        time.sleep(1)

    process.kill()
    raise RuntimeError("ComfyUI failed to start")

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
