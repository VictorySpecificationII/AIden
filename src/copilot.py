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

    boot_process.load_secrets()
    boot_process.check_internet_connection()

    print("Boot: Process Complete. System Operational.")
if __name__ == "__main__":
	
	boot()


