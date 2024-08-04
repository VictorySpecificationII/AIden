"""
This module contains startup utility functions for an AI Co-Pilot application.

Functions:
- print_banner(): Prints a welcome banner at startup.
- check_local_llm_availability(): Checks if the necessary LLM models are available locally, downloads them if not.
- check_local_internet_connection(): Checks for an active internet connection.
"""

import os
import requests
import mistral_onboard_llm
import llama2_onboard_llm

def print_banner():
    '''
    Prints a banner at startup.
    '''
    ascii_art = """
        _    ___    _            
       / \  |_ _|__| | ___ _ __  
      / _ \  | |/ _` |/ _ \ '_ \ 
     / ___ \ | | (_| |  __/ | | |
    /_/   \_\___\__,_|\___|_| |_|
    
   Artificial Intelligence Co-Pilot

    """
    print(ascii_art)

def check_local_llm_availability():
    '''
    Checks whether the LLM models are available locally, and if not - downloads them.
    '''
    print("Startup Check: Checking LLM models in ~/.cache/huggingface/hub...")
    # Get the paths to the model files
    mistral_path = mistral_onboard_llm.load_llm()
    llama2_path = llama2_onboard_llm.load_llm()

    # Check if the model files exist
    if not os.path.isfile(mistral_path):
        print(f"Error: Mistral model file not found at {mistral_path}.")
        mistral_found = False
    else:
        print(f"Success: Mistral model file found at {mistral_path}.")
        mistral_found = True

    if not os.path.isfile(llama2_path):
        print(f"Error: Llama2 model file not found at {llama2_path}.")
        llama2_found = False
    else:
        print(f"Success: Llama2 model file found at {llama2_path}.")
        llama2_found = True
    if (llama2_found or mistral_found):
        return True
    else:
        print(f"LLM's not found in ~/.chache/huggingface/hub directory.")
        return False

def check_local_internet_connection():
    '''
    Checks for internet connectivity.
    '''
    print("Startup Check: Checking Internet connectivity on host...")
    try:
        requests.get("https://www.google.com", timeout=5)
        print(f"Success: Internet connectivity enabled.")
        return True
    except requests.ConnectionError:
        print("Error: No internet connection.")
        return False
