import os
from dotenv import load_dotenv
import requests
from requests.exceptions import ConnectionError, Timeout

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

def check_mic_connection():
    pass

def check_camera_connection():
    pass

def check_sensory_connection():
    pass