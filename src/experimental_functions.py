# # Threaded version of the mic check, to integrate at some point

# import pyaudio
# import numpy as np
# import threading
# import time

# def check_microphones():
#     try:
#         # Create an instance of PyAudio
#         p = pyaudio.PyAudio()
        
#         # Get the number of audio I/O devices
#         devices = p.get_device_count()
        
#         # List to hold all microphone devices
#         active_microphones = []
        
#         # Iterate through all devices
#         for i in range(devices):
#             # Get the device info
#             device_info = p.get_device_info_by_index(i)
#             # Check if this device is a microphone (an input device)
#             if device_info.get('maxInputChannels') > 0:
#                 # Test microphone by recording a short sample
#                 if test_microphone(p, device_info):
#                     active_microphones.append(device_info)
        
#         # Clean up PyAudio instance
#         p.terminate()
        
#         return active_microphones
    
#     except OSError as e:
#         print(f"OS error in check_microphones: {e}")
#         return []

# def test_microphone(p, device_info):
#     try:
#         # Set parameters for testing
#         format = pyaudio.paInt16
#         channels = 1
#         rate = 44100  # Reduced sampling rate to 16 kHz
#         chunk = 4096  # Increased chunk size
#         record_seconds = 0.25
        
#         # Open stream for microphone input
#         stream = p.open(format=format,
#                         channels=channels,
#                         rate=rate,
#                         input=True,
#                         frames_per_buffer=chunk,
#                         input_device_index=device_info.get('index'))
        
#         frames = []
        
#         # Record audio for specified seconds
#         for _ in range(int(rate / chunk * record_seconds)):
#             try:
#                 data = stream.read(chunk)
#                 frames.append(data)
#             except IOError as ex:
#                 if ex.args[1] != pyaudio.paInputOverflowed:
#                     raise
        
#         # Stop and close the stream
#         stream.stop_stream()
#         stream.close()
        
#         # Convert frames to numpy array
#         audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        
#         # Check if there is any significant audio signal
#         if np.max(np.abs(audio_data)) > 500:  # Adjust threshold as needed
#             return True
        
#         return False
    
#     except OSError as e:
#         print(f"OS error in test_microphone: {e}")
#         return False

# def microphone_daemon():
#     while True:
#         active_microphones = check_microphones()
        
#         if active_microphones:
#             print("Active microphones detected:", [mic.get('name') for mic in active_microphones])
#             # Enable voice commands or perform other actions based on active microphones
        
#         else:
#             print("No active microphones detected. Disabling voice commands.")
#             # Disable voice commands or handle absence of microphones
        
#         # Sleep for some time before checking again (e.g., every 30 seconds)
#         time.sleep(30)

# # Start the microphone daemon in a separate thread
# daemon_thread = threading.Thread(target=microphone_daemon)
# daemon_thread.daemon = True  # Daemonize the thread so it exits when the main program ends
# daemon_thread.start()

# try:
#     # Optionally, you can join the thread to the main program to keep it running until the main program exits
#     while daemon_thread.is_alive():
#         daemon_thread.join(1)  # Wait for 1 second before checking if the thread is still alive

# except KeyboardInterrupt:
#     print("Exiting...")
#     # Handle any cleanup or exit tasks here

# print("Main program exiting.")



# ## old boot_process.py

# import os
# from dotenv import load_dotenv
# import requests
# from requests.exceptions import ConnectionError, Timeout
# import pyaudio
# import numpy as np
# import subprocess
# import cv2

# def load_secrets():
#     try:
#         # Load environment variables from .env file
#         load_dotenv()

#         # Access environment variables
#         api_key = os.getenv("OPENAI_API_KEY")

#         if api_key is None:
#             raise ValueError("OPENAI_API_KEY not found in environment variables. Ensure it's set in your .env file.")

#         print("Boot: Secrets loaded.")
#         return 1

#     except Exception as e:
#         print(f"Boot Error: {str(e)}")
#         return 0


# def check_internet_connection():
#     url = "https://8.8.8.8"  # Google's public DNS server IP
#     timeout = 5  # Timeout in seconds

#     try:
#         response = requests.get(url, timeout=timeout)
#         response.raise_for_status()  # Raise exception for non-200 status codes

#         print("Boot: Internet connection detected.")
#         return 1

#     except ConnectionError as e:
#         print(f"Boot Error: {str(e)}. No internet connection detected.")
#         return 0

#     except Timeout as e:
#         print(f"Boot Error: {str(e)}. Request timed out.")
#         return -1

# def check_mic_connection():
#     # Create an instance of PyAudio
#     p = pyaudio.PyAudio()
    
