import tempfile
import uuid

import gradio as gr
import numpy as np
import torch
from gtts import gTTS
from transformers import pipeline

from rag import chain, llm_cypher
from DialogManager import DialogManager

# ── Setup modelli (condivisi con whisper_gtts.py, ma qui senza loop da terminale) ──
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
transcriber = pipeline("automatic-speech-recognition",
                       model="openai/whisper-large-v3", device=DEVICE)

dialog_manager = DialogManager(chain, llm_cypher)


def trascrivi(audio):
    """audio è (sample_rate, np.ndarray) dal microfono di Gradio -> testo italiano."""
    sample_rate, dati = audio
    dati = dati.astype(np.float32)
    # normalizza gli interi PCM in [-1, 1] se necessario
    if np.issubdtype(audio[1].dtype, np.integer):
        dati /= np.iinfo(audio[1].dtype).max
    # se stereo, media i canali
    if dati.ndim > 1:
        dati = dati.mean(axis=1)
    risultato = transcriber(
        {"raw": dati, "sampling_rate": sample_rate},
        generate_kwargs={"language": "italian"},
    )
    return risultato["text"].strip()


def sintetizza(testo):
    """Genera l'audio della risposta e ne ritorna il percorso, per la riproduzione nel browser."""
    tts = gTTS(text=testo, lang="it")
    percorso = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    tts.save(percorso)
    return percorso


def _rispondi(domanda, cronologia, stato):
    """Logica di dialogo comune a voce e testo: passa la domanda al DialogManager
    (gestendo i chiarimenti) e aggiorna chat + audio della risposta."""
    domanda = (domanda or "").strip()
    if not domanda:
        return cronologia, None, stato

    cronologia = cronologia + [{"role": "user", "content": domanda}]

    thread_id = stato["thread_id"]
    if stato["in_attesa_chiarimento"]:
        esito = dialog_manager.rispondi_chiarimento(domanda, thread_id=thread_id)
    else:
        esito = dialog_manager.invoke(domanda, thread_id=thread_id)

    stato["in_attesa_chiarimento"] = (esito["tipo"] == "chiarimento")

    testo_bot = esito["testo"]
    etichetta = "❓ " + testo_bot if esito["tipo"] == "chiarimento" else testo_bot
    cronologia = cronologia + [{"role": "assistant", "content": etichetta}]

    audio_risposta = sintetizza(testo_bot)
    return cronologia, audio_risposta, stato


def gestisci_audio(audio, cronologia, stato):
    """Trascrive la richiesta vocale e la inoltra alla logica di dialogo comune."""
    if audio is None:
        return cronologia, None, stato, gr.update(value=None)
    domanda = trascrivi(audio)
    cronologia, audio_risposta, stato = _rispondi(domanda, cronologia, stato)
    return cronologia, audio_risposta, stato, gr.update(value=None)


def gestisci_testo(testo, cronologia, stato):
    """Inoltra la domanda digitata alla logica di dialogo comune."""
    cronologia, audio_risposta, stato = _rispondi(testo, cronologia, stato)
    return cronologia, audio_risposta, stato, gr.update(value="")


def nuova_conversazione():
    """Resetta chat e stato con un nuovo thread_id (cronologia pulita)."""
    stato = {"thread_id": str(uuid.uuid4()), "in_attesa_chiarimento": False}
    return [], None, stato, gr.update(value=None), gr.update(value="")


with gr.Blocks(title="Guida Caravaggio & Caracciolo") as demo:
    gr.Markdown(
        "# 🎨 Guida alle opere di Caravaggio e Caracciolo\n"
        "Fai la tua domanda **a voce** (microfono + Invia) oppure **scrivendola** nel campo di testo. "
        "Le risposte riguardano le opere dei due artisti e i musei di Napoli che le espongono."
    )

    stato = gr.State({"thread_id": str(uuid.uuid4()), "in_attesa_chiarimento": False})

    chatbot = gr.Chatbot(height=420, label="Conversazione")

    with gr.Row():
        audio_in = gr.Audio(sources=["microphone"], type="numpy", label="Domanda a voce")

    with gr.Row():
        invia_btn = gr.Button("🎤 Invia audio", variant="primary")
        reset_btn = gr.Button("Nuova conversazione")

    testo_in = gr.Textbox(
        label="Oppure scrivi la domanda",
        placeholder="Es. Quante opere di Caravaggio ci sono a Napoli?",
        submit_btn="Invia",
    )

    audio_out = gr.Audio(label="Risposta", autoplay=True)

    invia_btn.click(
        gestisci_audio,
        inputs=[audio_in, chatbot, stato],
        outputs=[chatbot, audio_out, stato, audio_in],
    )
    testo_in.submit(
        gestisci_testo,
        inputs=[testo_in, chatbot, stato],
        outputs=[chatbot, audio_out, stato, testo_in],
    )
    reset_btn.click(
        nuova_conversazione,
        inputs=None,
        outputs=[chatbot, audio_out, stato, audio_in, testo_in],
    )


if __name__ == "__main__":
    demo.launch()
