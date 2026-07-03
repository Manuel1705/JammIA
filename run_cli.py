"""Entry point: chatbot vocale da terminale.

Uso:  uv run run_cli.py
Premi Invio per parlare, di nuovo Invio per fermare la registrazione. Durante la riproduzione della
risposta, premi Invio per interromperla e passare subito a parlare.
"""
import select
import subprocess
import sys
import uuid

import numpy as np
import sounddevice as sd

from chatbot import config
from chatbot.dialog.manager import DialogManager
from chatbot.rag.rag_chain import RagChain
from chatbot.speech.synthesizer import TextToSpeech
from chatbot.speech.transcriber import SpeechToText


def registra() -> np.ndarray:
    """Registra dal microfono finché l'utente non preme Invio."""
    print("In ascolto... premi Invio per fermare.")
    frames = []
    with sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                        callback=lambda indata, *_: frames.append(indata.copy())):
        input()
    return np.concatenate(frames).flatten()


def parla(tts: TextToSpeech, testo: str) -> bool:
    """Sintetizza e riproduce `testo`. Se l'utente preme Invio durante la riproduzione la interrompe
    e ritorna True (segnale per passare subito all'ascolto, senza un altro Invio per aprire il turno).

    Nota: uso select() su stdin invece di un thread bloccato su input(), perché un input() lasciato
    in attesa dopo la fine naturale dell'audio "ruberebbe" l'Invio destinato al prompt successivo.
    """
    percorso = tts.sintetizza(testo, percorso="risposta.mp3")
    processo = subprocess.Popen(["afplay", "-r", str(config.TTS_VELOCITA), percorso])  # macOS

    print("(Premi Invio per interrompere e parlare subito)")
    while processo.poll() is None:
        pronto, _, _ = select.select([sys.stdin], [], [], 0.05)
        if pronto:
            sys.stdin.readline()  # consuma l'Invio, così non resta in coda per il prossimo prompt
            processo.terminate()
            processo.wait()
            return True
    return False


def main():
    stt = SpeechToText()
    tts = TextToSpeech()
    rag = RagChain()
    dialog_manager = DialogManager(rag.chain, rag.llm)
    # thread_id nuovo a ogni avvio: ogni sessione parte con cronologia pulita invece di
    # riprendere (e accumulare all'infinito) quella delle sessioni precedenti
    thread_id = str(uuid.uuid4())

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

        # 1) registra e trascrivi
        audio = registra()
        print("transcribing...")
        domanda = stt.trascrivi_array(audio, config.SAMPLE_RATE)
        print("Tu:", domanda)

        # 2) genera la risposta; se serve un chiarimento, lo chiede a voce e attende una nuova
        #    risposta parlata, finché non ha abbastanza contesto
        esito = dialog_manager.invoke(domanda, thread_id=thread_id)
        while esito["tipo"] == "chiarimento":
            print("Bot (chiarimento):", esito["testo"])
            parla(tts, esito["testo"])

            audio_chiarimento = registra()
            print("transcribing...")
            risposta_utente = stt.trascrivi_array(audio_chiarimento, config.SAMPLE_RATE)
            print("Tu:", risposta_utente)

            esito = dialog_manager.rispondi_chiarimento(risposta_utente, thread_id=thread_id)

        risposta = esito["testo"]
        print("Bot:", risposta)

        # 3) sintesi vocale; se l'utente la interrompe, si passa subito al turno successivo
        salta_prompt = parla(tts, risposta)


if __name__ == "__main__":
    main()
