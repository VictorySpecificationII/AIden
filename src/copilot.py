import misc_utils
from dotenv import load_dotenv
import os
import openai
from langchain_openai import OpenAI

misc_utils.print_banner()

# Startup things
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

# Check if the key is present
if openai_api_key is None:
    raise ValueError("OpenAI API key not found in the environment file.")

# Set up OpenAI API key
openai.api_key = openai_api_key


if __name__ == "__main__":
    llm = OpenAI()
    for chunk in llm.stream("Please give me a 4 line lorem ipsum so i can test something"):
        print(chunk, end="", flush=True)
    print("\n")