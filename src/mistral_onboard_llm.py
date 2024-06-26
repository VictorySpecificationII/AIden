from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download
import startup_functions


def load_llm():
    ## Define model name and file name
    # model_name = "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF"
    # model_file = "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

    ## Use the following model_name and model_file if you have 8gb ram or less
    model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
    model_file = "mistral-7b-openorca.Q4_K_M.gguf"
    model_path = hf_hub_download(model_name, filename=model_file)
    
    ## Use the following model_name and model_file if you have 16gb ram or less
    # model_name = "TTheBloke/vicuna-13B-v1.5-16K-GGUF"
    # model_file = "vicuna-13b-v1.5-16k.Q4_K_M.gguf"

    return model_path

def instantiate_llm(path):
    # Load the LlamaCpp language model, adjust GPU usage based on your hardware
    n = startup_functions.llm_gpu_layers()
    llm = LlamaCpp(
        model_path=path,
        n_gpu_layers=n,
        n_batch=512,  # Batch size for model processing
        verbose=False,  # Disable detailed logging for debugging
    )
    return llm

def create_llm_chain(llm):
    # Define the prompt template with a placeholder for the question
    template = """
    You are AIden, a co-pilot and digital companion. You are witty, gentlemanly, and inquisitive with an engineering-oriented mindset. Please reflect these qualities in your response.

    Question: {question}

    Answer:
    """
    prompt = PromptTemplate(template=template, input_variables=["question"])

    # Create an LLMChain to manage interactions with the prompt and model
    llm_chain = LLMChain(prompt=prompt, llm=llm)
    return llm_chain

def ask_question(question):
    model_path = load_llm()
    llm = instantiate_llm(model_path)
    llm_chain = create_llm_chain(llm)
    answer = llm_chain.run(question)
    return answer

def main():
    model_path = load_llm()
    llm = instantiate_llm(model_path)
    llm_chain = create_llm_chain(llm)

    print("Chatbot initialized, ready to chat...")
    while True:
        question = input("> ")
        answer = llm_chain.run(question)
        print(answer, '\n')

if __name__ == "__main__":
    main()