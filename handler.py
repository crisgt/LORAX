import runpod
import json
import base64
import os
import sys
from io import BytesIO
from PIL import Image

# Add ComfyUI to path
sys.path.append('/app/ComfyUI')

# Import ComfyUI modules
from execution import PromptExecutor
from server import PromptServer
import folder_paths

# Set model paths to network volume
folder_paths.folder_names_and_paths["unet"] = (["/runpod-volume/ComfyUI/models/unet"], [".safetensors"])
folder_paths.folder_names_and_paths["vae"] = (["/runpod-volume/ComfyUI/models/vae"], [".safetensors"])
folder_paths.folder_names_and_paths["clip"] = (["/runpod-volume/ComfyUI/models/clip"], [".safetensors"])
folder_paths.folder_names_and_paths["loras"] = (["/runpod-volume/ComfyUI/models/loras"], [".safetensors"])

print("Loading ComfyUI...")

def load_workflow():
    """Load the workflow JSON"""
    with open('/app/workflow.json', 'r') as f:
        return json.load(f)

# Load workflow at startup
WORKFLOW = load_workflow()

def handler(event):
    """
    Handle ComfyUI workflow execution
    
    Expected input:
    {
        "prompt": "your prompt here",
        "width": 832,  # optional
        "height": 1216,  # optional
        "steps": 35,  # optional
        "guidance": 4.0,  # optional
        "seed": null  # optional, null for random
    }
    """
    try:
        input_data = event["input"]
        
        # Get parameters
        prompt = input_data.get("prompt", "a beautiful landscape")
        width = input_data.get("width", 832)
        height = input_data.get("height", 1216)
        steps = input_data.get("steps", 35)
        guidance = input_data.get("guidance", 4.0)
        seed = input_data.get("seed", None)
        
        # Clone workflow
        workflow = json.loads(json.dumps(WORKFLOW))
        
        # Update workflow parameters
        # Update prompt (node 6 - CLIPTextEncode)
        for node in workflow["nodes"]:
            if node["id"] == 6:  # CLIPTextEncode
                node["widgets_values"][0] = prompt
            elif node["id"] == 85:  # CR SDXL Aspect Ratio
                node["widgets_values"][0] = width
                node["widgets_values"][1] = height
            elif node["id"] == 17:  # BasicScheduler
                node["widgets_values"][1] = steps  # steps
            elif node["id"] == 60:  # FluxGuidance
                node["widgets_values"][0] = guidance
            elif node["id"] == 25:  # RandomNoise
                if seed is not None:
                    node["widgets_values"][0] = seed
                    node["widgets_values"][1] = "fixed"
        
        print(f"Executing workflow: {prompt[:50]}... ({width}x{height}, {steps} steps)")
        
        # Execute workflow
        from nodes import NODE_CLASS_MAPPINGS
        executor = PromptExecutor(PromptServer.instance)
        
        # Convert workflow to prompt format
        prompt_data = {str(node["id"]): {
            "inputs": {inp["name"]: inp.get("widget", {}).get("config", None) or inp.get("link")
                      for inp in node.get("inputs", [])},
            "class_type": node["type"]
        } for node in workflow["nodes"]}
        
        # Execute
        output_images = []
        results = executor.execute(prompt_data, "unique_id", {})
        
        # Get output images
        if results and "ui" in results:
            for node_id, node_output in results["ui"].items():
                if "images" in node_output:
                    for img_data in node_output["images"]:
                        if "filename" in img_data:
                            img_path = os.path.join(folder_paths.get_output_directory(), img_data["filename"])
                            img = Image.open(img_path)
                            
                            # Convert to base64
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            output_images.append(img_str)
        
        return {
            "images": output_images,
            "seed": seed,
            "prompt": prompt
        }
        
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

runpod.serverless.start({"handler": handler})
