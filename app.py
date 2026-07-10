import uuid
import gradio as gr

from chatbot.dialog.manager import DialogManager
from chatbot.rag.rag_chain import RagChain
from chatbot.speech.synthesizer import TextToSpeech
from chatbot.speech.transcriber import SpeechToText

stt = SpeechToText()
rag = RagChain()
dialog_manager = DialogManager(rag.chain, rag.llm)


def _dialogue(question, state):
    """Query the DialogManager (handling clarifications) and return (bot label, answer audio).
    Does not touch the chat: the handlers update it in two steps."""
    thread_id = state["thread_id"]
    if state["awaiting_clarification"]:
        result = dialog_manager.answer_clarification(question, thread_id=thread_id)
    else:
        result = dialog_manager.invoke(question, thread_id=thread_id)

    state["awaiting_clarification"] = (result["type"] == "clarification")

    bot_text = result["text"]
    label = "❓ " + bot_text if result["type"] == "clarification" else bot_text

    # speech synthesis (gTTS) depends on an external service and can fail transiently:
    # in that case we still show the text answer, just without audio
    try:
        answer_audio = TextToSpeech.synthesize(bot_text)
    except Exception as e:
        print(f"[app] speech synthesis failed, showing text only: {e}")
        answer_audio = None
    return label, answer_audio


# The turn is split into two chained events (step 1 → .then(step 2)):
# step 1 adds the user message to the chat (so it appears immediately); step 2 is a plain (non-generator)
# function that computes the answer, and while it runs Gradio shows its native animated "typing" dots on
# the Chatbot. A single streaming generator would NOT show that native animation.

def add_user_text(text, history):
    """Step 1 (text): add the typed message to the chat and clear the textbox."""
    text = (text or "").strip()
    if not text:
        return history, gr.update()
    return history + [{"role": "user", "content": text}], gr.update(value="")


def add_user_audio(audio, history):
    """Step 1 (voice): transcribe the recording and add it to the chat, then clear the recorder."""
    if audio is None:
        return history, gr.update(value=None)
    question = stt.transcribe_audio(audio).strip()
    if not question:
        return history, gr.update(value=None)
    return history + [{"role": "user", "content": question}], gr.update(value=None)


def generate_bot_answer(history, state):
    """Step 2: answer the last user message. As a plain function writing to the Chatbot, it makes
    Gradio show its native loading animation while it runs."""
    if not history or history[-1]["role"] != "user":
        return history, None, state  # nothing pending (e.g. empty input in step 1)
    question = history[-1]["content"]
    label, answer_audio = _dialogue(question, state)
    return history + [{"role": "assistant", "content": label}], answer_audio, state


def new_conversation():
    """Reset chat and state with a new thread_id (clean history)."""
    state = {"thread_id": str(uuid.uuid4()), "awaiting_clarification": False}
    return [], None, state, gr.update(value=None), gr.update(value="")


def create_ui():
    with gr.Blocks(title="Guida Caravaggio & Caracciolo") as demo:
        gr.Markdown(
            "# 🎨 Guida alle opere di Caravaggio e Caracciolo\n"
            "Fai la tua domanda **a voce** (microfono + Invia) oppure **scrivendola** nel campo di testo. "
            "Le risposte riguardano le opere dei due artisti e i musei di Napoli che le espongono."
        )

        state = gr.State({"thread_id": str(uuid.uuid4()), "awaiting_clarification": False})

        chatbot = gr.Chatbot(height=420, label="Conversazione")

        text_in = gr.Textbox(
            label="Oppure scrivi la domanda",
            placeholder="Es. Quante opere di Caravaggio ci sono a Napoli?",
            submit_btn="Invia",
        )

        audio_in = gr.Audio(sources=["microphone"], type="numpy", label="Domanda a voce")

        with gr.Row():
            send_btn = gr.Button("🎤 Invia audio", variant="primary")
            reset_btn = gr.Button("Nuova conversazione")

        audio_out = gr.Audio(label="Risposta", autoplay=True)

        # voice: transcribe + show the message (step 1), then generate the answer with the native
        # loading animation (step 2)
        send_btn.click(
            add_user_audio,
            inputs=[audio_in, chatbot],
            outputs=[chatbot, audio_in],
        ).then(
            generate_bot_answer,
            inputs=[chatbot, state],
            outputs=[chatbot, audio_out, state],
        )
        # text: show the message (step 1), then generate the answer (step 2)
        text_in.submit(
            add_user_text,
            inputs=[text_in, chatbot],
            outputs=[chatbot, text_in],
        ).then(
            generate_bot_answer,
            inputs=[chatbot, state],
            outputs=[chatbot, audio_out, state],
        )
        reset_btn.click(
            new_conversation,
            inputs=None,
            outputs=[chatbot, audio_out, state, audio_in, text_in],
        )
        return demo


if __name__ == "__main__":
    create_ui().launch(share=True)
