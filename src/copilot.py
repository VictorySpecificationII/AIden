import misc_utils
from dotenv import load_dotenv
import os
import openai
from langchain_openai import OpenAI
from langchain.schema.messages import HumanMessage, SystemMessage, FunctionMessage, ChatMessage, AIMessage
import loaders

misc_utils.print_banner()

# Startup things
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

# Check if the key is present
if openai_api_key is None:
    raise ValueError("OpenAI API key not found in the environment file.")

# Set up OpenAI API key
openai.api_key = openai_api_key

llm = OpenAI()

def queryLLM(llm, query):

    def get_response_chunks(query):
        response_chunks = []
        for chunk in llm.stream(query):
            response_chunks.append(chunk)
        return response_chunks

    def print_response_chunks(chunks):
        for chunk in chunks:
            print(chunk, end="", flush=True)
        print("\n")
    
    chunks = get_response_chunks(query)
    print_response_chunks(chunks)

if __name__ == "__main__":

    query = "Please give me a 4 line lorem ipsum so i can test something."

    queryLLM(llm, query)

