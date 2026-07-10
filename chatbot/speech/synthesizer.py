from gtts import gTTS

from chatbot import config


class TextToSpeech:
    @staticmethod
    def synthesize(testo: str) -> str:
        """synthesize text to speech and save it to a file, returning the path to the file"""
        percorso = str(config.BASE_DIR / "risposta.mp3")
        gTTS(text=testo, lang=config.TTS_LANG).save(percorso)
        return percorso
