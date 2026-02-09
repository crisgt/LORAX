import runpod
import requests
import time
import os
import base64
import traceback

COMFY_URL = "http://127.0.0.1:8188"
MODEL_ROOT = "/runpod-volume/runpod-slim/ComfyUI/models"

def fail(stage, err):
    return {
        "status": "failed",
        "stage": stage,
        "error": str(err),
        "traceback": traceback.format_exc()
    }

def wait_for_comfy():
    for i in range(120):
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.status_code == 200:
                return f"ready_after_{i}s"
        except:
            pass
        time.sleep(1)
    raise RuntimeError("Comfy daemon not reachable")

def validate_volume():
    if not os.path.exists(MODEL_ROOT):
        raise RuntimeError("Model volume missing")

    info = {}
    for d in ["unet","clip","vae","loras"]:
        p=f"{MODEL_ROOT}/{d}"
        if os.path.exists(p):
            info[d]=os.listdir(p)[:3]
        else:
            info[d]="missing"
    return info

def queue(prompt):
    r=requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt":prompt},
        timeout=60
    )
    if r.status_code!=200:
        raise RuntimeError(r.text)
    return r.json()["prompt_id"]

def collect(prompt_id):
    imgs=[]
    for _ in range(150):
        r=requests.get(
            f"{COMFY_URL}/history/{prompt_id}",
            timeout=5
        )
        if r.status_code!=200:
            raise RuntimeError("history fetch failed")

        hist=r.json()
        if prompt_id in hist:
            outs=hist[prompt_id]["outputs"]
            for node in outs.values():
                if "images" in node:
                    for img in node["images"]:
                        url=f"{COMFY_URL}/view?filename={img['filename']}&subfolder={img['subfolder']}&type=output"
                        ir=requests.get(url,timeout=10)
                        if ir.status_code==200:
                            imgs.append(
                                base64.b64encode(ir.content).decode()
                            )
            if imgs:
                return imgs
        time.sleep(2)
    raise RuntimeError("image timeout")

def handler(event):
    try:
        stage="daemon_check"
        wait_status=wait_for_comfy()

        stage="volume_check"
        volume=validate_volume()

        stage="input"
        data=event.get("input",{})
        prompt=data.get("prompt")
        if not isinstance(prompt,dict):
            return fail(stage,"prompt missing or invalid")

        stage="queue"
        pid=queue(prompt)

        stage="collect"
        images=collect(pid)

        return {
            "status":"success",
            "prompt_id":pid,
            "images":images,
            "daemon":wait_status,
            "volume":volume
        }

    except Exception as e:
        return fail(stage,e)

runpod.serverless.start({"handler":handler})
