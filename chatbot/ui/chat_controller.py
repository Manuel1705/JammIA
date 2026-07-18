import gradio as gr

from chatbot.ui.session_state import SessionState, new_session_state
from chatbot.dialog.dialog_manager import DialogManager
from chatbot.speech.text_to_speech import TextToSpeech
from chatbot.speech.speech_to_text import SpeechToText

# saluto iniziale mostrato in chat (all'avvio e dopo "N'ata vota")
_GREETING = {
    "role": "assistant",
    "content": (
        "Uè, benvenuto! 👋 Sono JammIA, la tua guida napoletana alle opere di Caravaggio "
        "e Caracciolo e ai musei di Napoli che le espongono. Jamme jà, chiedimi quello che vuoi sapere!"
    ),
}


class ChatController:
    """Holds the app's dependencies (speech-to-text, dialogue manager, text-to-speech) and exposes
    the Gradio event handlers as methods.

    A turn is split into two chained events (step 1 → .then(step 2)): step 1 adds the user message so
    it appears immediately; step 2 is a function that computes the answer while showing animated
    "typing" dots on the Chatbot.
    """

    def __init__(self):
        self._stt = SpeechToText()
        self._dialog = DialogManager()

    def launch(self, **kwargs):
        """Build the UI and launch it. In Gradio 6 the theme is passed to launch(), not to Blocks."""
        theme = gr.themes.Soft(primary_hue="sky", secondary_hue="cyan")  # azzurro Napoli
        self.create_ui().launch(theme=theme, **kwargs)

    def create_ui(self):
        with gr.Blocks(title="JammIA — 'a guida a Caravaggio e Caracciolo") as demo:
            # gr.State must be created INSIDE the Blocks context, otherwise it isn't registered with
            # this demo and Gradio raises KeyError when reading it during an event (state[block._id]).
            # Initial value None (NOT new_session_state()): the initial value is evaluated once at UI
            # build time and deep-copied to every session, so all users would share the same thread_id
            # (and thus the same conversation memory). The state is initialized lazily per session in
            # _generate_bot_answer.
            state = gr.State(None)

            gr.Markdown(
                "# 🌋 JammIA — 'a guida a Caravaggio e Caracciolo\n"
                "Uè! Fai la tua domanda **a voce** (microfono + Invia) oppure **scrivendola** nel campo di testo. "
                "Ti racconto le opere dei due artisti e i musei di Napoli che le espongono. Jamme jà! 🎨"
            )

            chatbot = gr.Chatbot(height=420, label="'A chiacchierata", value=[_GREETING])

            text_in = gr.Textbox(
                label="Oppure scrivi la domanda",
                placeholder="Es. Quante opere di Caravaggio ci sono a Napoli?",
                submit_btn="Invia",
            )

            audio_in = gr.Audio(sources=["microphone"], type="numpy", label="Domanda a voce")

            with gr.Row():
                send_btn = gr.Button("🎤 Manna 'a domanda", variant="primary")
                reset_btn = gr.Button("🔁 N'ata vota (nuova conversazione)")

            audio_out = gr.Audio(label="'A risposta di JammIA", autoplay=True)

            # voice: transcribe + show the message (step 1), then generate the answer with the native
            # loading animation (step 2)
            send_btn.click(
                self._add_user_audio,
                inputs=[audio_in, chatbot],
                outputs=[chatbot, audio_in],
            ).then(
                self._generate_bot_answer,
                inputs=[chatbot, state],
                outputs=[chatbot, audio_out, state],
            )
            # text: show the message (step 1), then generate the answer (step 2)
            text_in.submit(
                self._add_user_text,
                inputs=[text_in, chatbot],
                outputs=[chatbot, text_in],
            ).then(
                self._generate_bot_answer,
                inputs=[chatbot, state],
                outputs=[chatbot, audio_out, state],
            )
            reset_btn.click(
                self.new_conversation,
                inputs=None,
                outputs=[chatbot, audio_out, state, audio_in, text_in],
            )
            return demo

    def _dialogue(self, question, state: SessionState):
        """Query the DialogManager (handling clarifications) and return (bot label, answer audio).
        Does not touch the chat: the handlers update it."""
        thread_id = state["thread_id"]
        if state["awaiting_clarification"]:
            result = self._dialog.answer_clarification(question, thread_id=thread_id)
        else:
            result = self._dialog.invoke(question, thread_id=thread_id)

        state["awaiting_clarification"] = result["type"] == "clarification"

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

    def _add_user_text(self, text, history):
        """Step 1 (text): add the typed message to the chat and clear the textbox."""
        text = (text or "").strip()
        if not text:
            return history, gr.update()
        return history + [{"role": "user", "content": text}], gr.update(value="")

    def _add_user_audio(self, audio, history):
        """Step 1 (voice): transcribe the recording and add it to the chat, then clear the recorder."""
        if audio is None:
            return history, gr.update(value=None)
        question = self._stt.transcribe_audio(audio).strip()
        if not question:
            return history, gr.update(value=None)
        return history + [{"role": "user", "content": question}], gr.update(value=None)

    def _generate_bot_answer(self, history, state: SessionState | None):
        """Step 2: answer the last user message. As a plain function writing to the Chatbot, it makes
        Gradio show its native loading animation while it runs."""
        if state is None:  # first turn of this session: create a per-session thread_id
            state = new_session_state()
        if not history or history[-1]["role"] != "user":
            return history, None, state  # nothing pending (e.g. empty input in step 1)
        question = self._message_text(history[-1]["content"])
        label, answer_audio = self._dialogue(question, state)
        return history + [{"role": "assistant", "content": label}], answer_audio, state

    @staticmethod
    def _message_text(content) -> str:
        """Gradio may return a chat message's content as a list of parts
        (e.g. [{"text": "...", "type": "text"}]) instead of a plain string. Normalize it to text, so
        the question passed downstream — and stored in the conversation history — is clean."""
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
        return content or ""

    @staticmethod
    def new_conversation():
        """Reset chat and state with a new thread_id (clean history), keeping the greeting."""
        return [_GREETING], None, new_session_state(), gr.update(value=None), gr.update(value="")
