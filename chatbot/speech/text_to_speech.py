"""Speech synthesis (text-to-speech) via gTTS.

Only produces the audio file; playback happens in the browser (Gradio web interface), which receives
the path to the mp3 file.
"""
import os
import tempfile

from gtts import gTTS

from chatbot import config


class TextToSpeech:
    @staticmethod
    def synthesize(text: str) -> str:
        """Synthesize `text` to speech, save it to a temporary file and return the file path.

        A fresh temp file per call (instead of a single shared "risposta.mp3") avoids race
        conditions between concurrent sessions and stale-audio caching in the browser.
        """
        fd, path = tempfile.mkstemp(prefix="risposta_", suffix=".mp3")
        os.close(fd)
        gTTS(text=text, lang=config.TTS_LANG).save(path)
        return path
