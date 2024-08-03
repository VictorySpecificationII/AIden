"""
This module contains the logic for interacting with the Mistral model using LangChain and HuggingFace's hub.

Functions:
- load_llm(): Downloads and returns the path to the LLM model.
- instantiate_llm(path): Instantiates the LLM with the specified model path.
- create_llm_chain(llm): Creates an LLMChain instance with a prompt template and the provided LLM.
- ask_question(question): Passes a question to the LLM and returns the generated answer.
- main(): Command-line interface for interacting with the chatbot.
"""

from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download


def load_llm():
    """
    Load and return the path to the LLM model.
    """
    ## Define model name and file name
    # llm_model_name = "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF"
    # model_file = "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
    ## Use the following llm_model_name and model_file if you have 8gb ram or less
    llm_model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
    model_file = "mistral-7b-openorca.Q4_K_M.gguf"
    model_path = hf_hub_download(llm_model_name, filename=model_file)
    ## Use the following llm_model_name and model_file if you have 16gb ram or less
    # llm_model_name = "TTheBloke/vicuna-13B-v1.5-16K-GGUF"
    # model_file = "vicuna-13b-v1.5-16k.Q4_K_M.gguf"

    return model_path

def instantiate_llm(path):
    """
    Instantiate the LLM with specified parameters.
    
    Args:
        path (str): Path to the LLM model.
    
    Returns:
        LlamaCpp: An instance of the LlamaCpp model.
    """
    # Load the LlamaCpp language model, adjust GPU usage based on your hardware
    llm = LlamaCpp(
        model_path=path,
        n_gpu_layers=0,
        n_batch=512,  # Batch size for model processing
        verbose=False,  # Disable detailed logging for debugging
    )
    return llm

def create_llm_chain(llm):
    """
    Create an LLMChain using a prompt template and the provided LLM.
    
    Args:
        llm (LlamaCpp): The LlamaCpp instance to use.
    
    Returns:
        LLMChain: An instance of LLMChain.
    """
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
    """
    Pass a question to the LLM and get the answer.
    
    Args:
        question (str): The question to ask the LLM.
    
    Returns:
        str: The answer from the LLM.
    """
    model_path = load_llm()
    llm = instantiate_llm(model_path)
    llm_chain = create_llm_chain(llm)
    answer = llm_chain.run(question)
    return answer

def main():
    """
    Main function to interact with the chatbot via the command line.
    """
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
