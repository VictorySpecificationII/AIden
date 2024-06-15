import os
from dotenv import load_dotenv
import requests
from requests.exceptions import ConnectionError, Timeout
import pyaudio

def load_secrets():
    try:
        # Load environment variables from .env file
        load_dotenv()

        # Access environment variables
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key is None:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Ensure it's set in your .env file.")

        print("Boot: Secrets loaded.")
        return True

    except Exception as e:
        print(f"Boot Error: {str(e)}")
        return False


def check_internet_connection():
    url = "https://8.8.8.8"  # Google's public DNS server IP
    timeout = 5  # Timeout in seconds

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()  # Raise exception for non-200 status codes

        print("Boot: Internet connection detected.")
        return 1

    except ConnectionError as e:
        print(f"Boot Error: {str(e)}. No internet connection detected.")
        return 0

    except Timeout as e:
        print(f"Boot Error: {str(e)}. Request timed out.")
        return -1

def find_and_select_microphone():
    # Create an instance of PyAudio
    p = pyaudio.PyAudio()
    
    # Get the number of audio I/O devices
    devices = p.get_device_count()
    
    # Print the total number of devices
    print(f'Total number of devices: {devices}')
    
    # List to hold all microphone devices
    microphones = []
    
    # Iterate through all devices
    for i in range(devices):
        # Get the device info
        device_info = p.get_device_info_by_index(i)
        # Check if this device is a microphone (an input device)
        if device_info.get('maxInputChannels') > 0:
            microphones.append(device_info)
            print(f"Microphone: {device_info.get('name')} , Device Index: {device_info.get('index')}")
    
    if not microphones:
        print("No microphones found.")
        return None
    
    # Select the first available microphone as the active one (or implement a better selection logic if needed)
    active_microphone = microphones[0]
    print(f"Selected Microphone: {active_microphone.get('name')} , Device Index: {active_microphone.get('index')}")
    
    # Return the selected microphone's index and name
    return active_microphone.get('index'), active_microphone.get('name')

def check_mic_connection():
    index, name = find_and_select_microphone()
    if index is not None:
        print(f"Using microphone: {name} (Index: {index})")




def check_camera_connection():
    pass

def check_sensory_connection():
    pass