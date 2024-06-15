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
    mic_check = boot_process.check_mic_connection()
    cam_check = boot_process.check_camera_connection()

    if secrets_loaded and internet_connected and (mic_check or cam_check):
        print("Boot: Process Complete. System Operational.")
        return True
    else:
        print("Boot: Process Failed. System partially operational.")
        return False

    #Check if there's a local LLM model it can use if it's offline. If not, then exit. Otherwise, start using the offline model.

if __name__ == "__main__":
	
	boot()


