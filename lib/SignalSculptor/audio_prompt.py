import speech_recognition as sr

# Define trigger phrases
trigger_phrases = ["Aiden", "Hey Aiden", "Hi Aiden"]

def monitor_audio_input(prompt):
    """
    Monitor input prompt for trigger phrases.

    Args:
        prompt (str): The input prompt to monitor.

    Returns:
        bool: True if a trigger phrase is detected, False otherwise.
    """
    # Convert prompt to lowercase for case-insensitive matching
    prompt_lower = prompt.lower()

    # Check for trigger phrases
    for trigger_phrase in trigger_phrases:
        if trigger_phrase in prompt_lower:
            return True

    # No trigger phrase detected
    return False


def get_audio_prompt():
    """
    Capture an audio prompt from the user via the microphone.

    Returns:
        str: The transcribed audio prompt, or None if no valid prompt is captured.
    """
    # Create a recognizer instance
    recognizer = sr.Recognizer()

    # Use the default microphone as the audio source
    with sr.Microphone() as source:
        print("Listening for trigger phrase...")

        # Adjust for ambient noise before capturing the audio
        recognizer.adjust_for_ambient_noise(source)

        # Capture audio input from the user
        audio_data = recognizer.listen(source)

    try:
        # Use CMU Sphinx to transcribe the audio
        transcribed_prompt = recognizer.recognize_sphinx(audio_data)

        # Check if the transcribed prompt contains a trigger phrase
        if monitor_audio_input(transcribed_prompt):
            print("Trigger phrase detected:", transcribed_prompt)
            return transcribed_prompt
        else:
            print("No trigger phrase detected. Listening for trigger phrase again...")
            return None

    except sr.UnknownValueError:
        print("Sphinx could not understand audio")
        return None
    except sr.RequestError as e:
        print("Sphinx error: {0}".format(e))
        return None

def process_audio_prompt(prompt):
    """
    Process an audio prompt.

    Args:
        prompt (str): The audio prompt transcribed from speech.

    Returns:
        str: The processed prompt.
    """
    # Placeholder function for processing logic
    processed_prompt = "Processed: " + prompt
    return processed_prompt