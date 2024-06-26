import startup_functions
import mistral_onboard_llm
import llama2_onboard_llm

def print_divider():
    print("=" * 190)

def interactive_chat():
    current_personality = "Llama"
    while True:
        user_input = input("> ")
        if user_input.lower() == "change personality constructs":
            if current_personality == "Llama":
                current_personality = "Mistral"
                print("Personality changed to Mistral")
            elif current_personality == "Mistral":
                current_personality = "Llama"
                print("Personality changed to Llama")
        else:
            if current_personality == "Mistral":
                response = mistral_onboard_llm.ask_question(user_input)
            elif current_personality == "Llama":
                response = llama2_onboard_llm.ask_question(user_input)
            print(response)

if __name__ == "__main__":
    startup_functions.print_banner()
    startup_functions.check_local_llm_availability()
    startup_functions.check_local_gpu_availability()
    startup_functions.check_local_internet_connection()
    print_divider()
    interactive_chat()