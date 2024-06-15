# Threaded version of the mic check, to integrate at some point

import pyaudio
import numpy as np
import threading
import time

def check_microphones():
    try:
        # Create an instance of PyAudio
        p = pyaudio.PyAudio()
        
        # Get the number of audio I/O devices
        devices = p.get_device_count()
        
        # List to hold all microphone devices
        active_microphones = []
        
        # Iterate through all devices
        for i in range(devices):
            # Get the device info
            device_info = p.get_device_info_by_index(i)
            # Check if this device is a microphone (an input device)
            if device_info.get('maxInputChannels') > 0:
                # Test microphone by recording a short sample
                if test_microphone(p, device_info):
                    active_microphones.append(device_info)
        
        # Clean up PyAudio instance
        p.terminate()
        
        return active_microphones
    
    except OSError as e:
        print(f"OS error in check_microphones: {e}")
        return []

def test_microphone(p, device_info):
    try:
        # Set parameters for testing
        format = pyaudio.paInt16
        channels = 1
        rate = 44100  # Reduced sampling rate to 16 kHz
        chunk = 4096  # Increased chunk size
        record_seconds = 0.25
        
        # Open stream for microphone input
        stream = p.open(format=format,
                        channels=channels,
                        rate=rate,
                        input=True,
                        frames_per_buffer=chunk,
                        input_device_index=device_info.get('index'))
        
        frames = []
        
        # Record audio for specified seconds
        for _ in range(int(rate / chunk * record_seconds)):
            try:
                data = stream.read(chunk)
                frames.append(data)
            except IOError as ex:
                if ex.args[1] != pyaudio.paInputOverflowed:
                    raise
        
        # Stop and close the stream
        stream.stop_stream()
        stream.close()
        
        # Convert frames to numpy array
        audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        
        # Check if there is any significant audio signal
        if np.max(np.abs(audio_data)) > 500:  # Adjust threshold as needed
            return True
        
        return False
    
    except OSError as e:
        print(f"OS error in test_microphone: {e}")
        return False

def microphone_daemon():
    while True:
        active_microphones = check_microphones()
        
        if active_microphones:
            print("Active microphones detected:", [mic.get('name') for mic in active_microphones])
            # Enable voice commands or perform other actions based on active microphones
        
        else:
            print("No active microphones detected. Disabling voice commands.")
            # Disable voice commands or handle absence of microphones
        
        # Sleep for some time before checking again (e.g., every 30 seconds)
        time.sleep(30)

# Start the microphone daemon in a separate thread
daemon_thread = threading.Thread(target=microphone_daemon)
daemon_thread.daemon = True  # Daemonize the thread so it exits when the main program ends
daemon_thread.start()

try:
    # Optionally, you can join the thread to the main program to keep it running until the main program exits
    while daemon_thread.is_alive():
        daemon_thread.join(1)  # Wait for 1 second before checking if the thread is still alive

except KeyboardInterrupt:
    print("Exiting...")
    # Handle any cleanup or exit tasks here

print("Main program exiting.")