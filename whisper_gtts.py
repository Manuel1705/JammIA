import select
import sounddevice as sd
import numpy as np
import subprocess
import sys
import uuid
import torch
from transformers import pipeline
from gtts import gTTS
from rag import chain, llm_cypher
from DialogManager import DialogManager

SR = 16000
# Whisper su MPS (GPU Apple) se disponibile, altrimenti CPU
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
transcriber = pipeline("automatic-speech-recognition",
                       model="openai/whisper-large-v3", device=DEVICE)


def parla(testo, velocita=1.3):
    """Riproduce la risposta. Se l'utente preme Invio mentre l'audio è in corso,
    interrompe subito la riproduzione. Ritorna True se è stata interrotta (segnale
    per il loop principale di passare direttamente all'ascolto, senza richiedere
    un altro Invio per aprire il turno)."""
    tts = gTTS(text=testo, lang="it")
    tts.save("risposta.mp3")
    processo = subprocess.Popen(["afplay", "-r", str(velocita), "risposta.mp3"])  # macOS

    print("(Premi Invio per interrompere e parlare subito)")
    while processo.poll() is None:
        pronto, _, _ = select.select([sys.stdin], [], [], 0.05)
        if pronto:
            sys.stdin.readline()  # consuma l'Invio, così non resta in coda per il prossimo prompt
            processo.terminate()
            processo.wait()
            return True

    return False


def registra():
    """Registra dal microfono finché l'utente non preme di nuovo Invio."""
    print("In ascolto... premi Invio per fermare.")
    frames = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        callback=lambda indata, *_: frames.append(indata.copy())):
        input()
    return np.concatenate(frames).flatten()


dialog_manager = DialogManager(chain, llm_cypher)
# un thread_id nuovo ad ogni avvio dello script, così ogni sessione parte con una
# cronologia pulita invece di riprendere (e accumulare all'infinito) quella di sessioni precedenti
THREAD_ID = str(uuid.uuid4())

print("\nConversazione avviata. Premi Invio per parlare, scrivi 'esci' per terminare.")
salta_prompt = False
while True:
    if not salta_prompt:
        comando = input("\nPremi Invio e parla (o 'esci' per uscire)... ")
        if comando.strip().lower() in ("esci", "exit", "quit"):
            print("A presto!")
            dialog_manager.close()
            break
    salta_prompt = False

    # 1) Registra e trascrivi
    audio = registra()
    print("transcribing...")
    domanda = transcriber(audio, generate_kwargs={"language": "italian"})["text"]
    print("Tu:", domanda)

    # 2) Genera la risposta tramite il dialog state tracker; se manca un'informazione
    #    (es. a quale opera ci si riferisce), il grafo chiede chiarimento a voce e resta
    #    in attesa di una nuova risposta parlata, finché non ha abbastanza contesto
    esito = dialog_manager.invoke(domanda, thread_id=THREAD_ID)
    while esito["tipo"] == "chiarimento":
        print("Bot (chiarimento):", esito["testo"])
        parla(esito["testo"])

        audio_chiarimento = registra()
        print("transcribing...")
        risposta_utente = transcriber(audio_chiarimento, generate_kwargs={"language": "italian"})["text"]
        print("Tu:", risposta_utente)

        esito = dialog_manager.rispondi_chiarimento(risposta_utente, thread_id=THREAD_ID)

    risposta = esito["testo"]
    print("Bot:", risposta)

    # 3) Sintesi vocale della risposta; se l'utente la interrompe premendo Invio,
    #    si passa subito alla registrazione del turno successivo
    salta_prompt = parla(risposta)