#     # Get the number of audio I/O devices
#     devices = p.get_device_count()
    
#     # Print the total number of devices
#     print(f'Total number of devices: {devices}')
    
#     # List to hold all microphone devices
#     microphones = []
    
#     # Iterate through all devices
#     for i in range(devices):
#         # Get the device info
#         device_info = p.get_device_info_by_index(i)
#         # Check if this device is a microphone (an input device)
#         if device_info.get('maxInputChannels') > 0:
#             microphones.append(device_info)
#             print(f"Microphone: {device_info.get('name')} , Device Index: {device_info.get('index')}")
    
#     if not microphones:
#         print("No microphones found.")
#         return None
    
#     # Test each microphone by recording a 2-second sample
#     for mic in microphones:
#         print(f"Testing microphone: {mic.get('name')} (Index: {mic.get('index')})")
        
#         # Set parameters for recording
#         # NOTE: If you get overflow errors, adjust these settings. The current settings seem to work. 
#         format = pyaudio.paInt16
#         channels = 1
#         rate = 44100
#         chunk = 4096
#         record_seconds = 0.25
        
#         # Open stream for microphone input
#         stream = p.open(format=format,
#                         channels=channels,
#                         rate=rate,
#                         input=True,
#                         frames_per_buffer=chunk,
#                         input_device_index=mic.get('index'))
        
#         frames = []
        
#         # Record audio for specified seconds
#         for _ in range(int(rate / chunk * record_seconds)):
#             data = stream.read(chunk)
#             frames.append(data)
        
#         # Stop and close the stream
#         stream.stop_stream()
#         stream.close()
        
#         # Convert frames to numpy array
#         audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        
#         # Check if there is any significant audio signal
#         if np.max(np.abs(audio_data)) > 500:  # Adjust threshold as needed
#             print(f"Detected sound on microphone: {mic.get('name')} (Index: {mic.get('index')})")
#             #return mic.get('index'), mic.get('name')
#             return 1
#         else:
#             print(f"No sound detected on microphone: {mic.get('name')} (Index: {mic.get('index')})")
    
#     # If no microphone detected sound, return 0
#     print("No microphone detected sound.")
#     return 0

# def check_camera_connection():
#     try:
#         # Open the webcam
#         cap = cv2.VideoCapture(0)  # Use 0 for default webcam

#         if not cap.isOpened():
#             print("Vision Error: Could not open webcam.")
#             return 0

#         # Read a frame from the webcam
#         ret, frame = cap.read()

#         # Check if the frame is read correctly
#         if ret:
#             # Display the captured image
#             # cv2.imshow('Captured Image', frame)
#             # cv2.waitKey(0)  # Wait indefinitely until a key is pressed
#             # cv2.destroyAllWindows()  # Close the image window
#             tmp_image_path = os.path.join('/tmp', 'captured_image_boot_process.jpg')
#             cv2.imwrite(tmp_image_path, frame)
#             print(f"Test Image saved to {tmp_image_path}")
#             print("Detected vision on camera: Camera is available and can capture images.")
#             print(f"Vision: Camera Resolution: {frame.shape[1]}x{frame.shape[0]}")
#             return 1

#         else:
#             print("Vision Error: Failed to capture image from webcam.")
#             return -1

#     except Exception as e:
#         print(f"Error: {str(e)}")
#         return -2

#     finally:
#         # Release the webcam
#         if cap.isOpened():
#             cap.release()

# def check_sensory_connection():
#     # That's a complicated bit, work on it once you have sensors
#     pass



# ## old copilot.py

# # src/copilot.py

# # from dotenv import load_dotenv
# # import os
# # import requests
# import boot_process
# import misc_utils

# def boot():
#     """
#     Function to initiate boot process, check internet connectivity, load secrets,
#     and display ASCII art.
#     """
#     misc_utils.print_banner()
    
#     print("Boot: Process Initiating")

#     secrets_loaded = boot_process.load_secrets()
#     internet_connected = boot_process.check_internet_connection()
#     mic_check = boot_process.check_mic_connection()
#     cam_check = boot_process.check_camera_connection()

#     if secrets_loaded and internet_connected and (mic_check or cam_check):
#         print("Boot: Process Complete. System Operational.")
#         return [1,1,1,1]
#     else:
#         print("Boot: Process Failed. System partially operational.")
#         return [secrets_loaded, internet_connected, mic_check, cam_check] 

#     #Check if there's a local LLM model it can use if it's offline. If not, then exit. Otherwise, start using the offline model.

# if __name__ == "__main__":
	
# 	print(boot())


