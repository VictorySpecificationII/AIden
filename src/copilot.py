import startup_functions
import openai
from langchain_openai import OpenAI
from langchain.schema.messages import HumanMessage, SystemMessage, FunctionMessage, ChatMessage, AIMessage
import document_loaders
import llm_functions

startup_functions.print_banner()

startup_functions.load_environment_variables()

llm = OpenAI()

if __name__ == "__main__":

    query = "Please give me a 4 line lorem ipsum so i can test something."

    llm_functions.queryLLM(llm, query)

