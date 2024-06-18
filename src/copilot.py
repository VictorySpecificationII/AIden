import startup_functions
import mistral_onboard_llm

startup_functions.print_banner()
llm = startup_functions.init_llm()

def interactive_chat():
    print("Interactive Chat: Type 'exit' to end the chat.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            print("Exiting chat. Goodbye!")
            break
        response = mistral_onboard_llm.run_inference(user_input, llm)
        print(f"LLM: {response}")

if __name__ == "__main__":
    interactive_chat()