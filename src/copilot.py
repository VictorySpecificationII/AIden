import startup_functions
import mistral_onboard_llm
import llama2_onboard_llm

startup_functions.print_banner()

if __name__ == "__main__":
    print(mistral_onboard_llm.ask_question("Are you Mistral?"))
    print(llama2_onboard_llm.ask_question("Are you Llama2?"))