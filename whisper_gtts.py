import sounddevice as sd
import numpy as np
import subprocess
import torch
from transformers import pipeline
from gtts import gTTS
from rag import genera_risposta

SR = 16000
# Whisper su MPS (GPU Apple) se disponibile, altrimenti CPU
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
transcriber = pipeline("automatic-speech-recognition",
                       model="openai/whisper-large-v3", device='cpu')


def parla(testo):
    tts = gTTS(text=testo, lang="it")
    tts.save("risposta.mp3")
    subprocess.run(["afplay", "risposta.mp3"])  # macOS


def registra():
    """Registra dal microfono finché l'utente non preme di nuovo Invio."""
    print("In ascolto... premi Invio per fermare.")
    frames = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        callback=lambda indata, *_: frames.append(indata.copy())):
        input()
    return np.concatenate(frames).flatten()


print("\nConversazione avviata. Premi Invio per parlare, scrivi 'esci' per terminare.")
while True:
    comando = input("\nPremi Invio e parla (o 'esci' per uscire)... ")
    if comando.strip().lower() in ("esci", "exit", "quit"):
        print("A presto!")
        break

    # 1) Registra e trascrivi
    audio = registra()
    domanda = transcriber(audio, generate_kwargs={"language": "italian"})["text"]
    print("Tu:", domanda)

    # 2) Aggiungi la domanda alla cronologia e genera la risposta

    risposta = genera_risposta(domanda)
    print("Bot:", risposta)

    # 4) Sintesi vocale della risposta
    parla(risposta)
