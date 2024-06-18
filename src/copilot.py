import startup_functions
import mistral_onboard_llm

startup_functions.print_banner()

if __name__ == "__main__":
    model_path = mistral_onboard_llm.load_llm()
    llm = mistral_onboard_llm.instantiate_llm(model_path)
    result = mistral_onboard_llm.run_inference("meaning of life", llm)
    print(result)