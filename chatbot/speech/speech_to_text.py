"""Speech recognition (speech-to-text) via Whisper. Shared by the web interface."""
import numpy as np
from transformers import pipeline
from chatbot import config
from transformers.utils import logging as hf_logging

hf_logging.set_verbosity_error()


class SpeechToText:
    def __init__(self):
        self._pipeline = pipeline(
            "automatic-speech-recognition",
            config.WHISPER_MODEL,
            device=config.DEVICE,
        )

    def transcribe_audio(self, audio) -> str:
        """Transcribe the (sample_rate, ndarray) format returned by Gradio's microphone."""
        sample_rate, raw = audio
        raw = np.asarray(raw)
        # Whisper expects mono float32 in [-1, 1]; Gradio's microphone returns int16
        # (and possibly stereo), so normalize by the integer range and average the channels.
        if np.issubdtype(raw.dtype, np.integer):
            data = raw.astype(np.float32) / np.iinfo(raw.dtype).max
        else:
            data = raw.astype(np.float32)
        if data.ndim == 2:  # stereo -> mono
            data = data.mean(axis=1)
        result = self._pipeline(
            {"raw": data, "sampling_rate": sample_rate},
            generate_kwargs={"language": "italian"},
        )
        return result["text"].strip()
