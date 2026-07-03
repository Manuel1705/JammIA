"""Sintesi vocale (text-to-speech) tramite gTTS.

Questa classe si occupa solo di produrre il file audio: la riproduzione è lasciata a chi la usa
(nel browser per l'interfaccia web, via `afplay` per la CLI), perché è specifica dell'interfaccia.
"""
import tempfile

from gtts import gTTS

from chatbot import config


class TextToSpeech:
    def __init__(self, lang: str = None):
        self.lang = lang or config.TTS_LANG

    def sintetizza(self, testo: str, percorso: str = None) -> str:
        """Genera l'audio di `testo` e ne ritorna il percorso del file mp3.
        Se `percorso` non è fornito, usa un file temporaneo."""
        if percorso is None:
            percorso = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        gTTS(text=testo, lang=self.lang).save(percorso)
        return percorso
