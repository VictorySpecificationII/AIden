# src/copilot.py

from dotenv import load_dotenv
import os
import requests

def boot_process():
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

    try:
        # Load environment variables from .env file
        load_dotenv()

        # Access environment variables
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key is None:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Ensure it's set in your .env file.")

        print("Boot: Secrets loaded.")

        # Check internet connection
        url = "https://8.8.8.8"  # Google's public DNS server IP
        timeout = 5  # Timeout in seconds

        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Raise exception for non-200 status codes

            print("Boot: Internet connection detected.")
            print("Boot: Process Complete. System Operational.")

        except (requests.ConnectionError, requests.Timeout) as e:
            raise ValueError(f"{str(e)}. No internet connection detected.")

    except Exception as e:
        print(f"Boot Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
	
	boot_process()

