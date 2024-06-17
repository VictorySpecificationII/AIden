import startup_functions
import llm_functions

startup_functions.print_banner()
startup_functions.load_environment_variables()

if __name__ == "__main__":

    # query = "Please give me a 4 line lorem ipsum so i can test something."

    # print(llm_functions.queryLLM_openAI(query))

    while True:
        # Get user input
        query = input("Enter your prompt (or type 'exit' to quit): ")

        # Exit condition
        if query.lower() == 'exit':
            print("Exiting the program. Goodbye!")
            break

        # Query the LLM
        response = llm_functions.queryLLM_openAI(query)

        # Print the response
        print(f"Model Response: {response}\n")