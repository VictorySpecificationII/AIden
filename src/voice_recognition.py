import speech_recognition as sr

def speech_to_text():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print('Say Something:')
        audio = r.listen(source)
        print ('Done')
    text = r.recognize_sphinx(audio, language = 'en-GB')
    print(text)
    print(r.recognize_sphinx(audio))
    return text

def main():
    speech_to_text()

if __name__ == "__main__":
    main()