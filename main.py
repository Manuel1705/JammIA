import sounddevice as sd
import numpy as np
import subprocess
from transformers import pipeline
from gtts import gTTS

SR = 16000
transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3")

def parla(testo):
    tts = gTTS(text=testo, lang="it")
    tts.save("risposta.mp3")
    subprocess.run(["afplay", "risposta.mp3"])   # macOS

# 1) Registra dal microfono
input("Premi Invio e parla...")
print("In ascolto... premi Invio per fermare.")
frames = []
with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                    callback=lambda indata, *_: frames.append(indata.copy())):
    input()
audio = np.concatenate(frames).flatten()

# 2) Trascrivi
domanda = transcriber(audio, generate_kwargs={"language": "italian"})["text"]
print("Tu:", domanda)

# 3) Genera la risposta (qui andrà NLU + Neo4j; per ora un placeholder)
risposta = f"Hai detto: {domanda}"
print("Bot:", risposta)

# 4) Sintesi vocale della risposta
parla(risposta)