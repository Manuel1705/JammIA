import numpy as np
from transformers import pipeline

from chatbot import config


class SpeechToText:
    def __init__(self):
        self._pipeline = pipeline(
            "automatic-speech-recognition",
            config.WHISPER_MODEL,
            device=config.DEVICE,
        )

    def trascrivi_audio(self, audio) -> str:
        sample_rate, audio = audio
        dati = np.asarray(audio).astype(np.float32)  # cast to [float32] for whisper
        risultato = self._pipeline(
            {"raw": dati, "sampling_rate": sample_rate},
            generate_kwargs={"language": "italian"},
        )
        return risultato["text"].strip()
