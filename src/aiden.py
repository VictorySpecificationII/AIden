import requests

from fastapi import FastAPI, Response

app = FastAPI()

@app.get('/')
def home():
    return {"Chat" : "Bot"}

@app.get('/ask')
def ask(prompt :str):
    res = requests.post('http://localhost:11434/api/generate', json={
        "prompt": prompt,
        "stream" : False,
        "model" : "smollm:135m"
    })

    return Response(content=res.text, media_type="application/json")