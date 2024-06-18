## Imports
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

global model_path
global llm

def load_llm():
    ## Define model name and file name
    # model_name = "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF"
    # model_file = "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

    ## Use the following model_name and model_file if you have 8gb ram or less
    model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
    model_file = "mistral-7b-openorca.Q4_K_M.gguf"

    ## Use the following model_name and model_file if you have 16gb ram or less
    # model_name = "TTheBloke/vicuna-13B-v1.5-16K-GGUF"
    # model_file = "vicuna-13b-v1.5-16k.Q4_K_M.gguf"
    ## Download the model
    model_path = hf_hub_download(model_name, filename=model_file)

    return model_path

def instantiate_llm(path):
    model_kwargs = {
      "n_ctx":4096,    # Context length to use
      "n_threads":4,   # Number of CPU threads to use
      "n_gpu_layers":0,# Number of model layers to offload to GPU. Set to 0 if only using CPU
    }

    ## Instantiate model from downloaded file
    llm = Llama(model_path=path, **model_kwargs)
    return llm

def run_inference(input, llm):
    ## Generation kwargs
    generation_kwargs = {
        "max_tokens":1000, # Max number of new tokens to generate
        "stop":["<|endoftext|>", "</s>"], # Text sequences to stop generation on
        "echo":False, # Echo the prompt in the output
        "top_k":1 # This is essentially greedy decoding, since the model will always return the highest-probability token. Set this value > 1 for sampling decoding
    }

    ## Run inference
    prompt = input
    res = llm(prompt, **generation_kwargs) # Res is a dictionary

    ## Unpack and the generated text from the LLM response dictionary and print it
    # print(res["choices"][0]["text"])
    return res["choices"][0]["text"]

# example usage
# model_path = load_llm()
# llm = instantiate_llm()
# result = run_inference("meaning of life")
# print(result)