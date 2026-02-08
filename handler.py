import runpod
import json
import subprocess
import os
import time
import requests
import base64

print("Handler starting...", flush=True)

def handler(event):
    """Simple handler that accepts workflow JSON"""
    print("=" * 50, flush=True)
    print("Handler called!", flush=True)
    
    try:
        input_data = event.get("input", {})
        print(f"Received input with keys: {list(input_data.keys())}", flush=True)
        
        # Get workflow
        if "workflow" not in input_data:
            return {"error": "Missing 'workflow' in input"}
        
        workflow = input_data["workflow"]
        print(f"Workflow has {len(workflow.get('nodes', []))} nodes", flush=True)
        
        # Save workflow to temp file
        workflow_file = "/tmp/workflow_api.json"
        with open(workflow_file, 'w') as f:
            json.dump(workflow, f)
        print(f"Saved workflow to {workflow_file}", flush=True)
        
        # Check volume
        volume_path = "/runpod-volume/ComfyUI/models"
        if os.path.exists(volume_path):
            print(f"✓ Volume found at {volume_path}", flush=True)
        else:
            return {"error": f"Volume not found at {volume_path}"}
        
        # Start ComfyUI server
        print("Starting ComfyUI server...", flush=True)
        
        env = os.environ.copy()
        env["COMFYUI_MODEL_PATHS"] = json.dumps({
            "checkpoints": "/runpod-volume/ComfyUI/models/unet",
            "vae": "/runpod-volume/ComfyUI/models/vae",
            "clip": "/runpod-volume/ComfyUI/models/clip",
            "loras": "/runpod-volume/ComfyUI/models/loras",
        })
        
        comfyui_cmd = [
            "python", "/app/ComfyUI/main.py",
            "--listen", "127.0.0.1",
            "--port", "8188",
            "--output-directory", "/tmp/output"
        ]
        
        process = subprocess.Popen(
            comfyui_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Wait for server to be ready
        print("Waiting for ComfyUI to start...", flush=True)
        server_ready = False
        
        for i in range(60):
            try:
                resp = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
                if resp.status_code == 200:
                    server_ready = True
                    print(f"✓ ComfyUI ready after {i+1}s", flush=True)
                    break
            except:
                pass
            time.sleep(1)
        
        if not server_ready:
            process.kill()
            return {"error": "ComfyUI failed to start within 60s"}
        
        # Queue the workflow
        print("Queueing workflow...", flush=True)
        
        queue_url = "http://127.0.0.1:8188/prompt"
        prompt_request = {"prompt": workflow}
        
        resp = requests.post(queue_url, json=prompt_request, timeout=10)
        
        if resp.status_code != 200:
            process.kill()
            return {"error": f"Failed to queue: {resp.text}"}
        
        queue_result = resp.json()
        prompt_id = queue_result.get("prompt_id")
        
        if not prompt_id:
            process.kill()
            return {"error": f"No prompt_id: {queue_result}"}
        
        print(f"✓ Queued with prompt_id: {prompt_id}", flush=True)
        
        # Wait for completion
        print("Waiting for generation...", flush=True)
        output_images = []
        
        for wait_count in range(150):  # 5 minutes max
            try:
                history_resp = requests.get(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=5)
                
                if history_resp.status_code == 200:
                    history = history_resp.json()
                    
                    if prompt_id in history:
                        print(f"Found result in history", flush=True)
                        outputs = history[prompt_id].get("outputs", {})
                        
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                print(f"Found images in node {node_id}", flush=True)
                                
                                for img_info in node_output["images"]:
                                    filename = img_info.get("filename", "")
                                    subfolder = img_info.get("subfolder", "")
                                    
                                    # Download image
                                    img_url = f"http://127.0.0.1:8188/view?filename={filename}&subfolder={subfolder}&type=output"
                                    img_resp = requests.get(img_url, timeout=10)
                                    
                                    if img_resp.status_code == 200:
                                        img_b64 = base64.b64encode(img_resp.content).decode()
                                        output_images.append(img_b64)
                                        print(f"✓ Got image: {filename}", flush=True)
                        
                        if output_images:
                            break
            except Exception as e:
                print(f"Wait loop error: {e}", flush=True)
            
            if wait_count % 10 == 0:
                print(f"Still waiting... ({wait_count}s)", flush=True)
            
            time.sleep(2)
        
        # Cleanup
        process.kill()
        
        if not output_images:
            return {"error": "No images generated"}
        
        print(f"✓ Success! Generated {len(output_images)} image(s)", flush=True)
        
        return {
            "status": "success",
            "images": output_images,
            "prompt_id": prompt_id
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR: {error_trace}", flush=True)
        return {
            "error": str(e),
            "traceback": error_trace
        }

print("Starting RunPod handler...", flush=True)
runpod.serverless.start({"handler": handler})
