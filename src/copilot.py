import startup_functions
import mistral_onboard_llm

startup_functions.print_banner()
llm = startup_functions.init_llm()

if __name__ == "__main__":

    result = mistral_onboard_llm.run_inference("meaning of life", llm)
    print(result)