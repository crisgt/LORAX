import runpod
import json
import base64
import subprocess
import os
import time
import requests
from PIL import Image
from io import BytesIO

def handler(event):
    """
    Handle ComfyUI workflow execution
    
    Expected input:
    {
        "workflow": {...},  // Full ComfyUI workflow JSON
        "prompt": "optional override",  // Optional: overrides prompt in workflow
        "seed": null  // Optional: overrides seed in workflow
    }
    
    OR for simple text-to-image without full workflow:
    {
        "prompt": "your prompt here",
        "width": 832,
        "height": 1216,
        "steps": 35,
        "guidance": 4.0,
        "seed": null
    }
    """
    try:
        input_data = event["input"]
        
        # Check if workflow is provided
        if "workflow" not in input_data:
            return {
                "error": "No workflow provided. Please include 'workflow' key with ComfyUI workflow JSON"
            }
        
        workflow = input_data["workflow"]
        
        # Optional overrides
        prompt_override = input_data.get("prompt", None)
        seed_override = input_data.get("seed", None)
        
        # Apply overrides if provided
        if prompt_override:
            print(f"Overriding prompt: {prompt_override[:50]}...")
            for node in workflow["nodes"]:
                if node.get("type") == "CLIPTextEncode":
                    if "widgets_values" in node and len(node["widgets_values"]) > 0:
                        node["widgets_values"][0] = prompt_override
                        break
        
        if seed_override is not None:
            print(f"Overriding seed: {seed_override}")
            for node in workflow["nodes"]:
                if node.get("type") == "RandomNoise":
                    if "widgets_values" in node and len(node["widgets_values"]) >= 2:
                        node["widgets_values"][0] = seed_override
                        node["widgets_values"][1] = "fixed"
                        break
        
        # Generate unique ID for this request
        import random
        request_id = random.randint(100000, 999999)
        
        print(f"Processing workflow request #{request_id}")
        
        # Start ComfyUI server in background
        print("Starting ComfyUI server...")
        comfyui_process = subprocess.Popen(
            ["python", "/app/ComfyUI/main.py", "--listen", "127.0.0.1", "--port", "8188"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        max_startup_wait = 30
        server_ready = False
        for i in range(max_startup_wait):
            try:
                response = requests.get("http://127.0.0.1:8188/system_stats", timeout=1)
                if response.status_code == 200:
                    server_ready = True
                    print(f"ComfyUI server ready after {i+1}s")
                    break
            except:
                pass
            time.sleep(1)
        
        if not server_ready:
            comfyui_process.kill()
            return {"error": "ComfyUI server failed to start"}
        
        # Convert workflow to API prompt format
        prompt_data = {"prompt": {}}
        
        for node in workflow["nodes"]:
            node_id = str(node["id"])
            node_inputs = {}
            
            # Process inputs
            if "inputs" in node:
                for inp in node["inputs"]:
                    inp_name = inp["name"]
                    if "link" in inp and inp["link"] is not None:
                        # This is a link to another node - skip for now
                        pass
                    elif "widget" in inp:
                        # Widget input
                        node_inputs[inp_name] = inp["widget"].get("value")
            
            # Add widget values
            if "widgets_values" in node and node["widgets_values"]:
                # Get widget parameter names from node type
                # For common nodes, map widget values
                if node["type"] == "CLIPTextEncode" and len(node["widgets_values"]) > 0:
                    node_inputs["text"] = node["widgets_values"][0]
                elif node["type"] == "KSamplerSelect" and len(node["widgets_values"]) > 0:
                    node_inputs["sampler_name"] = node["widgets_values"][0]
                elif node["type"] == "RandomNoise" and len(node["widgets_values"]) >= 2:
                    node_inputs["noise_seed"] = node["widgets_values"][0]
                elif node["type"] == "BasicScheduler" and len(node["widgets_values"]) >= 3:
                    node_inputs["scheduler"] = node["widgets_values"][0]
                    node_inputs["steps"] = node["widgets_values"][1]
                    node_inputs["denoise"] = node["widgets_values"][2]
                elif node["type"] == "FluxGuidance" and len(node["widgets_values"]) > 0:
                    node_inputs["guidance"] = node["widgets_values"][0]
                elif node["type"] == "UNETLoader" and len(node["widgets_values"]) >= 2:
                    node_inputs["unet_name"] = node["widgets_values"][0]
                    node_inputs["weight_dtype"] = node["widgets_values"][1]
                elif node["type"] == "VAELoader" and len(node["widgets_values"]) > 0:
                    node_inputs["vae_name"] = node["widgets_values"][0]
                elif node["type"] == "DualCLIPLoader" and len(node["widgets_values"]) >= 2:
                    node_inputs["clip_name1"] = node["widgets_values"][0]
                    node_inputs["clip_name2"] = node["widgets_values"][1]
                    if len(node["widgets_values"]) >= 3:
                        node_inputs["type"] = node["widgets_values"][2]
                elif node["type"] == "LoraLoaderModelOnly" and len(node["widgets_values"]) >= 2:
                    node_inputs["lora_name"] = node["widgets_values"][0]
                    node_inputs["strength_model"] = node["widgets_values"][1]
                elif node["type"] == "ModelSamplingFlux" and len(node["widgets_values"]) >= 4:
                    node_inputs["max_shift"] = node["widgets_values"][0]
                    node_inputs["base_shift"] = node["widgets_values"][1]
                    node_inputs["width"] = node["widgets_values"][2]
                    node_inputs["height"] = node["widgets_values"][3]
                elif node["type"] == "SaveImage" and len(node["widgets_values"]) > 0:
                    node_inputs["filename_prefix"] = node["widgets_values"][0]
            
            prompt_data["prompt"][node_id] = {
                "inputs": node_inputs,
                "class_type": node["type"]
            }
        
        # Process links
        for link in workflow.get("links", []):
            # link format: [link_id, source_node, source_slot, target_node, target_slot, type]
            if len(link) >= 6:
                source_node = str(link[1])
                source_slot = link[2]
                target_node = str(link[3])
                target_slot = link[4]
                
                # Find the output name from source node
                if source_node in prompt_data["prompt"]:
                    source_node_data = next((n for n in workflow["nodes"] if n["id"] == int(source_node)), None)
                    if source_node_data and "outputs" in source_node_data:
                        if source_slot < len(source_node_data["outputs"]):
                            output_name = source_node_data["outputs"][source_slot]["name"]
                            
                            # Find input name from target node
                            target_node_data = next((n for n in workflow["nodes"] if n["id"] == int(target_node)), None)
                            if target_node_data and "inputs" in target_node_data:
                                if target_slot < len(target_node_data["inputs"]):
                                    input_name = target_node_data["inputs"][target_slot]["name"]
                                    
                                    # Create the link in prompt format
                                    prompt_data["prompt"][target_node]["inputs"][input_name] = [source_node, source_slot]
        
        # Queue the prompt
        print("Queueing workflow...")
        url = "http://127.0.0.1:8188/prompt"
        response = requests.post(url, json=prompt_data, timeout=10)
        
        if response.status_code != 200:
            comfyui_process.kill()
            return {"error": f"Failed to queue workflow: {response.text}"}
        
        result = response.json()
        prompt_id = result.get("prompt_id")
        
        if not prompt_id:
            comfyui_process.kill()
            return {"error": f"No prompt_id returned: {result}"}
        
        print(f"Workflow queued with prompt_id: {prompt_id}")
        
        # Wait for completion
        max_wait = 300  # 5 minutes
        start_time = time.time()
        output_images = []
        
        while time.time() - start_time < max_wait:
            try:
                history_response = requests.get(
                    f"http://127.0.0.1:8188/history/{prompt_id}",
                    timeout=5
                )
                
                if history_response.status_code == 200:
                    history = history_response.json()
                    
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        
                        # Find SaveImage node outputs
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for img_info in node_output["images"]:
                                    # Download image
                                    filename = img_info.get("filename", "")
                                    subfolder = img_info.get("subfolder", "")
                                    img_type = img_info.get("type", "output")
                                    
                                    img_url = f"http://127.0.0.1:8188/view?filename={filename}&subfolder={subfolder}&type={img_type}"
                                    
                                    img_response = requests.get(img_url, timeout=10)
                                    
                                    if img_response.status_code == 200:
                                        img_str = base64.b64encode(img_response.content).decode()
                                        output_images.append(img_str)
                        
                        if output_images:
                            print(f"Generated {len(output_images)} image(s)")
                            break
            except Exception as e:
                print(f"Error checking status: {e}")
            
            time.sleep(2)
        
        # Cleanup
        comfyui_process.kill()
        
        if not output_images:
            return {"error": "No images generated within timeout period"}
        
        return {
            "images": output_images,
            "prompt_id": prompt_id,
            "request_id": request_id
        }
        
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

runpod.serverless.start({"handler": handler})
