import startup_functions
import mistral_onboard_llm
import llama2_onboard_llm



if __name__ == "__main__":
    startup_functions.print_banner()
    startup_functions.check_local_llm_availability()
    
    print(mistral_onboard_llm.ask_question("Are you Mistral?"))
    print(llama2_onboard_llm.ask_question("Are you Llama2?"))