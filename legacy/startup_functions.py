from dotenv import load_dotenv
import os
import openai

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

def load_environment_variables():
    # Startup things
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY")

    # Check if the key is present
    if openai_api_key is None:
        raise ValueError("OpenAI API key not found in the environment file.")

    # Set up OpenAI API key
    openai.api_key = openai_api_key