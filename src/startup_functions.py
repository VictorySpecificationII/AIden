from dotenv import load_dotenv
import os
import openai
import mistral_onboard_llm

def print_banner():
    ascii_art = """
        _    ___    _            
       / \  |_ _|__| | ___ _ __  
      / _ \  | |/ _` |/ _ \ '_ \ 
     / ___ \ | | (_| |  __/ | | |
    /_/   \_\___\__,_|\___|_| |_|
    
   Artificial Intelligence Co-Pilot

    """
    print(ascii_art)

def init_llm():
    model_path = mistral_onboard_llm.load_llm()
    llm = mistral_onboard_llm.instantiate_llm(model_path)
    return llm