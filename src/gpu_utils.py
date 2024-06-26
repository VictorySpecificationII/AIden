import GPUtil

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

def check_gpu_compatibility(gpu_info, startup):
    if startup:
        print("Startup Check: Checking GPU availability on host...")
    if gpu_info is None:
        if startup:
            print("Error: No GPU found. You are either running on Integrated Graphics, or there is an issue with your GPU.")
        return False
    # Define the minimum requirements for the language models
    min_memory = 8 * 1024  # 8 GB
    min_compute_capability = 7.0  # CUDA compute capability 7.0 or higher
    # Check if the GPU meets the minimum requirements
    if gpu_info["memory_total"] < min_memory:
        if startup:
            print(f"Error: GPU has {gpu_info['memory_total'] / 1024} GB of memory, which is less than the minimum requirement of {min_memory / 1024} GB")
        return False
    if gpu_info["compute_capability"] < min_compute_capability:
        if startup:
            print(f"Error: GPU has compute capability {gpu_info['compute_capability']}, which is less than the minimum requirement of {min_compute_capability}")
        return False
    return True
