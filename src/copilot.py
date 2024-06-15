# src/copilot.py

# from dotenv import load_dotenv
# import os
# import requests
import boot_process
import misc_utils

def boot():
    """
    Function to initiate boot process, check internet connectivity, load secrets,
    and display ASCII art.
    """
    misc_utils.print_banner()
    
    print("Boot: Process Initiating")

    secrets_loaded = boot_process.load_secrets()
    internet_connected = boot_process.check_internet_connection()

    print(secrets_loaded)
    print(internet_connected)
    # if secrets_loaded and internet_connected:
    #     print("Boot: Process Complete. System Operational.")
    #     return True
    # else:
    #     print("Boot: Process Failed. System not fully operational.")
    #     return False

    #Check if there's a local LLM model it can use if it's offline. If not, then exit. Otherwise, start using the offline model.

if __name__ == "__main__":
	
	boot()


