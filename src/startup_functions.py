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