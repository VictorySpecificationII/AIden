import gpu_utils

#The idea with this function is to automatically set the GPU layers that the LLM can use, depending on the hardware present on the machine.    
def llm_gpu_layers():
    gpu_info = gpu_utils.get_gpu_info()
    if gpu_utils.check_gpu_compatibility(gpu_info, False):
        #print(f"LLM: Using 2 layers on GPU for LLM execution.")
        return 2
    else:
        #print(f"LLM: Using 0 layers on GPU for LLM execution.")
        return 0