from dotenv import load_dotenv
import os
import openai
import mistral_onboard_llm
import llama2_onboard_llm
import GPUtil


def print_banner():
    ascii_art = """
        _    ___    _            
       / \  |_ _|__| | ___ _ __  
      / _ \  | |/ _` |/ _ \ '_ \ 
     / ___ \ | | (_| |  __/ | | |
    /_/   \_\___\__,_|\___|_| |_|
    
   Artificial Intelligence Co-Pilot

    """
    print(ascii_art)

def check_local_llm_availability():
    print("Startup Check: Checking LLM models in ~/.cache/huggingface/hub...")
    # Get the paths to the model files
    mistral_path = mistral_onboard_llm.load_llm()
    llama2_path = llama2_onboard_llm.load_llm()

    # Check if the model files exist
    if not os.path.isfile(mistral_path):
        print(f"Error: Mistral model file not found at {mistral_path}.")
        mistral_found = False
    else:
        print(f"Success: Mistral model file found at {mistral_path}.")
        mistral_found = True

    if not os.path.isfile(llama2_path):
        print(f"Error: Llama2 model file not found at {llama2_path}.")
        llama2_found = False
    else:
        print(f"Success: Llama2 model file found at {llama2_path}.")
        llama2_found = True
    
    if (llama2_found or mistral_found):
        return True
    else:
        print(f"LLM's not found in ~/.chache/huggingface/hub directory. Exiting...")
        return False

def check_local_gpu_availability():
    gpu_info = get_gpu_info()
    if not check_gpu_compatibility(gpu_info):
        return False
    else:
        return True
    
#The idea with this function is to automatically set the GPU layers that the LLM can use, depending on the hardware present on the machine.    
def llm_gpu_layers():
    gpu_info = get_gpu_info()
    if check_gpu_compatibility(gpu_info):
        #print(f"LLM: Using 2 layers on GPU for LLM execution.")
        return 2
    else:
        #print(f"LLM: Using 0 layers on GPU for LLM execution.")
        return 0
        
def get_gpu_info():
    gpus = GPUtil.getGPUs()
    if len(gpus) == 0:
        return None
    gpu = gpus[0]
    return {
        "name": gpu.name,
        "memory_total": gpu.memoryTotal,
        "compute_capability": gpu.compute_capability
    }

def check_gpu_compatibility(gpu_info):
    print("Startup Check: Checking GPU availability on host...")
    if gpu_info is None:
        print("Error: No GPU found. You are either running on Integrated Graphics, or there is an issue with your GPU.")
        return False
    # Define the minimum requirements for the language models
    min_memory = 8 * 1024  # 8 GB
    min_compute_capability = 7.0  # CUDA compute capability 7.0 or higher
    # Check if the GPU meets the minimum requirements
    if gpu_info["memory_total"] < min_memory:
        print(f"Error: GPU has {gpu_info['memory_total'] / 1024} GB of memory, which is less than the minimum requirement of {min_memory / 1024} GB")
        return False
    if gpu_info["compute_capability"] < min_compute_capability:
        print(f"Error: GPU has compute capability {gpu_info['compute_capability']}, which is less than the minimum requirement of {min_compute_capability}")
        return False
    return True

