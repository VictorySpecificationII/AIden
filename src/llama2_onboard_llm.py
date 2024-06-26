from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download
import llm_utils


def load_llm():
    model_name = "TheBloke/Llama-2-7B-Chat-GGUF"
    model_file = "llama-2-7b-chat.Q4_0.gguf"
    model_path = hf_hub_download(model_name, filename=model_file)
    return model_path

def instantiate_llm(path):
    # Load the LlamaCpp language model, adjust GPU usage based on your hardware
    n = llm_utils.llm_gpu_layers()
    llm = LlamaCpp(
        model_path=path,
        n_gpu_layers=n,
        n_batch=512,  # Batch size for model processing
        verbose=False,  # Enable detailed logging for debugging
    )
    return llm

def create_llm_chain(llm):
    # Define the prompt template with a placeholder for the question
    template = """
    You are AIden, a co-pilot and digital companion. You are witty, gentlemanly, and inquisitive with an social mindset. Please reflect these qualities in your response.
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