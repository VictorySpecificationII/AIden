from lib.SignalSculptor.audio_prompt import monitor_audio_input, get_audio_prompt, process_audio_prompt
from lib.SignalSculptor.text_prompt import get_text_prompt, process_text_prompt

def main():
    while True:
        trigger_phrase = get_audio_prompt()
        if trigger_phrase is not None:
            if monitor_audio_input(trigger_phrase) is True:
                prompt = get_audio_prompt()
                process_audio_prompt(prompt)

if __name__ == "__main__":
    main()