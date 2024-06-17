import startup_functions
import llm_functions

startup_functions.print_banner()
startup_functions.load_environment_variables()

if __name__ == "__main__":

    query = "Please give me a 4 line lorem ipsum so i can test something."

    print(llm_functions.queryLLM_openAI(query))

