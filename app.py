"""Entry point: interfaccia web (Gradio) del chatbot.

Uso:  uv run app.py
Permette di fare domande a voce (microfono) o scritte; mostra la conversazione e riproduce la
risposta come audio nel browser.
"""
import uuid
import warnings

# warning innocuo interno a Gradio: usa una costante Starlette deprecata (HTTP_422_UNPROCESSABLE_ENTITY).
# Non dipende dal nostro codice; lo silenziamo solo per pulire la console.
warnings.filterwarnings("ignore", message=".*HTTP_422_UNPROCESSABLE_ENTITY.*")

import gradio as gr

from chatbot.dialog.manager import DialogManager
from chatbot.rag.rag_chain import RagChain
from chatbot.speech.synthesizer import TextToSpeech
from chatbot.speech.transcriber import SpeechToText

# ── Componenti condivisi (STT, TTS, RAG, gestione dialogo) ──
stt = SpeechToText()
tts = TextToSpeech()
rag = RagChain()
dialog_manager = DialogManager(rag.chain, rag.llm)


def _rispondi(domanda, cronologia, stato):
    """Logica di dialogo comune a voce e testo: passa la domanda al DialogManager (gestendo i
    chiarimenti) e aggiorna chat + audio della risposta."""
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

    audio_risposta = tts.sintetizza(testo_bot)
    return cronologia, audio_risposta, stato


def gestisci_audio(audio, cronologia, stato):
    """Trascrive la richiesta vocale e la inoltra alla logica di dialogo comune."""
    if audio is None:
        return cronologia, None, stato, gr.update(value=None)
    domanda = stt.trascrivi_gradio(audio)
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
