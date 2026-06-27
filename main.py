import sounddevice as sd
import numpy as np
import subprocess
import torch
from transformers import pipeline
from mlx_lm import load, generate
from gtts import gTTS
from sparql_query import costruisci_contesto

SR = 16000
# Whisper su MPS (GPU Apple) se disponibile, altrimenti CPU
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
transcriber = pipeline("automatic-speech-recognition",
                       model="openai/whisper-large-v3", device=DEVICE)

# Modello di generazione su MLX (Apple Silicon)
MODEL_NAME = "mlx-community/Meta-Llama-3.1-8B-Instruct-8bit"
MODEL, TOKENIZER = load(MODEL_NAME)

# Contesto RAG dalle query SPARQL su DBpedia (caricato una volta all'avvio)
print("Carico il contesto da DBpedia...")
CONTESTO = costruisci_contesto()
print(CONTESTO)


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


# La cronologia parte con il solo system prompt e si accumula a ogni turno
system_prompt = (
    "Sei un assistente esperto dei dipinti di Caravaggio e Battistello Caracciolo. "
    "Rispondi in italiano in modo conciso e accurato, basandoti solo sul CONTESTO "
    "qui sotto. Se l'informazione non è nel contesto, dillo onestamente. "
    "Ogni opera ha un'etichetta tra parentesi quadre: [A NAPOLI] se si trova a Napoli, "
    "[NON a Napoli] altrimenti. Quando ti chiedono dove si trova un'opera o se è a Napoli, "
    "usa quell'etichetta per rispondere.\n\n"
    f"CONTESTO:\n{CONTESTO}"
)
messages = [{"role": "system", "content": system_prompt}]

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
    messages.append({"role": "user", "content": domanda})
    prompt = TOKENIZER.apply_chat_template(messages, add_generation_prompt=True)
    risposta = generate(MODEL, TOKENIZER, prompt=prompt, max_tokens=1000, verbose=False)
    print("Bot:", risposta)

    # 3) Memorizza la risposta nella cronologia (così il modello la "ricorda")
    messages.append({"role": "assistant", "content": risposta})

    # 4) Sintesi vocale della risposta
    parla(risposta)
