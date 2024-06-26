import pyaudio
import numpy as np
import speech_recognition as sr

def record_audio(duration=5, rate=44100, chunk=1024):
    p = pyaudio.PyAudio()

    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    frames_per_buffer=chunk)

    print("* recording")

    frames = []

    for i in range(0, int(rate / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)

    print("* done recording")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Convert frames to numpy array
    audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)

    return audio_data

def audio_to_text(audio_data, rate):
    r = sr.Recognizer()
    audio = sr.AudioData(audio_data.tobytes(), rate, 2)  # 2 bytes per sample
    try:
        text = r.recognize_google(audio)
        return text
    except sr.UnknownValueError:
        return "Speech Recognition could not understand audio"
    except sr.RequestError as e:
        return "Could not request results from Speech Recognition service; {0}".format(e)

# Record audio for 5 seconds
audio_data = record_audio(duration=5)

# Convert audio to text
text = audio_to_text(audio_data, rate=44100)
print(text)

def main():
    record_audio()

if __name__ == "__main__":
    main()
