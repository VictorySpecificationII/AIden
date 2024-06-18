import startup_functions
import mistral_onboard_llm
import llama2_onboard_llm

startup_functions.print_banner()

if __name__ == "__main__":
    llama2_onboard_llm.main()
    #mistral_onboard_llm.main()
    pass