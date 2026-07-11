"""Speech recognition (speech-to-text) via Whisper. Shared by the web interface."""
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

    def transcribe_audio(self, audio) -> str:
        """Transcribe the (sample_rate, ndarray) format returned by Gradio's microphone."""
        sample_rate, audio = audio
        data = np.asarray(audio).astype(np.float32)  # cast to float32 for Whisper
        result = self._pipeline(
            {"raw": data, "sampling_rate": sample_rate},
            generate_kwargs={"language": "italian"},
        )
        return result["text"].strip()
