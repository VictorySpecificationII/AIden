from threading import Thread
from lib.SignalSculptor.audio_prompt import monitor_audio_input, get_audio_prompt, process_audio_prompt
from lib.SignalSculptor.text_prompt import get_text_prompt, process_text_prompt

def process_audio():
    while True:
        trigger_phrase = get_audio_prompt()
        if trigger_phrase is not None and monitor_audio_input(trigger_phrase) is True:
            prompt = get_audio_prompt()
            process_audio_prompt(prompt)

def process_text():
    while True:
        prompt = get_text_prompt()
        process_text_prompt(prompt)

def main():
    audio_thread = Thread(target=process_audio)
    text_thread = Thread(target=process_text)

    audio_thread.start()
    text_thread.start()

    audio_thread.join()
    text_thread.join()

if __name__ == "__main__":
    main()
