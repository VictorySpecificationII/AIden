import misc_utils
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import os
import openai
from langchain_community.chat_models import ChatOpenAI
from langchain.llms import OpenAI
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
    response = llm.invoke("List the seven wonders of the world.")
    print(response)
    