# src/copilot.py

from dotenv import load_dotenv
import os
import requests
import boot_process

def boot():
    """
    Function to initiate boot process, check internet connectivity, load secrets,
    and display ASCII art.
    """

    ascii_art = """
        _    ___    _            
       / \  |_ _|__| | ___ _ __  
      / _ \  | |/ _` |/ _ \ '_ \ 
     / ___ \ | | (_| |  __/ | | |
    /_/   \_\___\__,_|\___|_| |_|
	
   Artificial Intelligence Co-Pilot

    """
    print(ascii_art)
    print("Boot: Process Initiating")

    boot_process.load_secrets()

if __name__ == "__main__":
	
	boot()


