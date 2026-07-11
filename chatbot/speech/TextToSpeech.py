"""Speech synthesis (text-to-speech) via gTTS.

Only produces the audio file; playback happens in the browser (Gradio web interface), which receives
the path to the mp3 file.
"""
from gtts import gTTS

from chatbot import config


class TextToSpeech:
    @staticmethod
    def synthesize(text: str) -> str:
        """Synthesize `text` to speech, save it to a file and return the file path."""
        path = str(config.BASE_DIR / "risposta.mp3")
        gTTS(text=text, lang=config.TTS_LANG).save(path)
        return path
