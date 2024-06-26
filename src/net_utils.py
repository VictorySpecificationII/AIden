import requests

def check_internet_connection():
    print("Startup Check: Checking Internet connectivity on host...")
    try:
        requests.get("https://www.google.com", timeout=5)
        print(f"Success: Internet connectivity enabled.")
        return True
    except requests.ConnectionError:
        print("Error: No internet connection.")
        return False